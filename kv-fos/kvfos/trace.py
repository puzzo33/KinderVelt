"""Stage 4 — funding traceability (SPEC §9 Stage 4).

Every US transfer gets a trace card: each link of the chain is matched,
missing, or mismatched. A break in the chain is a reportable finding,
not a silent gap (SPEC §1.2).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .config import Knowledge
from .model import BankLine, DataStatus, TraceLink, Transaction, money


def _within(a: str, b: str, days: int) -> bool:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= days


def build_traces(k: Knowledge, month: str, wise_transfers: list[dict],
                 funding_requests: list[dict], txns: list[Transaction],
                 lines: list[BankLine]) -> list[dict]:
    tol_pct = k.threshold("transfer_amount_tolerance_pct") / Decimal(100)
    cards = []
    for tr in wise_transfers:
        transfer_id = str(tr.get("transfer_id"))
        usd = money(tr.get("amount_usd"))
        uah = money(tr.get("amount_uah")) if tr.get("amount_uah") else None
        delivered = tr.get("date_delivered") or tr.get("date_sent")
        links: list[TraceLink] = []

        # 1. funding request (optional input; missing != failure, it caps
        #    the link at "missing" and the confidence component notices)
        req = _match_request(funding_requests, usd)
        links.append(TraceLink(
            step="funding_request",
            status="matched" if req else "missing",
            detail=(f"request for ${req['requested_usd']} ({req['file']})"
                    if req else "no funding request letter provided"),
            refs=[{"doc_id": req["doc_id"], "file": req["file"]}] if req else [],
        ))

        # 2. wise confirmation — the transfer record itself
        links.append(TraceLink(
            step="wise_confirmation",
            status="matched",
            detail=f"Wise {transfer_id}: ${usd} sent {tr.get('date_sent')}",
            refs=[tr["_source"].as_dict()] if tr.get("_source") else [],
        ))

        # 3. delivery confirmation
        links.append(TraceLink(
            step="wise_delivery",
            status="matched" if tr.get("date_delivered") else "missing",
            detail=(f"delivered {tr.get('date_delivered')}, "
                    f"₴{uah} at rate {tr.get('rate')}"
                    if tr.get("date_delivered") else
                    "no delivery confirmation"),
        ))

        # 4. deposit visible on the Ukrainian bank statement
        deposit = _find_deposit(lines, uah, delivered, tol_pct)
        links.append(TraceLink(
            step="bank_deposit",
            status="matched" if deposit else "missing",
            detail=(f"₴{deposit.amount_uah} credited {deposit.date} "
                    f"({deposit.account})" if deposit else
                    "no matching credit found on any bank statement"),
            refs=[deposit.source.as_dict()] if deposit and deposit.source else [],
        ))

        # 5. receipt recorded in the books
        ledger_entry = _find_ledger_income(txns, uah, delivered, tol_pct)
        links.append(TraceLink(
            step="ledger_entry",
            status="matched" if ledger_entry else "missing",
            detail=(f"booked ₴{ledger_entry.amount_uah} on {ledger_entry.date}"
                    if ledger_entry else "no matching income entry in ledger"),
            refs=([ledger_entry.source.as_dict()]
                  if ledger_entry and ledger_entry.source else []),
        ))
        if ledger_entry:
            ledger_entry.funding_source = str(
                tr.get("funding_source") or "fokv_general")
            # realized Wise rate takes precedence over reference rate (§9.9)
            if tr.get("rate"):
                ledger_entry.fx_rate = money(tr["rate"])
                ledger_entry.fx_source = f"wise-realized {transfer_id}"
                ledger_entry.amount_usd = usd
                ledger_entry.usd_status = DataStatus.VERIFIED.value

        complete = all(l.status == "matched" for l in links)
        deposited = deposit is not None
        cards.append({
            "transfer_id": transfer_id,
            "month": month,
            "amount_usd": str(usd),
            "amount_uah": str(uah) if uah is not None else None,
            "rate": str(tr.get("rate")) if tr.get("rate") else None,
            "date_sent": tr.get("date_sent"),
            "date_delivered": tr.get("date_delivered"),
            "links": [l.as_dict() for l in links],
            "chain_complete": complete,
            "deposit_confirmed": deposited,
        })
    return cards


def _match_request(requests: list[dict], usd: Decimal) -> dict | None:
    for req in requests:
        if req.get("requested_usd") and money(req["requested_usd"]) >= usd:
            return req
    return None


def _find_deposit(lines: list[BankLine], uah: Decimal | None,
                  delivered: str | None, tol_pct: Decimal) -> BankLine | None:
    if uah is None:
        return None
    for line in lines:
        if line.amount_uah <= 0:
            continue
        if abs(line.amount_uah - uah) <= uah * tol_pct:
            if delivered is None or _within(line.date, delivered, 5):
                return line
    return None


def _find_ledger_income(txns: list[Transaction], uah: Decimal | None,
                        delivered: str | None, tol_pct: Decimal
                        ) -> Transaction | None:
    if uah is None:
        return None
    for t in txns:
        if t.direction != "income":
            continue
        if abs(t.amount_uah - uah) <= uah * tol_pct:
            if delivered is None or _within(t.date, delivered, 5):
                return t
    return None
