"""Monthly outputs (SPEC §10).

All reports are generated markdown; every figure that can carry a source
reference does (doc + locator), which is what "clickable" means in the v1
form factor (§10.6). The master register is regenerated from all months'
normalized transactions on every close, so it can never contain dupes.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .config import Knowledge
from .model import Transaction, money

_STATUS_MARK = {"ok": "✓", "warn": "⚠", "fail": "✗"}


def _fmt(uah, usd=None) -> str:
    s = f"₴{money(uah):,}"
    if usd is not None:
        s += f" (~${money(usd):,})"
    return s


def _header(title: str, month: str, k: Knowledge) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (f"# {title} — {month}\n\n"
            f"*{k.organization.get('us_entity', '')} — Financial Oversight "
            f"System. Generated {ts}.*\n\n")


def _open_findings(findings):
    return [f for f in findings if f.status == "open"]


def executive_summary(k, month, fin, conf, findings, gaps) -> str:
    open_f = _open_findings(findings)
    top_cats = list(fin["by_category"].items())[:3]
    lines = [_header("Executive Summary", month, k)]
    lines.append(f"| | UAH | USD |\n|---|---:|---:|\n"
                 f"| Income | ₴{money(fin['income_uah']):,} | ${money(fin['income_usd']):,} |\n"
                 f"| Expenses | ₴{money(fin['expenses_uah']):,} | ${money(fin['expenses_usd']):,} |\n"
                 f"| Net change | ₴{money(fin['net_uah']):,} | |\n")
    lines.append("\n**Largest categories:** " + "; ".join(
        f"{a['label']} ₴{money(a['uah']):,}" for _, a in top_cats) + "\n")
    lines.append(f"\n**Confidence:** {conf['overall']}/100 — risk {conf['risk']}\n")
    if open_f:
        lines.append("\n**Major risks / open questions:**\n")
        for f in open_f[:5]:
            lines.append(f"- {f.title}\n")
        if len(open_f) > 5:
            lines.append(f"- …and {len(open_f) - 5} more (see Treasurer Report)\n")
    else:
        lines.append("\n**Major risks / open questions:** none open.\n")
    blocking = [g for g in gaps if g["severity"] == "blocking"]
    if blocking:
        lines.append(f"\n⚠ **This close is degraded:** {len(blocking)} required "
                     "input(s) missing — see GAPS.md.\n")
    return "".join(lines)


def treasurer_report(k, month, fin, conf, findings, gaps, reconciliation,
                     traces, ops, prior) -> str:
    lines = [_header("Treasurer Report", month, k)]

    # 15-minute path: confidence → exceptions → variances (§10.2)
    lines.append(f"## Confidence: {conf['overall']}/100 — {conf['risk']}\n\n")
    lines.append("| Component | | Detail |\n|---|---|---|\n")
    for name, c in conf["components"].items():
        lines.append(f"| {name.replace('_', ' ').title()} | "
                     f"{_STATUS_MARK[c['status']]} | {c['detail']} "
                     f"({c['earned']}/{c['weight']}) |\n")
    lines.append(f"\n*{conf['disclaimer']}*\n\n")

    open_f = _open_findings(findings)
    auto = [f for f in findings if f.status == "auto_explained"]
    lines.append(f"## Exceptions — {len(open_f)} open"
                 f"{f', {len(auto)} auto-explained' if auto else ''}\n\n")
    for f in open_f:
        lines.append(f"### [{f.severity.upper()}] {f.title}\n\n"
                     f"{f.explanation}\n\n")
        for ev in f.evidence:
            lines.append(f"- source: `{ev.get('file')}` {ev.get('locator', '')} "
                         f"(doc {ev.get('doc_id')})\n")
        if f.txn_ids:
            lines.append(f"- transactions: {', '.join(f.txn_ids)}\n")
        lines.append(f"- finding id: `{f.finding_id}`\n\n")
    for f in auto:
        lines.append(f"- ✓ auto-explained: {f.title} — *{f.resolution}*\n")

    lines.append("\n## Reconciliation\n\n")
    lines.append("| Account | Book opening | Income | Expenses | Computed close "
                 "| Book close | Bank close | Reconciled |\n"
                 "|---|---:|---:|---:|---:|---:|---:|---|\n")
    for a in reconciliation["accounts"]:
        lines.append(
            f"| {a['account']} | {a['book_opening'] or '—'} | {a['income_uah']} "
            f"| {a['expenses_uah']} | {a['computed_closing'] or '—'} "
            f"| {a['book_closing'] or '—'} | {a['bank_closing'] or '—'} "
            f"| {'✓' if a['reconciled'] else '✗'} |\n")
    lines.append(f"\nLedger transactions bank-matched: "
                 f"{reconciliation['txns_bank_matched']}/{reconciliation['txns_total']}; "
                 f"unmatched bank lines: {reconciliation['bank_lines_unmatched']}.\n")

    lines.append("\n## Vendor analysis\n\n| Vendor | UAH | USD | Txns |\n"
                 "|---|---:|---:|---:|\n")
    for _, v in list(fin["by_vendor"].items())[:15]:
        lines.append(f"| {v['name']} | ₴{money(v['uah']):,} "
                     f"| ${money(v['usd']):,} | {v['count']} |\n")

    if prior:
        lines.append("\n## Variance vs prior months\n\n"
                     "| Month | Income UAH | Expenses UAH |\n|---|---:|---:|\n")
        lines.append(f"| **{month}** | ₴{money(fin['income_uah']):,} "
                     f"| ₴{money(fin['expenses_uah']):,} |\n")
        for pm in sorted(prior, reverse=True):
            pf = prior[pm]
            lines.append(f"| {pm} | ₴{money(pf['income_uah']):,} "
                         f"| ₴{money(pf['expenses_uah']):,} |\n")

    lines.append("\n## Operational metrics\n\n")
    t = ops["totals"]
    lines.append(f"- Children served: {t['children_served']}; consultations: "
                 f"{t['consultations']}; classes: {t['classes']}; new children: "
                 f"{t['new_children']}\n")
    ue = ops["unit_economics"]
    lines.append(f"- Cost per child served: ₴{ue['cost_per_child_served_uah'] or '—'}; "
                 f"per consultation: ₴{ue['cost_per_consultation_uah'] or '—'}; "
                 f"per class: ₴{ue['cost_per_class_uah'] or '—'} "
                 f"*(method: {ue['method']})*\n")

    if gaps:
        lines.append(f"\n## Data gaps ({len(gaps)}) — see GAPS.md for actions\n\n")
        for g in gaps:
            lines.append(f"- **[{g['severity']}]** {g['title']}\n")
    lines.append(f"\n*Materiality rules v{k.materiality.get('version')}; "
                 f"confidence rubric v{conf['rubric_version']}.*\n")
    return "".join(lines)


def board_report(k, month, fin, ops, findings) -> str:
    open_f = _open_findings(findings)
    high = [f for f in open_f if f.severity == "high"]
    lines = [_header("Board Report", month, k)]
    lines.append(
        f"- **Income:** {_fmt(fin['income_uah'], fin['income_usd'])}\n"
        f"- **Expenses:** {_fmt(fin['expenses_uah'], fin['expenses_usd'])}\n"
        f"- **Net change in cash:** ₴{money(fin['net_uah']):,}\n"
        f"- **Program share of spending:** "
        f"{fin['program_share_pct'] or '—'}%\n\n")
    t = ops["totals"]
    lines.append("## Program highlights\n\n"
                 f"Across our centers this month we served "
                 f"**{t['children_served']} children**, held "
                 f"**{t['consultations']} parent consultations** and ran "
                 f"**{t['classes']} classes**; **{t['new_children']} new "
                 f"children** joined the program.\n\n")
    lines.append("## Financial risks\n\n")
    if high:
        for f in high:
            lines.append(f"- {f.title}\n")
    else:
        lines.append("No high-severity financial risks are open this month.\n")
    return "".join(lines)


def donor_report(k, month, fin, ops) -> str:
    """Public-facing; aggregate figures only (SPEC §8, §10.4). The
    narrative is a draft for the Treasurer to edit — never auto-published."""
    lines = [_header("Transparency Report (DRAFT — for Treasurer review)",
                     month, k)]
    program = money(fin["program_uah"])
    admin = money(fin["admin_uah"]) + money(fin["taxes_uah"])
    lines.append(
        f"- **Donations put to work:** {_fmt(fin['expenses_uah'], fin['expenses_usd'])}\n"
        f"- **Program spending:** ₴{program:,}\n"
        f"- **Administrative spending (incl. taxes):** ₴{admin:,}\n\n")
    lines.append("## Where the money went\n\n| Category | UAH |\n|---|---:|\n")
    for cid, a in list(fin["by_category"].items())[:6]:
        lines.append(f"| {a['label']} | ₴{money(a['uah']):,} |\n")
    t = ops["totals"]
    lines.append(f"\n## Your impact\n\n"
                 f"- **{t['children_served']}** children served\n"
                 f"- **{t['consultations']}** parent consultations\n"
                 f"- **{t['classes']}** classes conducted\n"
                 f"- **{t['new_children']}** new children welcomed\n\n")
    lines.append("## Narrative (draft)\n\n"
                 f"In {month}, thanks to our donors, Kinder Velt's centers "
                 f"continued to provide psychological support and education "
                 f"to children affected by the war. "
                 f"{fin['program_share_pct'] or '—'}% of spending went "
                 f"directly to programs.\n\n"
                 "*[Treasurer: edit this narrative before publication.]*\n")
    return "".join(lines)


def trace_cards_md(k, month, traces) -> str:
    lines = [_header("Transfer Trace Cards", month, k)]
    if not traces:
        lines.append("No US transfers recorded this month.\n")
    for card in traces:
        state = "✅ complete" if card["chain_complete"] else "⚠ incomplete"
        lines.append(f"## Transfer {card['transfer_id']} — "
                     f"${card['amount_usd']} ({state})\n\n")
        for link in card["links"]:
            mark = {"matched": "✓", "missing": "✗", "mismatch": "⚠"}[link["status"]]
            lines.append(f"- {mark} **{link['step'].replace('_', ' ')}** — "
                         f"{link['detail']}\n")
            for ref in link.get("refs", []):
                loc = f" {ref.get('locator')}" if ref.get("locator") else ""
                lines.append(f"    - source: `{ref.get('file')}`{loc}\n")
        lines.append("\n")
    return "".join(lines)


def gaps_md(k, month, gaps) -> str:
    lines = [_header("Data Gaps & Re-upload Instructions", month, k)]
    if not gaps:
        lines.append("No data gaps — all required inputs present and readable.\n")
        return "".join(lines)
    lines.append("Fix any item below by adding/replacing the file in "
                 f"`months/{month}/inputs/` and re-running "
                 f"`python -m kvfos close --month {month}`. Reprocessing is "
                 "idempotent — replaced files supersede, nothing duplicates.\n\n")
    for g in gaps:
        lines.append(f"## [{g['severity'].upper()}] {g['title']}\n\n"
                     f"{g['detail']}\n\n**Action:** {g['action']}\n\n")
    return "".join(lines)


REGISTER_FIELDS = ["month", "date", "txn_id", "account", "direction",
                   "vendor", "vendor_id", "category", "center", "amount_uah",
                   "amount_usd", "fx_source", "funding_source", "status",
                   "usd_status", "invoice_ref", "source_file", "source_locator",
                   "doc_id"]


def rebuild_master_register(k: Knowledge, root: Path) -> Path:
    """Regenerate the cumulative register from every month's normalized
    transactions (SPEC §10.5). Full rebuild => structurally dupe-free."""
    reg_dir = root / "registry"
    reg_dir.mkdir(parents=True, exist_ok=True)
    out = reg_dir / "master_register.csv"
    rows = []
    for txn_file in sorted((root / "months").glob("*/derived/transactions.jsonl")):
        with open(txn_file, encoding="utf-8") as f:
            for line in f:
                t = json.loads(line)
                src = t.get("source") or {}
                rows.append({
                    "month": t["month"], "date": t["date"],
                    "txn_id": t["txn_id"], "account": t["account"],
                    "direction": t["direction"],
                    "vendor": (k.vendor_by_id[t["vendor_id"]].name
                               if t.get("vendor_id") in k.vendor_by_id
                               else t.get("vendor_raw", "")),
                    "vendor_id": t.get("vendor_id") or "",
                    "category": t.get("category") or "",
                    "center": t.get("center") or "",
                    "amount_uah": t["amount_uah"],
                    "amount_usd": t.get("amount_usd") or "",
                    "fx_source": t.get("fx_source") or "",
                    "funding_source": t.get("funding_source") or "",
                    "status": t["status"], "usd_status": t["usd_status"],
                    "invoice_ref": t.get("invoice_ref") or "",
                    "source_file": src.get("file", ""),
                    "source_locator": src.get("locator", ""),
                    "doc_id": src.get("doc_id", ""),
                })
    rows.sort(key=lambda r: (r["month"], r["date"], r["txn_id"]))
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REGISTER_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return out
