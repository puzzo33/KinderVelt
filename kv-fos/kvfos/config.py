"""Knowledge-base loading and validation (SPEC §7).

The knowledge base is plain, versioned YAML under kv-fos/knowledge/.
All thresholds and rubrics are configuration; the pipeline never hardcodes
an org-specific value.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"missing knowledge file: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    return data


def normalize_name(s: str) -> str:
    """Canonical form for vendor-name matching: casefold, strip legal
    prefixes/punctuation, collapse whitespace, normalize unicode."""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = re.sub(r"[\"'«»`’.,;:()]+", " ", s)
    s = re.sub(r"\b(тов|фоп|пп|llc|ltd|inc)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass
class Vendor:
    id: str
    name: str
    translit: str = ""
    aliases: list[str] = field(default_factory=list)
    category: str | None = None
    centers: list[str] = field(default_factory=list)
    recurrence: str | None = None
    classification: str | None = None
    expected_uah: dict | None = None


@dataclass
class Knowledge:
    root: Path
    organization: dict
    centers: list[dict]
    accounts: list[dict]
    us_accounts: list[dict]
    groups: dict
    income_categories: dict
    account_map: dict
    vendors: list[Vendor]
    materiality: dict
    funding_sources: list[dict]
    fx: dict
    confidence: dict
    learned_aliases: list[dict]
    learned_resolutions: list[dict]

    # ---- derived lookup tables ------------------------------------------

    def __post_init__(self):
        self.vendor_by_id = {v.id: v for v in self.vendors}
        self._alias_index: dict[str, str] = {}
        for v in self.vendors:
            for name in [v.name, v.translit, *v.aliases]:
                if name:
                    self._alias_index[normalize_name(name)] = v.id
        for entry in self.learned_aliases:
            self._alias_index[normalize_name(entry["alias"])] = entry["vendor"]
        self.category_group: dict[str, str] = {}
        self.category_label: dict[str, str] = {}
        for gid, g in self.groups.items():
            for cid, label in g.get("categories", {}).items():
                self.category_group[cid] = gid
                self.category_label[cid] = label
        self._fx_dates = sorted(self.fx.get("rates", {}).keys())

    def match_vendor(self, raw_name: str) -> str | None:
        return self._alias_index.get(normalize_name(raw_name))

    def active_centers(self) -> list[dict]:
        return [c for c in self.centers if c.get("active")]

    def active_accounts(self) -> list[dict]:
        return [a for a in self.accounts if a.get("active")]

    def active_us_accounts(self) -> list[dict]:
        return [a for a in self.us_accounts if a.get("active")]

    def threshold(self, key: str) -> Decimal:
        try:
            return Decimal(str(self.materiality["thresholds"][key]))
        except KeyError as e:
            raise ConfigError(f"materiality threshold missing: {key}") from e

    def fx_rate(self, iso_date: str) -> tuple[Decimal, str] | None:
        """NBU rate for a date, falling back to the nearest prior date
        within 7 days (fx_rates.yaml fallback_policy). None => gap."""
        rates = self.fx.get("rates", {})
        if iso_date in rates:
            return Decimal(str(rates[iso_date])), f"NBU {iso_date}"
        d = date.fromisoformat(iso_date)
        for back in range(1, 8):
            prior = (d - timedelta(days=back)).isoformat()
            if prior in rates:
                return Decimal(str(rates[prior])), f"NBU {prior} (nearest prior)"
        return None

    def find_resolution(self, rule: str, *, vendor: str | None = None,
                        month_of_year: int | None = None,
                        account: str | None = None,
                        category: str | None = None) -> dict | None:
        """Return a learned resolution matching this finding, if any."""
        for r in self.learned_resolutions:
            if r.get("rule") != rule:
                continue
            if r.get("vendor") and r["vendor"] != vendor:
                continue
            if r.get("month_of_year") and r["month_of_year"] != month_of_year:
                continue
            if r.get("account") and r["account"] != account:
                continue
            if r.get("category") and r["category"] != category:
                continue
            return r
        return None


def _validate(k: Knowledge) -> None:
    problems = []
    ids = [c["id"] for c in k.centers]
    if len(ids) != len(set(ids)):
        problems.append("duplicate center ids")
    for v in k.vendors:
        if v.category and v.category not in k.category_group:
            problems.append(f"vendor {v.id}: unknown category {v.category}")
        for c in v.centers:
            if c not in ids:
                problems.append(f"vendor {v.id}: unknown center {c}")
    for code, cat in k.account_map.items():
        if cat not in k.category_group:
            problems.append(f"account_map {code}: unknown category {cat}")
    for entry in k.learned_aliases:
        if entry["vendor"] not in k.vendor_by_id:
            problems.append(f"learned alias -> unknown vendor {entry['vendor']}")
    weights = sum(c.get("weight", 0) for c in k.confidence["components"].values())
    if weights != 100:
        problems.append(f"confidence component weights sum to {weights}, expected 100")
    if problems:
        raise ConfigError("knowledge base invalid: " + "; ".join(problems))


def load_knowledge(root: Path) -> Knowledge:
    """root = the kv-fos directory containing knowledge/."""
    kdir = Path(root) / "knowledge"
    org = _load_yaml(kdir / "organization.yaml")
    cats = _load_yaml(kdir / "categories.yaml")
    vendors_raw = _load_yaml(kdir / "vendors.yaml").get("vendors", [])
    learned_dir = kdir / "learned"
    k = Knowledge(
        root=Path(root),
        organization=org.get("organization", {}),
        centers=org.get("centers", []),
        accounts=org.get("accounts", []),
        us_accounts=org.get("us_accounts", []),
        groups=cats.get("groups", {}),
        income_categories=cats.get("income_categories", {}),
        account_map=cats.get("account_map", {}),
        vendors=[Vendor(**v) for v in vendors_raw],
        materiality=_load_yaml(kdir / "materiality.yaml"),
        funding_sources=_load_yaml(kdir / "funding_sources.yaml").get("funding_sources", []),
        fx=_load_yaml(kdir / "fx_rates.yaml"),
        confidence=_load_yaml(kdir / "confidence.yaml"),
        learned_aliases=_load_yaml(learned_dir / "vendor_aliases.yaml").get("aliases", []) or [],
        learned_resolutions=_load_yaml(learned_dir / "resolutions.yaml").get("resolutions", []) or [],
    )
    _validate(k)
    return k
