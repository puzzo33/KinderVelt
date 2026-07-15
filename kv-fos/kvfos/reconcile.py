"""Stage 3 — reconciliation (SPEC §9 Stage 3).

Three-way comparison: accounting records vs bank statements vs prior
month's verified closing balances. Ledger transactions matched to bank
lines are upgraded to Verified (two independent sources, SPEC §4.1).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .config import Knowledge
from .model import BankLine, DataStatus, Transaction, money


def match_bank(k: Knowledge, txns: list[Transaction],
               lines: list[BankLine]) -> None:
    """Greedy 1:1 matching: same account, equal amount, dates within the
    configured window. Mutates txn.status/bank_match and line.matched_txn."""
    window = int(k.threshold("bank_match_window_days"))
    unmatched_lines = [l for l in lines if l.matched_txn is None]
    by_key: dict[tuple, list[BankLine]] = {}
    for l in unmatched_lines:
        by_key.setdefault((l.account, str(l.amount_uah)), []).append(l)

    for txn in sorted(txns, key=lambda t: (t.date, t.txn_id)):
        if txn.bank_match:
            continue
        candidates = by_key.get((txn.account, str(txn.amount_uah)), [])
        best = None
        t_date = date.fromisoformat(txn.date)
        for line in candidates:
            if line.matched_txn:
                continue
            delta = abs((date.fromisoformat(line.date) - t_date).days)
            if delta <= window and (best is None or delta < best[0]):
                best = (delta, line)
        if best:
            line = best[1]
            line.matched_txn = txn.txn_id
            txn.bank_match = line.line_id
            txn.status = DataStatus.VERIFIED.value


def _prior_closing(root: Path, month: str, account: str) -> Decimal | None:
    """Verified closing balance for this account from the prior month's
    reconciliation output, if that month was processed."""
    y, m = map(int, month.split("-"))
    prior = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
    path = root / "months" / prior / "derived" / "reconciliation.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    for acc in rec.get("accounts", []):
        if acc["account"] == account and acc.get("bank_closing") is not None:
            return money(acc["bank_closing"])
    return None


def reconcile(k: Knowledge, root: Path, month: str,
              txns: list[Transaction], lines: list[BankLine],
              book_balances: list[dict]) -> dict:
    """Per-account and total reconciliation. Returns a JSON-able dict;
    breaks become exceptions downstream."""
    tol = k.threshold("reconciliation_tolerance_uah")
    books = {}
    for b in book_balances:
        acct = str(b.get("bank_account") or "").strip().lower()
        books[acct] = b

    accounts_out = []
    for account in sorted({a["id"] for a in k.active_accounts()}):
        acct_txns = [t for t in txns if t.account == account]
        acct_lines = [l for l in lines if l.account == account]

        book = books.get(account, {})
        book_opening = book.get("opening_uah")
        book_closing = book.get("closing_uah")

        income = sum((t.amount_uah for t in acct_txns if t.direction == "income"),
                     Decimal("0"))
        expenses = sum((t.amount_uah for t in acct_txns if t.direction == "expense"),
                       Decimal("0"))
        computed_closing = (money(book_opening) + income + expenses
                            if book_opening is not None else None)

        bank_closing = None
        if acct_lines:
            last = max(acct_lines, key=lambda l: (l.date, l.line_id))
            bank_closing = last.balance_after

        prior_closing = _prior_closing(root, month, account)

        breaks = []
        if book_opening is not None and prior_closing is not None and \
                abs(money(book_opening) - prior_closing) > tol:
            breaks.append({
                "kind": "opening_vs_prior_close",
                "book_opening": str(money(book_opening)),
                "prior_bank_closing": str(prior_closing),
            })
        if computed_closing is not None and book_closing is not None and \
                abs(computed_closing - money(book_closing)) > tol:
            breaks.append({
                "kind": "ledger_vs_book_closing",
                "computed_closing": str(computed_closing),
                "book_closing": str(money(book_closing)),
            })
        if book_closing is not None and bank_closing is not None and \
                abs(money(book_closing) - bank_closing) > tol:
            breaks.append({
                "kind": "book_vs_bank_closing",
                "book_closing": str(money(book_closing)),
                "bank_closing": str(bank_closing),
            })

        accounts_out.append({
            "account": account,
            "book_opening": str(money(book_opening)) if book_opening is not None else None,
            "income_uah": str(income),
            "expenses_uah": str(expenses),
            "computed_closing": str(computed_closing) if computed_closing is not None else None,
            "book_closing": str(money(book_closing)) if book_closing is not None else None,
            "bank_closing": str(bank_closing) if bank_closing is not None else None,
            "prior_bank_closing": str(prior_closing) if prior_closing is not None else None,
            "statement_present": bool(acct_lines),
            "reconciled": not breaks and bool(acct_lines) and book_closing is not None,
            "breaks": breaks,
        })

    matched = sum(1 for t in txns if t.bank_match)
    return {
        "month": month,
        "tolerance_uah": str(tol),
        "accounts": accounts_out,
        "txns_total": len(txns),
        "txns_bank_matched": matched,
        "bank_lines_total": len(lines),
        "bank_lines_unmatched": sum(1 for l in lines if not l.matched_txn),
        "fully_reconciled": all(a["reconciled"] for a in accounts_out),
    }
