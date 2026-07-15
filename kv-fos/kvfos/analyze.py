"""Stages 5 & 6 — financial and operational analysis (SPEC §9).

Unit-economics figures are always Estimated (they depend on allocation
rules) and state their method; where a center's metrics are missing its
unit costs are Missing, never computed from partial data (SPEC Stage 6).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .config import Knowledge
from .model import Transaction, money


def _usd(t: Transaction) -> Decimal:
    return t.amount_usd if t.amount_usd is not None else Decimal("0")


def financial_analysis(k: Knowledge, month: str,
                       txns: list[Transaction]) -> dict:
    income = [t for t in txns if t.direction == "income"]
    expenses = [t for t in txns if t.direction == "expense"]

    def total(ts, usd=False):
        if usd:
            return sum((_usd(t) for t in ts), Decimal("0"))
        return sum((abs(t.amount_uah) for t in ts), Decimal("0"))

    by_category: dict[str, dict] = {}
    for t in expenses:
        cat = t.category or "uncategorized"
        agg = by_category.setdefault(cat, {"uah": Decimal("0"), "usd": Decimal("0"),
                                           "count": 0})
        agg["uah"] += abs(t.amount_uah)
        agg["usd"] += _usd(t)
        agg["count"] += 1

    by_group: dict[str, Decimal] = {}
    for cat, agg in by_category.items():
        group = k.category_group.get(cat, "uncategorized")
        by_group[group] = by_group.get(group, Decimal("0")) + agg["uah"]

    by_vendor: dict[str, dict] = {}
    for t in expenses:
        vid = t.vendor_id or f"unknown:{t.vendor_raw or '—'}"
        label = (k.vendor_by_id[t.vendor_id].name if t.vendor_id else
                 (t.vendor_raw or "(no counterparty)"))
        agg = by_vendor.setdefault(vid, {"name": label, "uah": Decimal("0"),
                                         "usd": Decimal("0"), "count": 0})
        agg["uah"] += abs(t.amount_uah)
        agg["usd"] += _usd(t)
        agg["count"] += 1

    by_center: dict[str, Decimal] = {}
    for t in expenses:
        by_center[t.center or "unallocated"] = \
            by_center.get(t.center or "unallocated", Decimal("0")) + abs(t.amount_uah)

    program = by_group.get("program", Decimal("0"))
    admin = by_group.get("administration", Decimal("0"))
    taxes = by_group.get("taxes", Decimal("0"))
    total_exp = total(expenses)

    return {
        "month": month,
        "income_uah": str(total(income)),
        "income_usd": str(total(income, usd=True)),
        "expenses_uah": str(total_exp),
        "expenses_usd": str(total(expenses, usd=True)),
        "net_uah": str(total(income) - total_exp),
        "by_category": {c: {"uah": str(a["uah"]), "usd": str(a["usd"]),
                            "count": a["count"],
                            "label": k.category_label.get(
                                c, k.income_categories.get(c, c))}
                        for c, a in sorted(by_category.items(),
                                           key=lambda kv: -kv[1]["uah"])},
        "by_group": {g: str(v) for g, v in by_group.items()},
        "by_vendor": {v: {"name": a["name"], "uah": str(a["uah"]),
                          "usd": str(a["usd"]), "count": a["count"]}
                      for v, a in sorted(by_vendor.items(),
                                         key=lambda kv: -kv[1]["uah"])},
        "by_center": {c: str(v) for c, v in sorted(by_center.items())},
        "program_uah": str(program),
        "admin_uah": str(admin),
        "taxes_uah": str(taxes),
        "program_share_pct": str(money(program / total_exp * 100)) if total_exp else None,
    }


def operational_analysis(k: Knowledge, month: str, stats_rows: list[dict],
                         financial: dict) -> dict:
    from .config import normalize_name
    centers = {}
    for rec in stats_rows:
        cid = None
        key = normalize_name(str(rec.get("center", "")))
        for c in k.centers:
            if key in (c["id"], normalize_name(c["name"])):
                cid = c["id"]
                break
        centers[cid or str(rec.get("center"))] = {
            "children_served": rec.get("children_served"),
            "consultations": rec.get("consultations"),
            "classes": rec.get("classes"),
            "new_children": rec.get("new_children"),
        }

    missing_centers = [c["id"] for c in k.active_centers()
                       if c["id"] not in centers]

    totals = {m: sum(v[m] or 0 for v in centers.values())
              for m in ("children_served", "consultations", "classes",
                        "new_children")}

    exp = Decimal(financial["expenses_uah"])
    program = Decimal(financial["program_uah"])

    def per(metric):
        n = totals[metric]
        if not n:
            return None
        return str(money(program / n))

    by_center_cost = {}
    fin_by_center = financial["by_center"]
    for cid, m in centers.items():
        cost = fin_by_center.get(cid)
        served = m.get("children_served")
        by_center_cost[cid] = {
            **m,
            "expenses_uah": cost,
            # Missing metrics => Missing unit cost, never partial (§ Stage 6)
            "cost_per_child_uah": (str(money(Decimal(cost) / served))
                                   if cost and served else None),
        }

    return {
        "month": month,
        "totals": totals,
        "centers": by_center_cost,
        "missing_centers": missing_centers,
        # method statement — these are Estimated figures by definition
        "unit_economics": {
            "method": ("program-group expenses divided by metric totals; "
                       "Estimated (allocation-dependent), UAH"),
            "cost_per_child_served_uah": per("children_served"),
            "cost_per_consultation_uah": per("consultations"),
            "cost_per_class_uah": per("classes"),
        },
        "total_expenses_uah": str(exp),
    }


def load_prior_analysis(root: Path, month: str, lookback: int = 12) -> dict[str, dict]:
    """Prior months' financial analyses for trend/variance work."""
    y, m = map(int, month.split("-"))
    out = {}
    for _ in range(lookback):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        prior = f"{y}-{m:02d}"
        path = root / "months" / prior / "derived" / "analysis.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                out[prior] = json.load(f)["financial"]
    return out
