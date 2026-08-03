"""Route pipeline LLM calls through local subscription CLIs instead of the
metered Gemini API.

WHY (2026-08-02): after a Gemini overspend incident, Martti wants surplus
capacity on subscriptions he already pays for (Claude Code, Codex, Cursor) to
absorb pipeline inference — classification, grounded selection, description
generation — as a cost offset. This is LOCAL-ONLY by design: subscription auth
lives on his PC, so the env var that activates this is set locally and never on
the VM (which keeps using metered, budget-guarded Gemini).

HOW
---
`spend_guard.client()` — the single choke point every pipeline Gemini call
already routes through — returns a `BrokerClient` when
`RESEARCH_LLM_PROVIDER` names a CLI provider chain, e.g.:

    RESEARCH_LLM_PROVIDER=claude_cli,codex_cli,gemini

The broker mimics the one sliver of genai.Client the pipeline uses
(`client.models.generate_content(...).text`), so no call site changes.

Routing rules:
  * Search-grounded calls (config carries `tools`, e.g. release-year lookup,
    YouTube search) ALWAYS go to real Gemini — headless CLIs cannot do
    citation-grounded search faithfully, and an uncited year is worse than no
    year (see release_year quarantine history).
  * Vision calls (image parts) are claude_cli-only among the CLIs — Claude Code
    reads image files natively; codex/cursor get text-only calls.
  * Any CLI failure/timeout falls through the chain, ending at metered Gemini
    (still budget-guarded). Fail-open on quality, fail-closed on spend.

Subscription etiquette: these CLIs share rate windows with interactive use.
The broker is throttle-aware in the crudest honest way — a provider that fails
`_COOLDOWN_AFTER_FAILURES` times in a row is benched for `_BENCH_SECONDS` so a
rate-limited CLI doesn't get hammered while it's refusing work.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_CLI_TIMEOUT = int(os.environ.get("LLM_CLI_TIMEOUT", "240") or 240)
_COOLDOWN_AFTER_FAILURES = 3
_BENCH_SECONDS = 900

# Hard per-process cap on subscription CLI calls — the broker's equivalent of
# GEMINI_DAILY_CALL_BUDGET, protecting the OTHER wallet (Claude/Codex/Cursor
# rate windows are shared with Martti's interactive work; an unbounded batch
# could lock him out of his own tools by morning). 0 = unlimited (don't).
_CLI_MAX_CALLS = int(os.environ.get("LLM_CLI_MAX_CALLS", "50") or 50)
_cli_calls_made = 0
_cap_announced = False

_BINARIES = {
    "claude_cli": ("claude",),
    "codex_cli": ("codex",),
    "cursor_cli": ("cursor-agent", "agent"),
}

_bench: dict[str, float] = {}
_fail_streak: dict[str, int] = {}


def provider_chain() -> list[str]:
    raw = os.environ.get("RESEARCH_LLM_PROVIDER", "") or ""
    chain = [p.strip() for p in raw.split(",") if p.strip()]
    return chain


def cli_providers_configured() -> bool:
    return any(p in _BINARIES for p in provider_chain())


def _binary_for(provider: str) -> str | None:
    for name in _BINARIES.get(provider, ()):
        path = shutil.which(name)
        if path:
            return path
    return None


def _log(msg: str) -> None:
    print(f"  [llm_broker] {msg}", flush=True)


def _mark_result(provider: str, ok: bool) -> None:
    if ok:
        _fail_streak[provider] = 0
        return
    _fail_streak[provider] = _fail_streak.get(provider, 0) + 1
    if _fail_streak[provider] >= _COOLDOWN_AFTER_FAILURES:
        _bench[provider] = time.time() + _BENCH_SECONDS
        _log(f"{provider} benched {_BENCH_SECONDS}s after {_fail_streak[provider]} consecutive failures")


def _benched(provider: str) -> bool:
    return _bench.get(provider, 0) > time.time()


def _split_parts(contents: Any) -> tuple[list[str], list[tuple[bytes, str]]]:
    """Separate genai-style contents into prompt text and (bytes, mime) images."""
    texts: list[str] = []
    images: list[tuple[bytes, str]] = []
    items = contents if isinstance(contents, (list, tuple)) else [contents]
    for item in items:
        if isinstance(item, str):
            texts.append(item)
            continue
        inline = getattr(item, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            images.append((inline.data, getattr(inline, "mime_type", "") or "image/jpeg"))
    return texts, images


def _run_cli(provider: str, binary: str, prompt: str, images: list[tuple[bytes, str]]) -> str | None:
    tmpdir: tempfile.TemporaryDirectory | None = None
    try:
        if images:
            if provider != "claude_cli":
                return None  # only Claude Code reads image files headlessly
            tmpdir = tempfile.TemporaryDirectory(prefix="llmbroker_")
            refs = []
            for i, (data, mime) in enumerate(images, 1):
                ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(mime, ".jpg")
                p = Path(tmpdir.name) / f"image_{i}{ext}"
                p.write_bytes(data)
                refs.append(f"IMAGE {i} is the file: {p}")
            prompt = prompt + "\n\nRead each image file listed below before scoring:\n" + "\n".join(refs)

        if provider == "claude_cli":
            cmd = [binary, "-p", prompt, "--output-format", "text"]
            if images:
                cmd += ["--allowedTools", "Read"]
        elif provider == "codex_cli":
            cmd = [binary, "exec", prompt]
        else:  # cursor_cli
            cmd = [binary, "-p", prompt]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_CLI_TIMEOUT,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            _log(f"{provider} rc={proc.returncode}: {(proc.stderr or proc.stdout)[:160]!r}")
            return None
        out = (proc.stdout or "").strip()
        return out or None
    except subprocess.TimeoutExpired:
        _log(f"{provider} timed out after {_CLI_TIMEOUT}s")
        return None
    except Exception as exc:  # noqa: BLE001
        _log(f"{provider} error: {type(exc).__name__}: {exc}")
        return None
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


class _Resp:
    def __init__(self, text: str):
        self.text = text
        self.candidates: list = []


class _BrokerModels:
    def __init__(self, gemini_factory):
        self._gemini_factory = gemini_factory
        self._gemini = None

    def _gemini_generate(self, **kwargs: Any) -> Any:
        if self._gemini is None:
            self._gemini = self._gemini_factory()
        return self._gemini.models.generate_content(**kwargs)

    def generate_content(self, *, model: str = "", contents: Any = None, config: Any = None) -> Any:
        # Search-grounded calls need real Gemini (citations); detect the tools
        # key on both dict configs and GenerateContentConfig objects.
        has_tools = False
        if isinstance(config, dict):
            has_tools = bool(config.get("tools"))
        elif config is not None:
            has_tools = bool(getattr(config, "tools", None))
        if has_tools:
            return self._gemini_generate(model=model, contents=contents, config=config)

        texts, images = _split_parts(contents)
        prompt = "\n".join(texts).strip()
        if not prompt:
            return self._gemini_generate(model=model, contents=contents, config=config)

        global _cli_calls_made, _cap_announced
        for provider in provider_chain():
            if provider == "gemini":
                break
            if provider not in _BINARIES or _benched(provider):
                continue
            if _CLI_MAX_CALLS and _cli_calls_made >= _CLI_MAX_CALLS:
                if not _cap_announced:
                    _log(f"LLM_CLI_MAX_CALLS={_CLI_MAX_CALLS} reached — remaining calls fall through to Gemini")
                    _cap_announced = True
                break
            binary = _binary_for(provider)
            if not binary:
                continue
            t0 = time.time()
            _cli_calls_made += 1
            out = _run_cli(provider, binary, prompt, images)
            _mark_result(provider, out is not None)
            if out is not None:
                _log(f"{provider} ok in {time.time() - t0:.1f}s "
                     f"({'vision, ' if images else ''}{len(prompt)} chars) "
                     f"[{_cli_calls_made}/{_CLI_MAX_CALLS or 'inf'}]")
                return _Resp(out)

        # Chain exhausted -> metered, budget-guarded Gemini.
        return self._gemini_generate(model=model, contents=contents, config=config)


class BrokerClient:
    """Drop-in for the sliver of genai.Client the pipeline uses."""

    def __init__(self, gemini_factory):
        self.models = _BrokerModels(gemini_factory)
