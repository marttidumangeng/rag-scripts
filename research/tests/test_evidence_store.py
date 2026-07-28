"""Evidence store: immutable page/extract persistence for discover/enrich replay."""

from __future__ import annotations

import json
from pathlib import Path

from evidence_store import (
    EvidenceStore,
    company_evidence_bytes,
    load_manifest,
    read_evidence_file,
    sweep_company_evidence,
)


def test_evidence_store_saves_page_extract_and_links(tmp_path, monkeypatch):
    monkeypatch.setattr("evidence_store.EVIDENCE_ROOT", tmp_path / "evidence")
    store = EvidenceStore("acme-robotics", run_id="test-run-1")

    page_entry = store.save_page(
        "https://www.acme.example/robots/bot-1",
        html="<html><body>Bot-1 payload 5kg</body></html>",
        title="Bot-1",
        source="fetch",
    )
    assert page_entry["kind"] == "page"
    assert page_entry["path"].endswith(".html")
    assert (store.root / page_entry["path"]).is_file()

    extract_entry = store.save_extract(
        "https://www.acme.example/robots/bot-1",
        [{"name": "Bot-1", "model_name": "BOT-1"}],
        extractor="gemini_discover",
    )
    assert extract_entry["kind"] == "extract"
    assert (store.root / extract_entry["path"]).is_file()

    store.link_robot(
        "https://www.acme.example/robots/bot-1",
        "Bot-1",
        staging_file="staging/robots/acme-robotics/bot-1.json",
        robot_id=42,
    )
    store.note_target_not_found(
        "https://www.acme.example/robots/other",
        "Ghost-9",
        detail="name not on page",
        robot_id=99,
        page_paths=[page_entry["path"]],
    )
    root = store.finish(discovered=1)
    assert root == store.root

    manifest = load_manifest("acme-robotics", "test-run-1")
    kinds = [e["kind"] for e in manifest["entries"]]
    assert kinds == ["page", "extract", "robot_link", "target_not_found"]
    assert manifest["finished_at"]
    assert manifest["entries"][2]["robot_id"] == 42
    assert manifest["entries"][3]["page_paths"] == [page_entry["path"]]

    body = read_evidence_file("acme-robotics", "test-run-1", page_entry["path"])
    assert "Bot-1 payload" in body

    meta = json.loads((store.root / "meta.json").read_text(encoding="utf-8"))
    assert meta["discovered"] == 1
    assert meta["run_id"] == "test-run-1"
    assert meta["pipeline"] == "discover"


def test_enrich_lean_page_saves_text_not_html(tmp_path, monkeypatch):
    monkeypatch.setattr("evidence_store.EVIDENCE_ROOT", tmp_path / "evidence")
    store = EvidenceStore("acme", run_id="lean-1", pipeline="enrich")
    entry = store.save_page(
        "https://oem.example/bot",
        html="<html><body><h1>RM65</h1><p>payload</p></body></html>",
        text="RM65 payload 5kg",
        title="RM65",
        robot_id=7,
        lean=True,
    )
    assert entry["lean"] is True
    assert entry["robot_id"] == 7
    assert entry["path"].endswith(".txt")
    body = (store.root / entry["path"]).read_text(encoding="utf-8")
    assert body == "RM65 payload 5kg"
    assert "<html>" not in body


def test_force_html_for_target_not_found_audit(tmp_path, monkeypatch):
    monkeypatch.setattr("evidence_store.EVIDENCE_ROOT", tmp_path / "evidence")
    store = EvidenceStore("acme", run_id="html-1", pipeline="enrich")
    entry = store.save_page(
        "https://oem.example/bot",
        html="<html>secret markup</html>",
        text="opaque",
        lean=True,
        force_html=True,
        robot_id=1,
        source="enrich_target_not_found",
    )
    assert entry["path"].endswith(".html")
    assert "secret markup" in (store.root / entry["path"]).read_text(encoding="utf-8")


def test_sweep_keeps_last_n_runs(tmp_path, monkeypatch):
    monkeypatch.setattr("evidence_store.EVIDENCE_ROOT", tmp_path / "evidence")
    for run_id in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z", "20260104T000000Z"):
        store = EvidenceStore("acme", run_id=run_id, pipeline="enrich")
        store.save_page("https://x.example/", text="hello " + run_id, lean=True)
        store.finish()

    result = sweep_company_evidence("acme", keep_runs=2, max_total_bytes=None)
    assert set(result["kept"]) == {"20260103T000000Z", "20260104T000000Z"}
    assert "20260101T000000Z" in result["deleted"]
    assert "20260102T000000Z" in result["deleted"]
    assert company_evidence_bytes("acme") > 0


def test_evidence_relative_root(tmp_path, monkeypatch):
    monkeypatch.setattr("evidence_store.EVIDENCE_ROOT", tmp_path / "evidence")
    store = EvidenceStore("slug", run_id="r2")
    assert store.run_id == "r2"
    assert Path(store.root).is_dir()
