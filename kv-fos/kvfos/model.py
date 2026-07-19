"""Core data model for KV-FOS.

Every figure the system reports carries a DataStatus (SPEC §4.1) and a
source reference chain (SPEC §10.6). Identifiers are deterministic
functions of content so that reprocessing a month never creates
duplicates (SPEC §9 Stage 1, idempotency).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any


CENT = Decimal("0.01")


def money(value) -> Decimal:
    """Normalize any numeric input to a 2-decimal Decimal."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def digest(*parts: str, length: int = 12) -> str:
    """Deterministic short id from string parts."""
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


class DataStatus(str, Enum):
    """SPEC §4.1 — the four-value data status taxonomy."""

    VERIFIED = "verified"      # matches >= 2 independent sources
    ESTIMATED = "estimated"    # derived by a documented method
    MISSING = "missing"        # expected but absent this month
    UNCERTAIN = "uncertain"    # sources conflict or ambiguous


class DocType(str, Enum):
    ACCOUNTING_WORKBOOK = "accounting_workbook"
    BANK_STATEMENT = "bank_statement"
    CENTER_STATS = "center_stats"
    WISE_TRANSFER = "wise_transfer"
    PLATFORM_EXPORT = "platform_export"   # Zeffy / Stripe / PayPal
    FUNDING_REQUEST = "funding_request"
    INVOICE = "invoice"
    SUPPORTING = "supporting"
    UNKNOWN = "unknown"


REQUIRED_DOC_TYPES = (
    DocType.ACCOUNTING_WORKBOOK,
    DocType.BANK_STATEMENT,
    DocType.CENTER_STATS,
)


@dataclass
class SourceRef:
    """Pointer from a figure back to a location in a source document."""

    doc_id: str
    file: str
    locator: str  # e.g. "sheet=GeneralLedger row=14" or "line=27"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Document:
    doc_id: str          # sha256(file bytes)[:12] — content addressed
    file: str            # path relative to the month inputs dir
    doc_type: str
    month: str           # YYYY-MM the document belongs to
    account: str | None = None   # for bank statements
    sha256: str = ""
    size: int = 0
    extraction_confidence: str = "high"   # high | low (e.g. OCR-needed)
    superseded_by: str | None = None
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Transaction:
    """One normalized ledger transaction (books are the system of record)."""

    txn_id: str
    month: str
    date: str                    # ISO YYYY-MM-DD
    account: str                 # bank/cash account code from the books
    description: str
    vendor_raw: str
    vendor_id: str | None        # canonical vendor, None => unknown vendor
    category: str | None         # leaf category id, None => uncategorized
    category_status: str         # DataStatus for the categorization
    center: str | None
    direction: str               # income | expense
    amount_uah: Decimal
    amount_usd: Decimal | None
    fx_rate: Decimal | None
    fx_source: str | None        # e.g. "NBU 2026-06-12", "wise-realized"
    usd_status: str              # DataStatus of the USD figure
    status: str                  # DataStatus of the transaction itself
    bank_match: str | None = None  # matched bank line id
    funding_source: str | None = None
    invoice_ref: str | None = None
    source: SourceRef | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("amount_uah", "amount_usd", "fx_rate"):
            if d[k] is not None:
                d[k] = str(d[k])
        return d


@dataclass
class BankLine:
    line_id: str
    month: str
    account: str
    date: str
    description: str
    counterparty: str
    amount_uah: Decimal          # signed: credit +, debit -
    balance_after: Decimal | None
    matched_txn: str | None = None
    source: SourceRef | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["amount_uah"] = str(d["amount_uah"])
        if d["balance_after"] is not None:
            d["balance_after"] = str(d["balance_after"])
        return d


@dataclass
class Finding:
    """One exception (SPEC §9 Stage 7, §12). Deterministic id."""

    finding_id: str
    month: str
    rule: str                    # e.g. new_vendor, unmatched_transfer
    severity: str                # high | medium | low
    title: str
    explanation: str             # plain-language why it was flagged
    evidence: list[dict] = field(default_factory=list)
    txn_ids: list[str] = field(default_factory=list)
    status: str = "open"         # open | auto_explained | accepted | escalated
    resolution: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class TraceLink:
    """One link in a transfer's traceability chain (SPEC §9 Stage 4)."""

    step: str                    # funding_request | wise_confirmation | ...
    status: str                  # matched | missing | mismatch
    detail: str = ""
    refs: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def make_txn_id(doc_id: str, date: str, amount: Decimal, counterparty: str,
                description: str, seq: int) -> str:
    """Deterministic transaction id.

    `seq` disambiguates genuinely identical rows within one document while
    keeping re-imports of the same document stable.
    """
    return "T" + digest(doc_id, date, str(amount), counterparty, description, str(seq))


def make_line_id(doc_id: str, date: str, amount: Decimal, description: str,
                 seq: int) -> str:
    return "B" + digest(doc_id, date, str(amount), description, str(seq))


def make_finding_id(month: str, rule: str, key: str) -> str:
    return "X" + digest(month, rule, key)


def jsonable(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    raise TypeError(f"not jsonable: {type(obj)}")
