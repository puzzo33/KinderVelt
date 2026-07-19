"""Stage 7 — exception analysis (SPEC §9 Stage 7, §12).

Every finding carries a plain-language explanation and evidence refs.
Findings matching a learned resolution (knowledge/learned/resolutions.yaml)
are auto-explained instead of re-flagged — the memory paying off (§7.6).
Finding ids are deterministic so reprocessing never duplicates them.
"""

from __future__ import annotations

from decimal import Decimal

from .config import Knowledge
from .model import (BankLine, DataStatus, Finding, Transaction,
                    make_finding_id, money)

_CASH_WORDS = ("готівк", "зняття", "cash withdrawal", "atm")


def detect(k: Knowledge, month: str, txns: list[Transaction],
           lines: list[BankLine], reconciliation: dict, traces: list[dict],
           payroll_rows: list[dict], prior: dict[str, dict],
           gaps: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    add = findings.append
    month_of_year = int(month.split("-")[1])

    def finding(rule, key, severity, title, explanation, evidence=(), txn_ids=(),
                vendor=None, account=None, category=None):
        f = Finding(
            finding_id=make_finding_id(month, rule, key),
            month=month, rule=rule, severity=severity, title=title,
            explanation=explanation, evidence=list(evidence),
            txn_ids=list(txn_ids), vendor=vendor,
        )
        res = k.find_resolution(rule, vendor=vendor, month_of_year=month_of_year,
                                account=account, category=category)
        if res:
            f.status = "auto_explained"
            f.resolution = res["explanation"]
        add(f)

    usd_limit = k.threshold("single_expense_usd")

    seen_payment_keys: dict[tuple, Transaction] = {}
    for t in txns:
        ev = [t.source.as_dict()] if t.source else []

        # unknown / new vendor (always flag, §7.5)
        if t.direction == "expense" and t.vendor_id is None:
            rule = "new_vendor" if t.vendor_raw else "unknown_expense"
            finding(rule, t.txn_id, "medium",
                    f"{'New vendor' if t.vendor_raw else 'Expense without counterparty'}: "
                    f"{t.vendor_raw or t.description or '—'}",
                    (f"Counterparty “{t.vendor_raw}” is not in the vendor master "
                     f"or learned aliases. Confirm who this is; confirming adds "
                     f"an alias so it is never asked again."
                     if t.vendor_raw else
                     "Ledger expense has no counterparty and no category source."),
                    ev, [t.txn_id])

        # large single expense (materiality §7.5)
        if t.direction == "expense" and t.amount_usd is not None \
                and t.amount_usd > usd_limit:
            finding("large_one_time_expense", t.txn_id, "medium",
                    f"Large expense ${t.amount_usd} — {t.vendor_raw or t.description}",
                    f"Single expense of ₴{abs(t.amount_uah)} (~${t.amount_usd}) "
                    f"exceeds the ${usd_limit} materiality threshold.",
                    ev, [t.txn_id], vendor=t.vendor_id, category=t.category)

        # duplicate payment (always flag)
        dkey = (t.date, str(t.amount_uah), t.vendor_raw.lower())
        if t.direction == "expense" and t.vendor_raw:
            if dkey in seen_payment_keys:
                first = seen_payment_keys[dkey]
                finding("duplicate_payment", t.txn_id, "high",
                        f"Possible duplicate payment to {t.vendor_raw}",
                        f"Two payments of ₴{abs(t.amount_uah)} to "
                        f"“{t.vendor_raw}” on {t.date}. Verify one is not an "
                        f"accidental double payment.",
                        ev + ([first.source.as_dict()] if first.source else []),
                        [t.txn_id, first.txn_id], vendor=t.vendor_id)
            else:
                seen_payment_keys[dkey] = t

        # expense outside vendor's learned expected range
        if t.direction == "expense" and t.vendor_id:
            v = k.vendor_by_id[t.vendor_id]
            if v.expected_uah:
                lo, hi = money(v.expected_uah["min"]), money(v.expected_uah["max"])
                if not (lo <= abs(t.amount_uah) <= hi):
                    finding("amount_outside_baseline", t.txn_id, "low",
                            f"{v.name}: ₴{abs(t.amount_uah)} outside expected "
                            f"₴{lo}–₴{hi}",
                            "Amount is outside this vendor's learned baseline "
                            "range; verify the invoice.",
                            ev, [t.txn_id], vendor=t.vendor_id)

    # cash withdrawals (always flag) — detected on bank lines
    for line in lines:
        text = f"{line.description} {line.counterparty}".lower()
        if line.amount_uah < 0 and any(w in text for w in _CASH_WORDS):
            finding("cash_withdrawal", line.line_id, "high",
                    f"Cash withdrawal ₴{abs(line.amount_uah)} on {line.date}",
                    "Cash withdrawals are always flagged (§7.5): confirm the "
                    "cash purpose and supporting documentation.",
                    [line.source.as_dict()] if line.source else [], [])

    # unmatched bank lines (always flag)
    for line in lines:
        if line.matched_txn is None:
            finding("unmatched_bank_transaction", line.line_id, "high",
                    f"Bank {line.account}: ₴{line.amount_uah} on {line.date} "
                    f"not in the books",
                    f"“{line.description or line.counterparty}” appears on the "
                    f"bank statement but no ledger entry matches it (amount + "
                    f"date window {int(k.threshold('bank_match_window_days'))}d). "
                    "Ask the accountant to book or explain it.",
                    [line.source.as_dict()] if line.source else [],
                    account=line.account)

    # ledger entries with no bank movement
    for t in txns:
        if t.bank_match is None and t.account != "unknown":
            finding("ledger_entry_without_bank_movement", t.txn_id, "medium",
                    f"Booked ₴{t.amount_uah} ({t.vendor_raw or t.description}) "
                    f"has no bank movement",
                    "Ledger entry not found on any bank statement — possibly "
                    "an accrual, a cash transaction, or an accounting error.",
                    [t.source.as_dict()] if t.source else [], [t.txn_id],
                    vendor=t.vendor_id)

    # reconciliation breaks
    for acc in reconciliation["accounts"]:
        for br in acc["breaks"]:
            finding("reconciliation_break", f"{acc['account']}:{br['kind']}",
                    "high",
                    f"Reconciliation break on {acc['account']}: {br['kind']}",
                    f"Balances disagree beyond the ₴{reconciliation['tolerance_uah']} "
                    f"tolerance: {br}.", [], account=acc["account"])
        if not acc["statement_present"]:
            finding("missing_bank_statement", acc["account"], "high",
                    f"No bank statement for {acc['account']}",
                    "Every active account requires a statement each month "
                    "(§6.1). Upload it and re-run the close.",
                    account=acc["account"])

    # unmatched transfers (always flag)
    for card in traces:
        if not card["deposit_confirmed"]:
            finding("unmatched_transfer", card["transfer_id"], "high",
                    f"US transfer {card['transfer_id']} (${card['amount_usd']}) "
                    f"not confirmed in Ukrainian bank",
                    "The Wise transfer could not be matched to a deposit on any "
                    "bank statement. Verify receipt.", [])

    # payroll / category variance vs prior month (materiality §7.5)
    if prior:
        latest_prior = sorted(prior)[-1]
        _variance_findings(k, month, txns, prior[latest_prior],
                           latest_prior, finding)

    # missing invoice on material expenses (always flag)
    for t in txns:
        if t.direction == "expense" and t.amount_usd is not None \
                and t.amount_usd > usd_limit and not t.invoice_ref:
            finding("missing_invoice", t.txn_id, "medium",
                    f"No invoice reference for ${t.amount_usd} expense "
                    f"({t.vendor_raw or t.description})",
                    "Material expense lacks an invoice/document reference in "
                    "the ledger; request the document.",
                    [t.source.as_dict()] if t.source else [], [t.txn_id],
                    vendor=t.vendor_id)

    # data gaps that the treasurer must act on also surface as findings
    for g in gaps:
        if g["severity"] == "blocking":
            finding("missing_required_input", g["gap_id"], "high",
                    g["title"], g["detail"], [])

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order[f.severity], f.rule, f.finding_id))
    return findings


def _variance_findings(k: Knowledge, month, txns, prior_fin, prior_month, finding):
    cur: dict[str, Decimal] = {}
    for t in txns:
        if t.direction == "expense" and t.category:
            cur[t.category] = cur.get(t.category, Decimal("0")) + abs(t.amount_uah)
    prior_by_cat = {c: Decimal(a["uah"]) for c, a in
                    prior_fin.get("by_category", {}).items()}

    checks = [
        ("rent", "rent_change_pct", "rent_variance"),
        ("utilities", "utility_change_pct", "utility_variance"),
    ]
    payroll_cats = ("psychologist_salaries", "therapists", "program_staff")
    cur_payroll = sum((cur.get(c, Decimal("0")) for c in payroll_cats), Decimal("0"))
    prior_payroll = sum((prior_by_cat.get(c, Decimal("0")) for c in payroll_cats),
                        Decimal("0"))
    if prior_payroll > 0:
        pct = abs(cur_payroll - prior_payroll) / prior_payroll * 100
        if pct > k.threshold("payroll_change_pct"):
            finding("payroll_change", "payroll", "high",
                    f"Payroll changed {money(pct)}% vs {prior_month}",
                    f"Payroll categories total ₴{cur_payroll} vs "
                    f"₴{prior_payroll} in {prior_month}; threshold is "
                    f"{k.threshold('payroll_change_pct')}%.", [])

    for cat, threshold_key, rule in checks:
        prior_amt = prior_by_cat.get(cat, Decimal("0"))
        if prior_amt > 0:
            cur_amt = cur.get(cat, Decimal("0"))
            pct = abs(cur_amt - prior_amt) / prior_amt * 100
            if pct > k.threshold(threshold_key):
                finding(rule, cat, "medium",
                        f"{k.category_label.get(cat, cat)} changed "
                        f"{money(pct)}% vs {prior_month}",
                        f"₴{cur_amt} vs ₴{prior_amt} in {prior_month}; "
                        f"threshold is {k.threshold(threshold_key)}%.",
                        [], category=cat)
