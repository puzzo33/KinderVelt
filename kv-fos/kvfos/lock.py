"""Month approval, locking and amendments (SPEC §9.8).

Approving a month freezes its input hashes and headline figures. A locked
month is never edited in place: re-closing it requires --amend, which
produces a delta report against the locked figures. Both versions remain
in history (the store is git-versioned).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .model import money

LOCK_FILE = "approved.lock.json"


class LockError(Exception):
    pass


def lock_path(month_dir: Path) -> Path:
    return month_dir / LOCK_FILE


def is_locked(month_dir: Path) -> bool:
    return lock_path(month_dir).exists()


def read_lock(month_dir: Path) -> dict:
    with open(lock_path(month_dir), encoding="utf-8") as f:
        return json.load(f)


def approve(month_dir: Path, month: str) -> dict:
    """Approve the month: requires a completed close with no blocking gaps."""
    derived = month_dir / "derived"
    analysis = derived / "analysis.json"
    gaps_file = derived / "gaps.json"
    if not analysis.exists():
        raise LockError(f"{month}: no completed close to approve — run "
                        f"`close --month {month}` first")
    with open(gaps_file, encoding="utf-8") as f:
        gaps = json.load(f)
    blocking = [g for g in gaps if g["severity"] == "blocking"]
    if blocking:
        raise LockError(
            f"{month}: cannot approve with {len(blocking)} blocking gap(s): "
            + "; ".join(g["title"] for g in blocking))

    with open(analysis, encoding="utf-8") as f:
        fin = json.load(f)["financial"]
    docs = json.load(open(derived / "documents.json", encoding="utf-8"))
    lock = {
        "month": month,
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approved_by": "treasurer",
        "input_hashes": sorted(d["sha256"] for d in docs
                               if d.get("superseded_by") is None),
        "figures": {
            "income_uah": fin["income_uah"],
            "expenses_uah": fin["expenses_uah"],
            "net_uah": fin["net_uah"],
            "by_category": {c: a["uah"] for c, a in fin["by_category"].items()},
        },
    }
    with open(lock_path(month_dir), "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2)
    return lock


def amendment_report(month_dir: Path, month: str) -> str:
    """After an --amend close of a locked month, report deltas vs the
    approved figures."""
    lock = read_lock(month_dir)
    with open(month_dir / "derived" / "analysis.json", encoding="utf-8") as f:
        fin = json.load(f)["financial"]
    old, new = lock["figures"], fin
    lines = [f"# Amendment Report — {month}\n\n"
             f"Approved on {lock['approved_at']}; the figures below were "
             f"restated by a re-import (SPEC §9.8). Both versions remain in "
             f"history.\n\n",
             "| Figure | Approved | Amended | Δ |\n|---|---:|---:|---:|\n"]
    for key, label in (("income_uah", "Income UAH"),
                       ("expenses_uah", "Expenses UAH"),
                       ("net_uah", "Net UAH")):
        a, b = money(old[key]), money(new[key])
        lines.append(f"| {label} | ₴{a:,} | ₴{b:,} | ₴{b - a:,} |\n")
    old_cats = old["by_category"]
    new_cats = {c: a["uah"] for c, a in new["by_category"].items()}
    for cat in sorted(set(old_cats) | set(new_cats)):
        a = money(old_cats.get(cat, "0"))
        b = money(new_cats.get(cat, "0"))
        if a != b:
            lines.append(f"| category: {cat} | ₴{a:,} | ₴{b:,} | ₴{b - a:,} |\n")
    return "".join(lines)
