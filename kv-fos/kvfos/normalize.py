"""Stage 2 — normalization (SPEC §9 Stage 2).

Ledger rows become Transactions; bank rows become BankLines. The books
are the system of record: the master register is built from the ledger,
while bank lines are used for reconciliation — merging the two would
create duplicates by design, so we never do it.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .config import Knowledge, normalize_name
from .model import (BankLine, DataStatus, SourceRef, Transaction,
                    make_line_id, make_txn_id, money)


def _center_id(k: Knowledge, raw) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    key = normalize_name(str(raw))
    for c in k.centers:
        if key in (c["id"], normalize_name(c["name"])):
            return c["id"]
    return None


def _account_id(k: Knowledge, raw) -> str:
    if raw is None:
        return "unknown"
    key = str(raw).strip().lower()
    for a in k.accounts:
        if key in (a["id"], a["name"].lower()):
            return a["id"]
    return key


def categorize(k: Knowledge, vendor_id: str | None, account_code: str | None,
               direction: str, description: str) -> tuple[str | None, str]:
    """Category resolution order (SPEC §9 Stage 2): accountant's chart
    mapping -> vendor default -> income heuristics -> uncertain."""
    if account_code and str(account_code).strip() in k.account_map:
        return k.account_map[str(account_code).strip()], DataStatus.VERIFIED.value
    if vendor_id and k.vendor_by_id[vendor_id].category:
        return k.vendor_by_id[vendor_id].category, DataStatus.ESTIMATED.value
    if direction == "income":
        text = normalize_name(description)
        if any(w in text for w in ("wise", "kinder velt usa", "friends of")):
            return "us_transfer", DataStatus.ESTIMATED.value
        return "other_income", DataStatus.UNCERTAIN.value
    return None, DataStatus.UNCERTAIN.value


def normalize_ledger(k: Knowledge, month: str, ledger_rows: list[dict]
                     ) -> tuple[list[Transaction], list[dict]]:
    """Returns (transactions, fx_gaps). fx_gaps are dates with no usable
    reference rate — the USD figure for those is left Missing, never
    silently interpolated (SPEC §4.1)."""
    txns: list[Transaction] = []
    fx_gaps: list[dict] = []
    seq: Counter = Counter()
    for rec in ledger_rows:
        src: SourceRef = rec["_source"]
        amount = rec["amount_uah"]
        if amount is None:
            continue
        counterparty = str(rec.get("counterparty") or "").strip()
        description = str(rec.get("description") or "").strip()
        direction = "income" if amount > 0 else "expense"
        key = (src.doc_id, rec["date"], str(amount), counterparty, description)
        seq[key] += 1
        txn_id = make_txn_id(src.doc_id, rec["date"], amount, counterparty,
                             description, seq[key])

        vendor_id = k.match_vendor(counterparty) if counterparty else None
        category, cat_status = categorize(
            k, vendor_id, rec.get("account_code"), direction, description)

        fx = k.fx_rate(rec["date"])
        if fx:
            rate, fx_source = fx
            amount_usd = money(abs(amount) / rate)
            usd_status = DataStatus.ESTIMATED.value
        else:
            rate, fx_source, amount_usd = None, None, None
            usd_status = DataStatus.MISSING.value
            fx_gaps.append({"date": rec["date"], "txn_id": txn_id})

        txns.append(Transaction(
            txn_id=txn_id,
            month=month,
            date=rec["date"],
            account=_account_id(k, rec.get("bank_account")),
            description=description,
            vendor_raw=counterparty,
            vendor_id=vendor_id,
            category=category,
            category_status=cat_status,
            center=_center_id(k, rec.get("center")),
            direction=direction,
            amount_uah=money(amount),
            amount_usd=amount_usd,
            fx_rate=rate,
            fx_source=fx_source,
            usd_status=usd_status,
            status=DataStatus.UNCERTAIN.value,  # upgraded on bank match
            invoice_ref=(str(rec["invoice_ref"]).strip()
                         if rec.get("invoice_ref") else None),
            source=src,
        ))
    return txns, fx_gaps


def normalize_bank(k: Knowledge, month: str, account: str,
                   bank_rows: list[dict]) -> list[BankLine]:
    lines: list[BankLine] = []
    seq: Counter = Counter()
    for rec in bank_rows:
        src: SourceRef = rec["_source"]
        amount = rec["amount_uah"]
        if amount is None:
            continue
        description = str(rec.get("description") or "").strip()
        key = (src.doc_id, rec["date"], str(amount), description)
        seq[key] += 1
        lines.append(BankLine(
            line_id=make_line_id(src.doc_id, rec["date"], amount,
                                 description, seq[key]),
            month=month,
            account=account,
            date=rec["date"],
            description=description,
            counterparty=str(rec.get("counterparty") or "").strip(),
            amount_uah=money(amount),
            balance_after=rec.get("balance"),
            source=src,
        ))
    return lines
