"""Hard daily budget on paid Gemini calls — the guard that was missing.

WHY THIS EXISTS (2026-08-02): Gemini spend jumped $42.75 -> $76/day in one day
and nothing in the pipeline noticed, because nothing was counting. The direct
trigger was media remedies re-billing vision calls forever on robots that could
never converge (capped separately in remedies/registry.py), but the structural
problem was bigger: every throughput lever added that week (workers, caps,
extra stages) multiplied paid-call volume, and the only meter was the billing
console, read by a human, a day late. This is the second cost incident of this
shape. Budget-sensitive levers must fail CLOSED from now on.

WHAT IT DOES
------------
* `client(**kwargs)` returns a genai.Client whose `models.generate_content`
  charges a persistent per-day counter BEFORE each call and raises
  `SpendBudgetExceeded` once the day's budget is spent.
* The counter lives in state/gemini_spend.json — `state/` survives both code
  deploys (tar excludes it) and cycle restarts, so the budget is per-DAY,
  not per-process. A runaway loop cannot reset it by restarting.
* Budget: env `GEMINI_DAILY_CALL_BUDGET`, default 2500 calls/day. At typical
  flash pricing that bounds worst-case spend well under the incident level
  while leaving ~2x headroom over legitimate daily volume.
* `status()` returns today's usage for cycle-log visibility — every cycle
  prints it, so an anomaly shows in the log the same hour, not on the bill.

FAIL BEHAVIOR
-------------
Exhaustion raises rather than silently continuing. Callers that already treat
Gemini as an optional upgrade (grounded selection, verification — all wrap
calls in try/except and fall back to heuristics) degrade gracefully: paid
calls stop, the pipeline keeps running free. Callers where Gemini is load-
bearing (discovery extraction) fail their item and move on. Both beat the
alternative, which is what actually happened: unlimited spend, invisible.

A test (tests/test_spend_guard.py) greps for raw `genai.Client(` outside this
module so new call sites cannot quietly bypass the meter.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # POSIX only; Windows dev runs are single-process so the thread lock suffices
    import fcntl
except ImportError:
    fcntl = None

_RESEARCH_DIR = Path(__file__).resolve().parent
STATE_PATH = _RESEARCH_DIR / "state" / "gemini_spend.json"

DEFAULT_DAILY_BUDGET = 2500

_LOCK = threading.Lock()


@contextlib.contextmanager
def _ledger_lock():
    """Cross-PROCESS exclusive lock on the spend ledger.

    Added 2026-08-04 when the VM pipeline split into two systemd loops
    (discovery.service + enrichment.service) sharing this one ledger. The
    thread lock no longer covers both writers, and a lost read-modify-write
    UNDERCOUNTS — on a cost guard, the one direction that must never happen.
    """
    with _LOCK:
        if fcntl is None:
            yield
            return
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_PATH.with_suffix(".lock"), "a+") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


class SpendBudgetExceeded(RuntimeError):
    """Today's GEMINI_DAILY_CALL_BUDGET is spent — no further paid calls."""


def _budget() -> int:
    try:
        return int(os.environ.get("GEMINI_DAILY_CALL_BUDGET", "") or DEFAULT_DAILY_BUDGET)
    except ValueError:
        return DEFAULT_DAILY_BUDGET


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict[str, Any]:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt file = fresh day, never crash the pipeline
        data = {}
    if data.get("date") != _today():
        data = {"date": _today(), "calls": 0, "by_kind": {}}
    return data


def _save(data: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    except Exception:  # noqa: BLE001 — a failed save loses one increment, never the run
        pass


def charge(kind: str = "generate_content") -> None:
    """Record one paid call; raise SpendBudgetExceeded when the day is spent.

    Charged BEFORE the call so exhaustion stops spend immediately rather than
    one call late. Serialized across processes via _ledger_lock — since the
    discovery/enrichment service split, two loops write this ledger and a
    lost update would undercount a cost guard.
    """
    with _ledger_lock():
        data = _load()
        if data["calls"] >= _budget():
            raise SpendBudgetExceeded(
                f"GEMINI_DAILY_CALL_BUDGET spent: {data['calls']}/{_budget()} calls "
                f"today ({data['date']}) — refusing further paid calls until UTC midnight. "
                f"Raise the env var only after checking WHY today's volume is this high."
            )
        data["calls"] += 1
        data["by_kind"][kind] = data["by_kind"].get(kind, 0) + 1
        _save(data)


def status() -> dict[str, Any]:
    """Today's usage — printed into every cycle log for same-hour visibility."""
    with _ledger_lock():
        data = _load()
    return {**data, "budget": _budget()}


class _MeteredModels:
    """Proxy for client.models that meters generate_content, passes through the rest."""

    def __init__(self, models: Any):
        self._models = models

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        model = str(kwargs.get("model") or (args[0] if args else "")) or "unknown"
        charge(f"generate_content:{model}")
        return self._models.generate_content(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._models, name)


class _MeteredClient:
    """Proxy for genai.Client — only `.models` is intercepted."""

    def __init__(self, real: Any):
        self._real = real
        self.models = _MeteredModels(real.models)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def client(**kwargs: Any) -> Any:
    """Drop-in replacement for genai.Client(**kwargs), with the meter attached.

    Every pipeline construction site MUST use this (enforced by
    tests/test_spend_guard.py). api_key defaults from GEMINI_API_KEY the same
    way most sites already passed it.

    When RESEARCH_LLM_PROVIDER names local subscription CLIs (llm_broker.py),
    the returned client routes plain/vision JSON calls through them first and
    only falls back to metered Gemini — search-grounded calls always stay on
    Gemini. Local-only by design: the VM never sets that env var.
    """
    from google import genai

    kwargs.setdefault("api_key", os.environ.get("GEMINI_API_KEY", ""))

    def _metered_gemini():
        return _MeteredClient(genai.Client(**kwargs))

    try:
        import llm_broker
        if llm_broker.cli_providers_configured():
            return llm_broker.BrokerClient(_metered_gemini)
    except ImportError:
        pass
    return _metered_gemini()
