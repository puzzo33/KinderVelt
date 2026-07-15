"""KV-FOS command-line interface.

    python -m kvfos remind              what needs the Treasurer's attention
    python -m kvfos status              state of every month since start
    python -m kvfos init-month 2026-07  create the month folder + checklist
    python -m kvfos close --month M     run the monthly close (idempotent)
    python -m kvfos approve --month M   approve & lock the month
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import lock as lock_mod, pipeline, registry
from .config import load_knowledge


def find_root(start: Path | None = None) -> Path:
    """The kv-fos directory (contains knowledge/)."""
    p = (start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate / "knowledge" / "organization.yaml").exists():
            return candidate
        if (candidate / "kv-fos" / "knowledge" / "organization.yaml").exists():
            return candidate / "kv-fos"
    raise SystemExit("kv-fos root not found (looked for knowledge/organization.yaml)")


def month_status(root: Path, month: str) -> str:
    month_dir = root / "months" / month
    inputs = month_dir / "inputs"
    has_inputs = inputs.exists() and any(
        p for p in inputs.rglob("*")
        if p.is_file() and p.name not in (".gitkeep", "manifest.yaml",
                                          "CHECKLIST.md"))
    derived_docs = month_dir / "derived" / "documents.json"
    if lock_mod.is_locked(month_dir):
        return "approved"
    if not has_inputs:
        return "awaiting_inputs"
    if not derived_docs.exists():
        return "inputs_ready"
    # closed — but stale if inputs changed since the close
    with open(derived_docs, encoding="utf-8") as f:
        closed_hashes = sorted(d["sha256"] for d in json.load(f))
    current = sorted(d.sha256 for d in registry.scan_inputs(month_dir, month))
    return "closed" if current == closed_hashes else "stale_inputs_changed"


def months_since_start(root: Path, today: date | None = None) -> list[str]:
    k = load_knowledge(root)
    start = k.organization.get("start_month", "2026-06")
    today = today or date.today()
    y, m = map(int, start.split("-"))
    out = []
    # every month whose period has fully ended
    while (y, m) < (today.year, today.month):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


STATUS_HINTS = {
    "awaiting_inputs": "⏰ collect the month's documents into inputs/ "
                       "(workbook, bank statements, center stats)",
    "inputs_ready": "▶ inputs present — run `close` to process",
    "stale_inputs_changed": "↻ inputs changed since last close — re-run `close`",
    "closed": "☑ closed — review reports, resolve exceptions, then `approve`",
    "approved": "✓ approved and locked",
}


def cmd_remind(root: Path, args) -> int:
    months = months_since_start(root)
    lines, actionable = [], 0
    for month in months:
        st = month_status(root, month)
        if st != "approved":
            actionable += 1
        lines.append((month, st))
    if args.format == "github-issue":
        # machine-readable block consumed by the reminder workflow
        title = "KV-FOS monthly oversight reminder"
        body = ["It's time for the monthly financial oversight cycle.\n"]
        for month, st in lines:
            body.append(f"- **{month}** — {st}: {STATUS_HINTS[st]}")
        body.append("\nRunbook: `kv-fos/README.md`. Drop the month's files "
                    "into `kv-fos/months/<month>/inputs/` on this branch and "
                    "the process workflow will run the close automatically.")
        print(json.dumps({"title": title, "body": "\n".join(body),
                          "actionable": actionable}))
        return 0
    if not months:
        print("No completed months to oversee yet.")
        return 0
    print("KV-FOS monthly oversight reminder\n")
    for month, st in lines:
        print(f"  {month}  {st:24}  {STATUS_HINTS[st]}")
    return 0 if actionable == 0 else 1


def cmd_status(root: Path, args) -> int:
    for month in months_since_start(root):
        st = month_status(root, month)
        extra = ""
        conf_file = root / "months" / month / "derived" / "confidence.json"
        if conf_file.exists():
            with open(conf_file, encoding="utf-8") as f:
                c = json.load(f)
            extra = f"  confidence {c['overall']}/100 ({c['risk']})"
        print(f"  {month}  {st}{extra}")
    return 0


def cmd_init_month(root: Path, args) -> int:
    month = args.month
    inputs = root / "months" / month / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    checklist = inputs / "CHECKLIST.md"
    if not checklist.exists():
        k = load_knowledge(root)
        accounts = "\n".join(
            f"- [ ] Bank statement: {a['name']} (`bank_{a['id']}_{month}.csv`)"
            for a in k.accounts if a.get("active"))
        checklist.write_text(
            f"# Inputs checklist — {month}\n\n"
            f"Required (SPEC §6.1):\n\n"
            f"- [ ] Accounting workbook (`workbook_{month}.xlsx`)\n{accounts}\n"
            f"- [ ] Center statistics (`CenterUpdates_{month}.pdf`/`.csv`)\n\n"
            f"Optional — add if they exist (SPEC §6.2):\n\n"
            f"- [ ] Wise transfer confirmations (`wise_{month}.csv`)\n"
            f"- [ ] Funding request letters\n- [ ] Invoices / receipts\n",
            encoding="utf-8")
    print(f"initialized {inputs}")
    return 0


def cmd_close(root: Path, args) -> int:
    try:
        summary = pipeline.close_month(root, args.month, amend=args.amend)
    except (pipeline.CloseError, lock_mod.LockError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"Close complete for {summary['month']}"
          f"{' (AMENDMENT)' if summary['amended'] else ''}:")
    print(f"  documents processed : {summary['documents']}")
    print(f"  transactions        : {summary['transactions']}")
    print(f"  bank lines          : {summary['bank_lines']}")
    print(f"  reconciled          : {'yes' if summary['fully_reconciled'] else 'NO'}")
    print(f"  confidence          : {summary['confidence']}/100 ({summary['risk']})")
    print(f"  open exceptions     : {summary['open_exceptions']} "
          f"(+{summary['auto_explained']} auto-explained)")
    print(f"  data gaps           : {summary['gaps_total']} "
          f"({summary['gaps_blocking']} blocking)")
    print(f"  reports             : {summary['reports_dir']}")
    if summary["gaps_blocking"]:
        print(f"\n⚠ blocking gaps — see months/{args.month}/GAPS.md, add the "
              f"missing files and re-run this command (idempotent).")
    if args.strict and (summary["gaps_blocking"] or not summary["fully_reconciled"]):
        return 1
    return 0


def cmd_approve(root: Path, args) -> int:
    try:
        lock = lock_mod.approve(root / "months" / args.month, args.month)
    except lock_mod.LockError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{args.month} approved and locked at {lock['approved_at']}. "
          f"Re-closing now requires --amend.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kvfos",
                                     description="Kinder Velt Financial Oversight System")
    parser.add_argument("--root", type=Path, default=None,
                        help="kv-fos directory (auto-detected by default)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("remind", help="what needs the Treasurer's attention")
    p.add_argument("--format", choices=["text", "github-issue"], default="text")
    p.set_defaults(fn=cmd_remind)

    p = sub.add_parser("status", help="state of every month")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("init-month", help="create a month folder + checklist")
    p.add_argument("month")
    p.set_defaults(fn=cmd_init_month)

    p = sub.add_parser("close", help="run the monthly close (idempotent)")
    p.add_argument("--month", required=True)
    p.add_argument("--amend", action="store_true",
                   help="re-close an approved month as an amendment")
    p.add_argument("--strict", action="store_true",
                   help="nonzero exit on blocking gaps or reconciliation failure")
    p.set_defaults(fn=cmd_close)

    p = sub.add_parser("approve", help="approve & lock a closed month")
    p.add_argument("--month", required=True)
    p.set_defaults(fn=cmd_approve)

    args = parser.parse_args(argv)
    root = args.root or find_root(Path(__file__).parent)
    return args.fn(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
