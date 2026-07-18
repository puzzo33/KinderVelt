"""Input completeness / data-gap detection (SPEC §6, the re-upload loop).

Gaps tell the Treasurer exactly what to add to the inputs folder; after
re-uploading, re-running `close` reprocesses the whole month idempotently.
Severity:
  blocking — required input absent/unreadable; the close is degraded
  material — would upgrade figures' data status if provided
  info     — optional document that would not change any figure
"""

from __future__ import annotations

from .config import Knowledge
from .model import DocType, Document, digest
from .registry import live


def detect_gaps(k: Knowledge, month: str, docs: list[Document],
                workbook: dict | None, stats_missing_centers: list[str],
                fx_gaps: list[dict], traces: list[dict]) -> list[dict]:
    gaps: list[dict] = []

    def gap(severity, kind, title, detail, action):
        gaps.append({
            "gap_id": digest(month, kind, title),
            "month": month, "severity": severity, "kind": kind,
            "title": title, "detail": detail, "action": action,
        })

    live_types = {d.doc_type for d in live(docs)}

    if DocType.ACCOUNTING_WORKBOOK.value not in live_types:
        gap("blocking", "missing_input", "Accounting workbook missing",
            "The monthly accounting workbook (general ledger, payroll, "
            "balances) was not found in the inputs folder.",
            f"Add the workbook .xlsx to months/{month}/inputs/ and re-run the close.")
    elif workbook and workbook.get("missing_sheets"):
        gap("blocking", "incomplete_workbook",
            f"Workbook missing sheets: {', '.join(workbook['missing_sheets'])}",
            "The workbook was read but required sheets were not recognized.",
            "Ask the accountant for the full workbook (GeneralLedger, "
            "Balances, PayrollRegister sheets) and replace the file.")

    if DocType.CENTER_STATS.value not in live_types:
        gap("blocking", "missing_input", "Center statistics missing",
            "Monthly center statistics (children served, consultations, "
            "classes, new children) were not provided.",
            f"Add the CenterUpdates file to months/{month}/inputs/ and re-run.")
    elif stats_missing_centers:
        gap("material", "partial_stats",
            f"No statistics for: {', '.join(stats_missing_centers)}",
            "Active centers without metrics get Missing unit costs — they "
            "are never computed from partial data.",
            "Request the missing centers' figures and replace the stats file.")

    covered = {d.account for d in live(docs, DocType.BANK_STATEMENT.value)}
    for acc in k.active_us_accounts():
        if acc["id"] not in covered:
            gap("material", "missing_input",
                f"US bank statement missing: {acc['name']}",
                "Without it the US cash position is unavailable and Wise "
                "transfers cannot be verified as leaving the US account.",
                f"Add bank_{acc['id']}_{month}.csv to months/{month}/inputs/ "
                "and re-run.")
    for acc in k.active_accounts():
        if acc["id"] not in covered:
            gap("blocking", "missing_input",
                f"Bank statement missing: {acc['name']}",
                "Every active organizational account needs a statement each "
                "month (§6.1); reconciliation for this account is impossible "
                "without it.",
                f"Add bank_{acc['id']}_{month}.csv (or pdf/xlsx) to "
                f"months/{month}/inputs/ and re-run.")

    for d in docs:
        if d.extraction_confidence == "low" and d.superseded_by is None:
            gap("blocking" if d.doc_type in
                (DocType.ACCOUNTING_WORKBOOK.value,
                 DocType.BANK_STATEMENT.value,
                 DocType.CENTER_STATS.value) else "material",
                "unreadable_document",
                f"Unreadable document: {d.file}",
                d.notes or "No machine-readable text/table could be extracted.",
                "Re-upload a text PDF, CSV, or Excel version of this document.")

    if fx_gaps:
        dates = sorted({g["date"] for g in fx_gaps})
        gap("material", "missing_fx_rate",
            f"No NBU rate for {len(dates)} transaction date(s)",
            f"Dates without a usable reference rate (nearest-prior-7-days "
            f"policy): {', '.join(dates)}. USD figures for these are Missing.",
            "Append the missing dates to knowledge/fx_rates.yaml and re-run.")

    # optional documents requested only when they would improve
    # reconciliation (§6.2)
    for card in traces:
        for link in card["links"]:
            if link["step"] == "funding_request" and link["status"] == "missing":
                gap("info", "optional_document",
                    f"Funding request letter for transfer {card['transfer_id']}",
                    "Providing it would upgrade this transfer's chain from "
                    "partial to fully traced.",
                    f"Add the request letter to months/{month}/inputs/ if it exists.")
            if link["step"] == "wise_delivery" and link["status"] == "missing":
                gap("material", "optional_document",
                    f"Wise delivery confirmation for {card['transfer_id']}",
                    "Without it the realized rate and delivery date are "
                    "unverified.",
                    "Download the delivery confirmation from Wise and add it.")

    for d in live(docs):
        if d.doc_type == DocType.UNKNOWN.value:
            gap("info", "unrecognized_file",
                f"Unrecognized file: {d.file}",
                "The file was stored but its type could not be detected, so "
                "it was not processed.",
                f"Add an entry for it to months/{month}/inputs/manifest.yaml "
                "(type: bank_statement|center_stats|wise_transfer|...).")

    order = {"blocking": 0, "material": 1, "info": 2}
    gaps.sort(key=lambda g: (order[g["severity"]], g["title"]))
    return gaps
