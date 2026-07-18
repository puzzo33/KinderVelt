"""Monthly close orchestrator — the seven stages end to end (SPEC §9).

Idempotent by construction: derived/ and reports/ for the month are
rebuilt from inputs + knowledge base on every run; ids are deterministic;
the cumulative register is regenerated, so re-uploading corrected files
and re-running can never create duplicates.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import (analyze, anomalies, confidence, gaps as gaps_mod, ingest,
               lock as lock_mod, normalize, reconcile, registry, reports,
               trace)
from .config import Knowledge, load_knowledge
from .model import DocType


class CloseError(Exception):
    pass


def close_month(root: Path, month: str, amend: bool = False) -> dict:
    """Run the full close for a month. Returns a summary dict."""
    root = Path(root)
    k = load_knowledge(root)
    month_dir = root / "months" / month
    inputs = month_dir / "inputs"
    if not inputs.exists() or not any(
            p for p in inputs.iterdir() if p.name != ".gitkeep"):
        raise CloseError(f"{month}: no inputs found in {inputs} — add the "
                         "month's documents first (see README runbook)")

    locked = lock_mod.is_locked(month_dir)
    if locked and not amend:
        raise CloseError(
            f"{month} is approved and locked (SPEC §9.8). Re-run with "
            f"--amend to produce an amendment against the approved figures.")

    # full rebuild of derived state — idempotent reprocessing
    for sub in ("derived", "reports"):
        d = month_dir / sub
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    # ---- Stage 1: import ---------------------------------------------------
    # a malformed document never crashes the close: it is marked
    # low-confidence and surfaces as an unreadable_document gap (§4.1)
    def _read(doc, reader, default):
        try:
            return reader(inputs / doc.file, doc)
        except Exception as e:  # noqa: BLE001 — one bad file must not kill the close
            doc.extraction_confidence = "low"
            doc.notes = str(e)
            return default

    docs = registry.scan_inputs(month_dir, month)
    live_wb = registry.live(docs, DocType.ACCOUNTING_WORKBOOK.value)
    workbook = None
    if live_wb:
        workbook = _read(live_wb[0], ingest.read_workbook, None)

    bank_rows_by_account: dict[str, list] = {}
    for d in registry.live(docs, DocType.BANK_STATEMENT.value):
        rows = _read(d, ingest.read_bank_statement, [])
        if rows:
            bank_rows_by_account.setdefault(d.account or "unknown", []).extend(rows)

    stats_rows: list[dict] = []
    for d in registry.live(docs, DocType.CENTER_STATS.value):
        stats_rows.extend(_read(d, ingest.read_center_stats, []))

    wise_transfers: list[dict] = []
    for d in registry.live(docs, DocType.WISE_TRANSFER.value):
        wise_transfers.extend(_read(d, ingest.read_wise, []))

    funding_requests: list[dict] = []
    for d in registry.live(docs, DocType.FUNDING_REQUEST.value):
        req = _read(d, ingest.read_funding_request, None)
        if req:
            funding_requests.append(req)

    registry.save_registry(docs, month_dir, root)

    # ---- Stage 2: normalize ------------------------------------------------
    txns, fx_gaps = ([], [])
    if workbook:
        txns, fx_gaps = normalize.normalize_ledger(k, month, workbook["ledger"])
    # US-entity statements (USD) are kept apart from the Ukrainian books:
    # they anchor the US cash position and transfer verification, never
    # the UAH reconciliation
    us_ids = {a["id"] for a in k.active_us_accounts()}
    bank_lines, us_lines = [], []
    for account, rows in bank_rows_by_account.items():
        lines = normalize.normalize_bank(k, month, account, rows)
        (us_lines if account in us_ids else bank_lines).extend(lines)

    # ---- Stage 3: reconcile ------------------------------------------------
    reconcile.match_bank(k, txns, bank_lines)
    reconciliation = reconcile.reconcile(
        k, root, month, txns, bank_lines,
        workbook["balances"] if workbook else [])

    # ---- Stage 4: funding traceability --------------------------------------
    traces = trace.build_traces(k, month, wise_transfers, funding_requests,
                                txns, bank_lines, us_lines)

    # ---- Stage 5 & 6: analysis ----------------------------------------------
    fin = analyze.financial_analysis(k, month, txns)
    ops = analyze.operational_analysis(k, month, stats_rows, fin)
    prior = analyze.load_prior_analysis(root, month)

    # ---- gap detection (feeds Stage 7 and the re-upload loop) ---------------
    gaps = gaps_mod.detect_gaps(k, month, docs, workbook,
                                ops["missing_centers"], fx_gaps, traces)

    # ---- Stage 7: exceptions -------------------------------------------------
    findings = anomalies.detect(k, month, txns, bank_lines, reconciliation,
                                traces, workbook["payroll"] if workbook else [],
                                prior, gaps)

    conf = confidence.score(k, reconciliation, traces, txns, ops, gaps)

    # ---- persist derived state ------------------------------------------------
    derived = month_dir / "derived"
    with open(derived / "transactions.jsonl", "w", encoding="utf-8") as f:
        for t in sorted(txns, key=lambda t: (t.date, t.txn_id)):
            f.write(json.dumps(t.as_dict(), ensure_ascii=False) + "\n")
    with open(derived / "bank_lines.jsonl", "w", encoding="utf-8") as f:
        for l in sorted(bank_lines, key=lambda l: (l.account, l.date, l.line_id)):
            f.write(json.dumps(l.as_dict(), ensure_ascii=False) + "\n")
    with open(derived / "us_lines.jsonl", "w", encoding="utf-8") as f:
        for l in sorted(us_lines, key=lambda l: (l.account, l.date, l.line_id)):
            f.write(json.dumps(l.as_dict(), ensure_ascii=False) + "\n")
    _dump(derived / "reconciliation.json", reconciliation)
    _dump(derived / "traces.json", traces)
    _dump(derived / "analysis.json", {"financial": fin, "operational": ops})
    _dump(derived / "exceptions.json", [f.as_dict() for f in findings])
    _dump(derived / "gaps.json", gaps)
    _dump(derived / "confidence.json", conf)

    # ---- reports ---------------------------------------------------------------
    rdir = month_dir / "reports"
    (rdir / "01_executive_summary.md").write_text(
        reports.executive_summary(k, month, fin, conf, findings, gaps),
        encoding="utf-8")
    (rdir / "02_treasurer_report.md").write_text(
        reports.treasurer_report(k, month, fin, conf, findings, gaps,
                                 reconciliation, traces, ops, prior),
        encoding="utf-8")
    (rdir / "03_board_report.md").write_text(
        reports.board_report(k, month, fin, ops, findings), encoding="utf-8")
    (rdir / "04_donor_transparency_report.md").write_text(
        reports.donor_report(k, month, fin, ops), encoding="utf-8")
    (rdir / "05_trace_cards.md").write_text(
        reports.trace_cards_md(k, month, traces), encoding="utf-8")
    (month_dir / "GAPS.md").write_text(
        reports.gaps_md(k, month, gaps), encoding="utf-8")

    if locked and amend:
        (rdir / "AMENDMENT.md").write_text(
            lock_mod.amendment_report(month_dir, month), encoding="utf-8")

    register_path = reports.rebuild_master_register(k, root)

    open_findings = [f for f in findings if f.status == "open"]
    return {
        "month": month,
        "documents": len(docs),
        "transactions": len(txns),
        "bank_lines": len(bank_lines),
        "confidence": conf["overall"],
        "risk": conf["risk"],
        "open_exceptions": len(open_findings),
        "auto_explained": sum(1 for f in findings if f.status == "auto_explained"),
        "gaps_blocking": sum(1 for g in gaps if g["severity"] == "blocking"),
        "gaps_total": len(gaps),
        "fully_reconciled": reconciliation["fully_reconciled"],
        "amended": locked and amend,
        "register": str(register_path),
        "reports_dir": str(rdir),
    }


def _dump(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
