"""Financial Oversight Confidence Score (SPEC §11).

Computed, not vibes: every component derives from measurable facts and
the derivation is shown. The rubric lives in knowledge/confidence.yaml.
The score is an aid to the Treasurer's review, not an audit opinion.
"""

from __future__ import annotations

from decimal import Decimal

from .config import Knowledge
from .model import DataStatus, Transaction, money


def score(k: Knowledge, reconciliation: dict, traces: list[dict],
          txns: list[Transaction], operational: dict,
          gaps: list[dict]) -> dict:
    comps = k.confidence["components"]
    parts = {}

    # bank reconciliation: fraction of active accounts fully reconciled
    accounts = reconciliation["accounts"]
    ok = sum(1 for a in accounts if a["reconciled"])
    parts["bank_reconciliation"] = {
        "ratio": ok / len(accounts) if accounts else 0.0,
        "detail": f"{ok}/{len(accounts)} accounts reconciled",
    }

    # transfer matching: share of transfers with confirmed deposit
    if traces:
        confirmed = sum(1 for t in traces if t["deposit_confirmed"])
        parts["transfer_matching"] = {
            "ratio": confirmed / len(traces),
            "detail": f"{confirmed}/{len(traces)} transfers traced to a bank deposit",
        }
    else:
        parts["transfer_matching"] = {"ratio": 1.0,
                                      "detail": "no US transfers this month"}

    # categorization: share of expenses with a non-uncertain category
    expenses = [t for t in txns if t.direction == "expense"]
    if expenses:
        good = sum(1 for t in expenses
                   if t.category and t.category_status != DataStatus.UNCERTAIN.value)
        parts["expense_categorization"] = {
            "ratio": good / len(expenses),
            "detail": f"{good}/{len(expenses)} expenses confidently categorized",
        }
    else:
        parts["expense_categorization"] = {"ratio": 1.0, "detail": "no expenses"}

    # program metrics: share of active centers with statistics
    active = len(k.active_centers())
    missing = len(operational.get("missing_centers", []))
    parts["program_metrics"] = {
        "ratio": (active - missing) / active if active else 1.0,
        "detail": f"{active - missing}/{active} active centers reported metrics",
    }

    # documentation: penalty per open blocking/material gap
    penalty = comps["supporting_documentation"].get("penalty_per_gap", 4)
    doc_gaps = [g for g in gaps if g["severity"] in ("blocking", "material")]
    weight = comps["supporting_documentation"]["weight"]
    doc_score = max(0, weight - penalty * len(doc_gaps))
    parts["supporting_documentation"] = {
        "ratio": doc_score / weight if weight else 1.0,
        "detail": (f"{len(doc_gaps)} open documentation gap(s)"
                   if doc_gaps else "no documentation gaps"),
    }

    total = Decimal("0")
    breakdown = {}
    for name, part in parts.items():
        weight = comps[name]["weight"]
        earned = money(Decimal(str(part["ratio"])) * weight)
        total += earned
        breakdown[name] = {
            "weight": weight,
            "earned": str(earned),
            "status": "ok" if part["ratio"] >= 0.999 else
                      ("warn" if part["ratio"] >= 0.7 else "fail"),
            "detail": part["detail"],
        }

    total_int = int(money(total))
    bands = k.confidence["risk_bands"]
    risk = ("LOW" if total_int >= bands["low"] else
            "MEDIUM" if total_int >= bands["medium"] else "HIGH")
    return {
        "rubric_version": k.confidence.get("version", 1),
        "overall": total_int,
        "risk": risk,
        "components": breakdown,
        "disclaimer": ("This score is an aid to the Treasurer's review, "
                       "not an audit opinion."),
    }
