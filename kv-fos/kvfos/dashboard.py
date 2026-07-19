"""Treasurer Console — self-contained HTML dashboard generator.

Renders the orchestration + analytics console from the repo's current
state. One static HTML file: inline CSS/SVG, no external requests, both
themes, treasurer-level detail (SPEC §8).

Product rules (Treasurer feedback, July 2026):
* Everything happens DIRECTLY from the portal. Actions call the
  viewer's claude.ai **GitHub connector** (window.claude.mcp) and commit
  straight to the repository: uploads land in the month's inputs folder,
  accepts write one small knowledge file each, approvals write a marker
  — and the repo's process workflow reruns the close automatically.
  Create-only commits with unique names keep every action conflict-free.
* If the GitHub connection isn't available, each action explains exactly
  how to enable it (per error code) — never a generic failure.
* No technical language on the page; USD default with a global ₴ toggle;
  entity tabs; mobile friendly; every month row carries its next step.

Regenerate any time with:  python -m kvfos dashboard
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from .config import Knowledge, load_knowledge
from .model import money

E = html.escape


# ---------------------------------------------------------------------------
# data gathering

def _j(path: Path):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return out or None
    except Exception:
        return None


def _repo_info(root: Path) -> dict:
    url = _git(root, "remote", "get-url", "origin") or ""
    m = re.search(r"[/:]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":  # detached (CI)
        branch = None
    return {"owner": m.group(1) if m else None,
            "repo": m.group(2) if m else None,
            "branch": branch or "claude/kinder-velt-fos-spec-s6clsr"}


def gather(root: Path, today: date | None = None) -> dict:
    from .cli import month_status, months_since_start
    k = load_knowledge(root)
    today = today or date.today()
    months = []
    for m in months_since_start(root, today):
        d = root / "months" / m / "derived"
        months.append({
            "month": m,
            "status": month_status(root, m),
            "confidence": _j(d / "confidence.json"),
            "exceptions": _j(d / "exceptions.json") or [],
            "gaps": _j(d / "gaps.json") or [],
            "analysis": _j(d / "analysis.json"),
            "reconciliation": _j(d / "reconciliation.json"),
            "traces": _j(d / "traces.json") or [],
            "us_lines": _jsonl(d / "us_lines.jsonl"),
            "platforms": _j(d / "platforms.json") or {},
        })
    return {
        "k": k, "months": months, "today": today.isoformat(),
        "current_period": f"{today.year}-{today.month:02d}",
        "commit": _git(root, "rev-parse", "--short", "HEAD"),
        "repo": _repo_info(root),
        "generated": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
    }


def month_name(m: str) -> str:
    return datetime.strptime(m + "-01", "%Y-%m-%d").strftime("%B %Y")


# ---------------------------------------------------------------------------
# currency-aware formatting (USD default, global ₴ toggle)

def _usd_s(v) -> str:
    return f"${money(v):,.0f}"


def _uah_s(v) -> str:
    return f"₴{money(v):,.0f}"


def pair(usd, uah, cls: str = "") -> str:
    u = _usd_s(usd) if usd is not None else "—"
    h = _uah_s(uah) if uah is not None else "—"
    return (f'<span class="money {cls}" data-usd="{E(u)}" '
            f'data-uah="{E(h)}">{E(u)}</span>')


def tip_pair(prefix: str, usd, uah, suffix: str = "") -> str:
    u = _usd_s(usd) if usd is not None else "—"
    h = _uah_s(uah) if uah is not None else "—"
    return (f'data-tip-usd="{E(prefix + u + suffix)}" '
            f'data-tip-uah="{E(prefix + h + suffix)}"')


def _month_fx(k: Knowledge, m: str) -> Decimal | None:
    fx = k.fx_rate(f"{m}-28") or k.fx_rate(f"{m}-25")
    return fx[0] if fx else None


# ---------------------------------------------------------------------------
# action buttons — every action runs directly from the portal

def _act_btn(label: str, act: str, attrs: dict | None = None,
             primary: bool = False, small: bool = False,
             attach: bool = False) -> str:
    shown = f"📎 {label}" if attach else label
    cls = "btn" + (" primary" if primary else "") + (" sm" if small else "")
    extra = "".join(f' data-{k}="{E(str(v))}"'
                    for k, v in (attrs or {}).items())
    return (f'<button class="{cls}" data-act="{E(act)}"{extra}>'
            f'{E(shown)}</button>')


NEXT_HUMAN = {
    "awaiting_inputs": "Gather this month's documents — the checklist below "
                       "shows what's still needed.",
    "inputs_ready": "All documents are in. Process the month.",
    "stale_inputs_changed": "Documents changed since the last run — the month "
                            "needs to be reprocessed.",
    "closed": "Look through the items below, then approve the month.",
    "approved": "Nothing — this month is approved and locked.",
}

STATUS_HUMAN = {
    "awaiting_inputs": "Collecting documents",
    "inputs_ready": "Ready to process",
    "stale_inputs_changed": "Needs reprocessing",
    "closed": "Processed — awaiting your review",
    "approved": "Approved & locked",
}

CHIP = {
    "awaiting_inputs": ("chip-neutral", "⏰"),
    "inputs_ready": ("chip-accent", "▶"),
    "stale_inputs_changed": ("chip-warning", "↻"),
    "closed": ("chip-accent", "☑"),
    "approved": ("chip-good", "✓"),
}

STEPS = ["Collect", "Process", "Review", "Approve"]
STEP_OF = {"awaiting_inputs": 0, "inputs_ready": 1,
           "stale_inputs_changed": 1, "closed": 2, "approved": 3}

STEP_LABEL = {
    "funding_request": "Funding request",
    "us_bank_debit": "Left TD Bank",
    "wise_confirmation": "Sent via Wise",
    "wise_delivery": "Delivered by Wise",
    "bank_deposit": "Deposited in Ukraine",
    "ledger_entry": "Recorded in the books",
}


def _next_action_btn(status: str, m: str) -> str:
    if status in ("inputs_ready", "stale_inputs_changed"):
        return _act_btn("Process this month", "process", {"month": m},
                        primary=True)
    if status == "closed":
        return _act_btn("Approve this month", "approve", {"month": m},
                        primary=True)
    if status == "awaiting_inputs":
        return _act_btn("Upload documents", "upload", {"month": m},
                        primary=True, attach=True)
    return ""


# ---------------------------------------------------------------------------
# panels

def _masthead(data: dict) -> str:
    stamp = f'Data as of {E(data["generated"])}'
    if data["commit"]:
        stamp += f' · snapshot {E(data["commit"])}'
    return (
        '<header class="mast"><div class="mast-brand">'
        '<span class="mast-mark">KV</span>'
        '<span class="mast-org">Friends of Kinder Velt USA · Financial '
        'Oversight</span>'
        '<span class="mast-tools">'
        '<span class="curswitch" role="group" aria-label="Currency">'
        '<button class="cur-btn active" data-cur="usd">$ USD</button>'
        '<button class="cur-btn" data-cur="uah">₴ UAH</button></span>'
        '<button class="btn primary" data-wizard>Start monthly process'
        '</button>'
        + _act_btn("Check for updates", "checklatest")
        + '</span></div>'
        '<h1>Treasurer Console</h1>'
        f'<p class="mast-stamp">{stamp}</p>'
        '<p class="mast-stamp" id="conn-note"></p></header>')


def _td_summary(k: Knowledge, latest: dict | None) -> dict | None:
    if not latest or not latest["us_lines"]:
        return None
    lines = latest["us_lines"]
    closing = Decimal(lines[-1]["balance_after"]) \
        if lines[-1].get("balance_after") else None
    inflow = sum((Decimal(l["amount_uah"]) for l in lines
                  if Decimal(l["amount_uah"]) > 0), Decimal("0"))
    outflow = sum((abs(Decimal(l["amount_uah"])) for l in lines
                   if Decimal(l["amount_uah"]) < 0), Decimal("0"))
    return {"closing": closing, "inflow": inflow, "outflow": outflow,
            "lines": lines}


def _summary_tiles(data: dict, focus: dict | None, latest: dict | None) -> str:
    k: Knowledge = data["k"]
    tiles = []
    if focus:
        cls, icon = CHIP[focus["status"]]
        tiles.append(f'<div class="tile"><div class="tile-k">Focus month</div>'
                     f'<div class="tile-v">{E(month_name(focus["month"]))}</div>'
                     f'<div class="chip {cls}">{icon} '
                     f'{E(STATUS_HUMAN[focus["status"]])}</div></div>')
    else:
        tiles.append('<div class="tile"><div class="tile-k">Focus month</div>'
                     '<div class="tile-v">—</div>'
                     '<div class="chip chip-good">✓ All months approved</div></div>')
    if latest and latest["confidence"]:
        c = latest["confidence"]
        band = {"LOW": "chip-good", "MEDIUM": "chip-warning",
                "HIGH": "chip-critical"}[c["risk"]]
        tiles.append(f'<div class="tile"><div class="tile-k">Confidence · '
                     f'{E(month_name(latest["month"]))}</div>'
                     f'<div class="tile-v hero">{c["overall"]}<small>/100</small></div>'
                     f'<div class="chip {band}">Risk {c["risk"]}</div></div>')
    td = _td_summary(k, latest)
    if td and td["closing"] is not None:
        fxr = _month_fx(k, latest["month"]) if latest else None
        uah = td["closing"] * fxr if fxr else None
        tiles.append(f'<div class="tile"><div class="tile-k">Cash · TD Bank '
                     f'(US)</div><div class="tile-v">'
                     f'{pair(td["closing"], uah)}</div>'
                     f'<div class="tile-s">end of '
                     f'{E(month_name(latest["month"]))}</div></div>')
    else:
        tiles.append('<div class="tile"><div class="tile-k">Cash · TD Bank '
                     '(US)</div><div class="tile-v">—</div>'
                     '<div class="chip chip-warning">⚠ Statement needed</div></div>')
    if latest:
        n_open = sum(1 for f in latest["exceptions"] if f["status"] == "open")
        blocking = sum(1 for g in latest["gaps"] if g["severity"] == "blocking")
        if blocking:
            chip = f'<div class="chip chip-critical">⛔ {blocking} blocking</div>'
        elif n_open:
            chip = '<div class="chip chip-warning">⚠ Needs review</div>'
        else:
            chip = '<div class="chip chip-good">✓ All clear</div>'
        tiles.append(f'<div class="tile"><div class="tile-k">To review · '
                     f'{E(month_name(latest["month"]))}</div>'
                     f'<div class="tile-v">{n_open}<small> items</small></div>'
                     f'{chip}</div>')
    return '<section class="tiles">' + "".join(tiles) + "</section>"


def _now_panel(data: dict, focus: dict | None) -> str:
    k: Knowledge = data["k"]
    if focus is None:
        cp = data["current_period"]
        body = (f'<p>All finished months are approved. <b>{E(month_name(cp))}'
                f'</b> is still in progress — upload documents as they '
                f'arrive; the month is processed after month-end.</p>'
                + _act_btn("Upload documents", "upload", {"month": cp},
                           primary=True, attach=True))
        return _card("Now", "What needs the Treasurer", body)
    m = focus["month"]
    step = STEP_OF[focus["status"]]
    stepper = "".join(
        f'<li class="{"done" if i < step else "cur" if i == step else ""}">'
        f'<i></i>{s}</li>' for i, s in enumerate(STEPS))
    checklist = ""
    if focus["status"] in ("awaiting_inputs", "inputs_ready",
                           "stale_inputs_changed"):
        wanted = ([("Bookkeeper's ledger", f"workbook_{m}.xlsx")]
                  + [(f"{a['name']} statement", f"bank_{a['id']}_{m}.csv")
                     for a in k.active_accounts()]
                  + [(f"{a['name']} statement (US)", f"bank_{a['id']}_{m}.csv")
                     for a in k.active_us_accounts()]
                  + [(f"{p['name']} export", f"{p['id']}_{m}.csv")
                     for p in k.active_platforms()]
                  + [("Center statistics", f"CenterUpdates_{m}.csv")])
        inputs_dir = k.root / "months" / m / "inputs"
        have = ({p.name for p in inputs_dir.iterdir()}
                if inputs_dir.exists() else set())
        items = "".join(
            f'<li class="{"have" if fn in have else "need"}">'
            f'<b>{"✓" if fn in have else "○"}</b> {E(label)}</li>'
            for label, fn in wanted)
        checklist = f'<ul class="checklist">{items}</ul>'
    blocking = [g for g in focus["gaps"] if g["severity"] == "blocking"]
    gaps_html = "".join(
        f'<div class="gap critical"><b>{E(g["title"])}</b>'
        f'<p>{E(g["detail"])}</p></div>' for g in blocking)
    wizard_btn = ""
    if focus["status"] in ("awaiting_inputs", "inputs_ready",
                           "stale_inputs_changed"):
        wizard_btn = ('<button class="btn primary" data-wizard>'
                      '📎 Start monthly process</button>')
    body = (f'<ol class="stepper">{stepper}</ol>{checklist}{gaps_html}'
            f'<p class="next"><span class="eyebrow">Next</span> '
            f'{E(NEXT_HUMAN[focus["status"]])}</p>'
            f'<div class="btnrow">{wizard_btn}'
            f'{_next_action_btn(focus["status"], m) if not wizard_btn else ""}'
            + _act_btn("Leave a note for Claude", "note", {"month": m})
            + "</div>")
    return _card("Now", f"{month_name(m)} — what needs the Treasurer", body)


def _month_row_actions(m: dict) -> str:
    """Every month row carries its own action — no report-only lines."""
    mm = m["month"]
    st = m["status"]
    if st == "awaiting_inputs":
        return _act_btn("Upload", "upload", {"month": mm}, small=True,
                        attach=True)
    if st in ("inputs_ready", "stale_inputs_changed"):
        return _act_btn("Process now", "process", {"month": mm}, small=True)
    if st == "closed":
        return ('<button class="btn sm" data-goto="review">Review items'
                '</button>'
                + _act_btn("Approve", "approve", {"month": mm}, small=True))
    # approved: still actionable — a locked month can be amended
    return _act_btn("Request a change", "upload",
                    {"month": mm, "context": "amendment"}, small=True,
                    attach=True)


def _months_panel(data: dict) -> str:
    rows = []
    for m in data["months"]:
        cls, icon = CHIP[m["status"]]
        n_open = sum(1 for f in m["exceptions"] if f["status"] == "open")
        line = STATUS_HUMAN[m["status"]]
        if m["status"] == "closed" and n_open:
            line = (f"Processed — {n_open} item{'s' if n_open != 1 else ''} "
                    f"to review, then approve")
        rows.append(f'<div class="mrow"><b>{E(month_name(m["month"]))}</b>'
                    f'<span class="mrow-s">{E(line)}</span>'
                    f'<span class="mrow-a">{_month_row_actions(m)}</span>'
                    f'<span class="chip {cls}">{icon}</span></div>')
    cp = data["current_period"]
    if all(m["month"] != cp for m in data["months"]):
        rows.append(f'<div class="mrow ghost"><b>{E(month_name(cp))}</b>'
                    f'<span class="mrow-s">In progress — upload documents '
                    f'now, processed after month-end</span>'
                    f'<span class="mrow-a">'
                    + _act_btn("Upload", "upload", {"month": cp}, small=True,
                               attach=True)
                    + '</span><span class="chip chip-neutral">◌</span></div>')
    return _card("Months", "Where each month stands — every line has its "
                 "next step", "".join(rows))


def _human_ref(e: dict) -> str:
    f = e.get("file", "")
    loc = (e.get("locator") or "").replace("sheet=", "").replace("row=", "row ")
    return f"{f} · {loc}".strip(" ·") if f else ""


def _exception_queue(data: dict, latest: dict | None) -> str:
    if not latest:
        return ""
    sev_cls = {"high": "critical", "medium": "serious", "low": "warning"}
    open_f = [f for f in latest["exceptions"] if f["status"] == "open"]
    auto = [f for f in latest["exceptions"] if f["status"] == "auto_explained"]
    name = month_name(latest["month"])
    cards = []
    for f in open_f:
        refs = "".join(f'<code>{E(_human_ref(e))}</code>'
                       for e in f["evidence"][:3] if _human_ref(e))
        is_new_vendor = f["rule"] == "new_vendor"
        raw_name = (f["title"].split(":", 1)[-1].strip()
                    if is_new_vendor else "")
        accept = _act_btn("Accept as expected", "accept", {
            "finding": f["finding_id"], "rule": f["rule"],
            "vendor": f.get("vendor") or "", "title": f["title"][:120],
            "newvendor": "1" if is_new_vendor else "0", "name": raw_name,
            "month": latest["month"]})
        adjust = _act_btn("Make an adjustment", "upload", {
            "month": latest["month"], "context": f"adjustment to "
            f"“{f['title'][:90]}”", "finding": f["finding_id"]}, attach=True)
        cards.append(
            f'<div class="finding {sev_cls[f["severity"]]}">'
            f'<div class="finding-head"><span class="sev">'
            f'{E(f["severity"].upper())}</span>'
            f'<span class="rule">{E(f["rule"].replace("_", " "))}</span></div>'
            f'<b>{E(f["title"])}</b><p>{E(f["explanation"])}</p>'
            f'{f"<div class=refs>{refs}</div>" if refs else ""}'
            f'<div class="btnrow">{accept}{adjust}</div></div>')
    auto_html = ""
    if auto:
        items = "".join(f'<li>✓ {E(f["title"])} — <i>{E(f["resolution"] or "")}'
                        f'</i></li>' for f in auto)
        auto_html = (f'<details class="auto"><summary>{len(auto)} explained '
                     f'automatically from past decisions</summary>'
                     f'<ul>{items}</ul></details>')
    body = ((f'<div class="findings">{"".join(cards)}</div>' if cards else
             '<p class="allclear">✓ Nothing needs review.</p>') + auto_html)
    return _card("To review", f"{name} — accept what's expected, adjust "
                 "what's not", body, anchor="review")


def _gaps_panel(latest: dict | None) -> str:
    if not latest or not latest["gaps"]:
        return ""
    name = month_name(latest["month"])
    sev_cls = {"blocking": "critical", "material": "serious", "info": "neutral"}
    sev_word = {"blocking": "Required", "material": "Important", "info": "Optional"}
    rows = []
    for g in latest["gaps"]:
        send = _act_btn("Upload it", "upload",
                        {"month": latest["month"],
                         "context": f"missing item: {g['title'][:90]}"},
                        attach=True, small=True)
        rows.append(
            f'<div class="gap {sev_cls[g["severity"]]}">'
            f'<span class="sev">{E(sev_word[g["severity"]].upper())}</span>'
            f'<b>{E(g["title"])}</b><p>{E(g["detail"])}</p>'
            f'<div class="btnrow">{send}</div></div>')
    return _card("Missing information", f"{name} — upload what's missing and "
                 "the month reprocesses automatically", "".join(rows))


def _ua_accounts_panel(k: Knowledge, latest: dict | None) -> str:
    if not latest or not latest["reconciliation"]:
        return ""
    fxr = _month_fx(k, latest["month"])
    names = {a["id"]: a["name"] for a in k.accounts}
    rows, total = [], Decimal("0")
    for a in latest["reconciliation"]["accounts"]:
        uah = Decimal(a["book_closing"]) if a["book_closing"] else None
        if uah is not None:
            total += uah
        usd = (uah / fxr) if (uah is not None and fxr) else None
        ok = ('<span class="chip chip-good">✓ Verified</span>'
              if a["reconciled"] else
              '<span class="chip chip-warning">⚠ Unverified</span>')
        rows.append(f'<div class="arow"><span>{E(names.get(a["account"], a["account"]))}'
                    f'</span>{pair(usd, uah)}{ok}</div>')
    total_usd = (total / fxr) if fxr else None
    rows.append(f'<div class="arow total"><span>Total in Ukraine</span>'
                f'{pair(total_usd, total)}<span></span></div>')
    return _card("Ukraine accounts",
                 f"{month_name(latest['month'])} — balances checked against "
                 "the books", "".join(rows))


def _us_panel(data: dict, latest: dict | None) -> str:
    k: Knowledge = data["k"]
    td = _td_summary(k, latest)
    name = month_name(latest["month"]) if latest else ""
    if not td:
        body = ('<p>No TD Bank statement has been provided for this month, '
                'so the US cash position and transfer verification are '
                'unavailable.</p>'
                + _act_btn("Upload the TD Bank statement", "upload",
                           {"month": latest["month"] if latest else
                            data["current_period"],
                            "context": "TD Bank statement"},
                           primary=True, attach=True))
        return _card("TD Bank", "United States entity", body)
    fxr = _month_fx(k, latest["month"]) if latest else None

    def p(v):
        return pair(v, v * fxr if fxr else None)

    lines_html = "".join(
        f'<div class="arow"><span>{E(l["date"][5:])} · '
        f'{E(l["description"][:48])}</span>'
        + pair(Decimal(l["amount_uah"]),
               Decimal(l["amount_uah"]) * fxr if fxr else None)
        + "<span></span></div>"
        for l in td["lines"])
    body = (f'<div class="arow big"><span>Balance, end of {E(name)}</span>'
            f'{p(td["closing"]) if td["closing"] is not None else "—"}<span></span></div>'
            f'<div class="arow"><span>Came in (donations & payouts)</span>'
            f'{p(td["inflow"])}<span></span></div>'
            f'<div class="arow"><span>Went out (transfers & fees)</span>'
            f'{p(td["outflow"])}<span></span></div>'
            f'<details class="auto"><summary>Statement activity '
            f'({len(td["lines"])} lines)</summary>{lines_html}</details>')
    return _card("TD Bank", "United States entity — from the monthly "
                 "statement", body)


def _platforms_panel(k: Knowledge, latest: dict | None) -> str:
    if not latest:
        return ""
    name = month_name(latest["month"])
    platforms = latest["platforms"]
    labels = {p["id"]: p["name"] for p in k.funding_platforms}
    fxr = _month_fx(k, latest["month"])

    def p(v):
        v = Decimal(str(v))
        return pair(v, v * fxr if fxr else None)

    rows, tg, tn = [], Decimal("0"), Decimal("0")
    for pid, agg in sorted(platforms.items()):
        tg += Decimal(str(agg["gross"]))
        tn += Decimal(str(agg["net"]))
        rows.append(f'<div class="arow"><span>{E(labels.get(pid, pid))} · '
                    f'{agg["count"]} donation{"s" if agg["count"] != 1 else ""}'
                    f'</span>{p(agg["net"])}<span class="tile-s">of '
                    f'{_usd_s(agg["gross"])} given</span></div>')
    for pl in k.active_platforms():
        if pl["id"] not in platforms:
            rows.append(f'<div class="arow"><span>{E(pl["name"])}</span>'
                        + _act_btn("Upload export", "upload",
                                   {"month": latest["month"],
                                    "context": f"{pl['name']} export"},
                                   small=True, attach=True)
                        + '<span></span></div>')
    if platforms:
        rows.append(f'<div class="arow total"><span>Total received</span>'
                    f'{p(tn)}<span class="tile-s">after '
                    f'{_usd_s(tg - tn)} in fees</span></div>')
    return _card("Donations by platform",
                 f"{name} — what came in through each channel", "".join(rows))


def _traces_panel(latest: dict | None) -> str:
    if not latest:
        return ""
    name = month_name(latest["month"])
    if not latest["traces"]:
        return _card("Transfers to Ukraine", name,
                     "<p class='empty'>No transfers recorded this month.</p>")
    rows = []
    for t in latest["traces"]:
        uah = Decimal(t["amount_uah"]) if t["amount_uah"] else None
        dots = "".join(
            f'<span class="tdot {"ok" if l["status"] == "matched" else "miss"}">'
            f'</span>' for l in t["links"])
        chip = ('<span class="chip chip-good">✓ Fully traced</span>'
                if t["chain_complete"] else
                '<span class="chip chip-warning">⚠ Gaps in the trail</span>')
        steps = "".join(
            f'<li class="{"ok" if l["status"] == "matched" else "miss"}">'
            f'<b>{"✓" if l["status"] == "matched" else "○"} '
            f'{E(STEP_LABEL.get(l["step"], l["step"]))}</b>'
            f'<span>{E(l["detail"])}</span></li>' for l in t["links"])
        rows.append(
            f'<details class="trace"><summary>'
            f'<b>{E(t["transfer_id"])}</b>{pair(t["amount_usd"], uah)}'
            f'<span class="tdots">{dots}</span>{chip}</summary>'
            f'<ol class="tsteps">{steps}</ol></details>')
    return _card("Transfers to Ukraine",
                 f"{name} — tap a transfer to see its full trail",
                 "".join(rows))


# ---------------------------------------------------------------------------
# wizard

def _month_sources(k: Knowledge, m: str) -> list[dict]:
    inputs_dir = k.root / "months" / m / "inputs"
    names = ([p.name.lower() for p in inputs_dir.iterdir()]
             if inputs_dir.exists() else [])

    def have(*kws):
        return any(any(kw in n for kw in kws) for n in names)

    src = []
    for a in k.active_us_accounts():
        src.append({"group": "United States", "name": f"{a['name']} statement",
                    "hint": "monthly bank statement (CSV or PDF)",
                    "have": have(a["id"], a["id"].split("_")[0])})
    for p in k.active_platforms():
        src.append({"group": "United States", "name": f"{p['name']} export",
                    "hint": "monthly transactions/payout export (CSV)",
                    "have": have(p["id"])})
    src.append({"group": "Ukraine", "name": "Bookkeeper's ledger",
                "hint": "the accountant's monthly workbook (Excel)",
                "have": have("workbook", "ledger", "облік")})
    for a in k.active_accounts():
        src.append({"group": "Ukraine", "name": f"{a['name']} statement",
                    "hint": "monthly bank statement (CSV, Excel or PDF)",
                    "have": have(a["id"], a["id"].split("_")[0])})
    src.append({"group": "Ukraine", "name": "Center statistics",
                "hint": "children served, consultations, classes by center",
                "have": have("centerupdate", "stats", "statistic")})
    src.append({"group": "Ukraine", "name": "Wise transfer confirmations",
                "hint": "optional — improves transfer tracing",
                "have": have("wise"), "optional": True})
    return src


def _wizard(data: dict, focus: dict | None) -> tuple[str, str]:
    k: Knowledge = data["k"]
    if focus and focus["status"] in ("awaiting_inputs", "inputs_ready",
                                     "stale_inputs_changed"):
        m = focus["month"]
    else:
        m = data["current_period"]
    name = month_name(m)
    sources = _month_sources(k, m)
    missing = [s for s in sources if not s["have"] and not s.get("optional")]
    groups: dict[str, list[dict]] = {}
    for s in sources:
        groups.setdefault(s["group"], []).append(s)

    rows = []
    for group, items in groups.items():
        rows.append(f'<h4>{E(group)}</h4>')
        for s in items:
            if s["have"]:
                state = '<span class="chip chip-good">✓ Received</span>'
                btn = ""
            else:
                state = ('<span class="chip chip-neutral">○ Optional</span>'
                         if s.get("optional") else
                         '<span class="chip chip-warning">Needed</span>')
                btn = _act_btn("Upload", "upload",
                               {"month": m, "context": s["name"]},
                               small=True, attach=True)
            rows.append(f'<div class="wrow"><div class="wrow-t">'
                        f'<b>{E(s["name"])}</b>'
                        f'<span>{E(s["hint"])}</span></div>{state}{btn}</div>')

    if missing:
        footer = (_act_btn(f"Upload several at once", "upload",
                           {"month": m, "context": "monthly documents"},
                           primary=True, attach=True)
                  + f'<p class="hint">{len(missing)} of '
                  f'{len([s for s in sources if not s.get("optional")])} '
                  f'required items still needed. Uploading here sends them '
                  f'straight into the oversight system.</p>')
    else:
        footer = (_act_btn("Everything is in — process the month", "process",
                           {"month": m}, primary=True)
                  + '<p class="hint">✓ Every required item has been '
                  'received.</p>')
    return m, (f'<dialog id="wizard"><form method="dialog" class="composer wiz">'
               f'<h3>Monthly process — {E(name)}</h3>'
               f'<div class="wlist">{"".join(rows)}</div>'
               f'{footer}'
               f'<div class="btnrow"><button class="btn">Close</button></div>'
               f'</form></dialog>')


# ---------------------------------------------------------------------------
# charts (geometry from USD; labels currency-aware)

def _bar_chart_months(data: dict) -> str:
    closed = [m for m in data["months"] if m["analysis"]]
    if not closed:
        return "<p class='empty'>No processed months yet.</p>"
    W, H, pad_l, pad_b, pad_t = 640, 240, 8, 26, 16
    n = len(closed)
    peak = max(max(Decimal(m["analysis"]["financial"]["income_usd"]),
                   Decimal(m["analysis"]["financial"]["expenses_usd"]))
               for m in closed) or Decimal(1)
    group_w = (W - pad_l * 2) / max(n, 4)
    bar_w = min(44.0, group_w / 2.6)
    plot_h = H - pad_b - pad_t
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Money in vs money out by month" class="chart">']
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = H - pad_b - plot_h * frac
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_l}" '
                     f'y2="{y:.1f}" class="grid"/>')
    parts.append(f'<line x1="{pad_l}" y1="{H - pad_b}" x2="{W - pad_l}" '
                 f'y2="{H - pad_b}" class="axis"/>')
    for i, m in enumerate(closed):
        fin = m["analysis"]["financial"]
        cx = pad_l + group_w * i + group_w / 2
        series = ((fin["income_usd"], fin["income_uah"], "s1", "Money in"),
                  (fin["expenses_usd"], fin["expenses_uah"], "s2", "Money out"))
        for si, (usd, uah, cls, sname) in enumerate(series):
            h = float(Decimal(usd) / peak) * plot_h
            x = cx - bar_w - 1 + si * (bar_w + 2)
            y = H - pad_b - h
            tp = tip_pair(f"{month_name(m['month'])} · {sname}: ", usd, uah)
            u, hh = _usd_s(usd), _uah_s(uah)
            parts.append(
                f'<g class="hit" {tp}>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                f'height="{h:.1f}" rx="4" class="{cls}"/>'
                f'<text x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" '
                f'class="val money" data-usd="{E(u)}" data-uah="{E(hh)}" '
                f'text-anchor="middle">{E(u)}</text></g>')
        parts.append(f'<text x="{cx:.1f}" y="{H - 8}" class="tick" '
                     f'text-anchor="middle">{E(month_name(m["month"]))}</text>')
    parts.append("</svg>")
    legend = ('<div class="legend"><span><i class="dot s1"></i>Money in</span>'
              '<span><i class="dot s2"></i>Money out</span></div>')
    return legend + "".join(parts)


def _bar_chart_categories(k: Knowledge, latest: dict) -> str:
    fin = latest["analysis"]["financial"]
    cats = list(fin["by_category"].items())[:8]
    if not cats:
        return "<p class='empty'>No spending recorded.</p>"
    peak = max(Decimal(a["usd"]) for _, a in cats) or Decimal(1)
    group_cls = {"program": "s1", "administration": "s2", "taxes": "s3"}
    rows = []
    for cid, a in cats:
        w = float(Decimal(a["usd"]) / peak) * 100
        cls = group_cls.get(k.category_group.get(cid, ""), "sneutral")
        tp = tip_pair(f"{a['label']}: ", a["usd"], a["uah"],
                      f" · {a['count']} payments")
        rows.append(
            f'<div class="hbar hit" {tp}>'
            f'<span class="hbar-label">{E(a["label"])}</span>'
            f'<span class="hbar-track"><span class="hbar-fill {cls}" '
            f'style="width:{w:.1f}%"></span></span>'
            f'<span class="hbar-val">{pair(a["usd"], a["uah"])}</span></div>')
    legend = ('<div class="legend"><span><i class="dot s1"></i>Program</span>'
              '<span><i class="dot s2"></i>Administration</span>'
              '<span><i class="dot s3"></i>Taxes</span></div>')
    return legend + '<div class="hbars">' + "".join(rows) + "</div>"


def _usd_group_totals(k: Knowledge, fin: dict) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for cid, a in fin["by_category"].items():
        g = k.category_group.get(cid, "other")
        out[g] = out.get(g, Decimal("0")) + Decimal(a["usd"])
    return out


def _split_bar(k: Knowledge, latest: dict) -> str:
    fin = latest["analysis"]["financial"]
    usd_groups = _usd_group_totals(k, fin)
    parts = [("Program", usd_groups.get("program", Decimal("0")),
              Decimal(fin["program_uah"]), "s1"),
             ("Administration", usd_groups.get("administration", Decimal("0")),
              Decimal(fin["admin_uah"]), "s2"),
             ("Taxes", usd_groups.get("taxes", Decimal("0")),
              Decimal(fin["taxes_uah"]), "s3")]
    total = sum(p[1] for p in parts) or Decimal(1)
    exact = [float(v / total) * 100 for _, v, _, _ in parts]
    ints = [int(x) for x in exact]
    for i in sorted(range(len(exact)), key=lambda i: exact[i] - ints[i],
                    reverse=True)[: 100 - sum(ints)]:
        ints[i] += 1
    segs, labels = [], []
    for (nm, usd, uah, cls), pct, ipct in zip(parts, exact, ints):
        if pct <= 0:
            continue
        tp = tip_pair(f"{nm}: ", usd, uah, f" ({ipct}%)")
        segs.append(f'<span class="seg {cls} hit" style="width:{pct:.2f}%" '
                    f'{tp}></span>')
        labels.append(f'<span><i class="dot {cls}"></i>{nm} <b>{ipct}%</b></span>')
    return ('<div class="stack">' + "".join(segs) + "</div>"
            '<div class="legend">' + "".join(labels) + "</div>")


def _impact(k: Knowledge, latest: dict) -> str:
    ops = latest["analysis"]["operational"]
    t, ue = ops["totals"], ops["unit_economics"]
    fxr = _month_fx(k, latest["month"])

    def cost(v):
        if not v:
            return "—"
        uah = Decimal(v)
        return pair(uah / fxr if fxr else None, uah)

    tiles = "".join(
        f'<div class="tile sm"><div class="tile-k">{E(lbl)}</div>'
        f'<div class="tile-v">{v}</div></div>'
        for lbl, v in (("Children served", str(t["children_served"])),
                       ("Consultations", str(t["consultations"])),
                       ("Classes", str(t["classes"])),
                       ("New children", str(t["new_children"])),
                       ("Cost per child", cost(ue["cost_per_child_served_uah"])),
                       ("Cost per class", cost(ue["cost_per_class_uah"]))))
    return f'<section class="tiles">{tiles}</section>'


def _card(eyebrow: str, title: str, body: str, anchor: str = "") -> str:
    aid = f' id="{E(anchor)}"' if anchor else ""
    return (f'<section class="card"{aid}><header><span class="eyebrow">'
            f'{E(eyebrow)}</span><h2>{E(title)}</h2></header>{body}</section>')


def _footer() -> str:
    return (
        '<footer class="foot"><p>Actions on this page commit directly into '
        'the oversight records through your GitHub connection; processing '
        'runs automatically within a couple of minutes — use “Check for '
        'updates” to pull in the freshest results. The monthly reports '
        'remain the authoritative record; the confidence score is an aid '
        'to the Treasurer’s review, not an audit opinion. Payroll appears '
        'only as category totals. This console is for the Treasurer — '
        'don’t share it publicly.</p></footer>')


# ---------------------------------------------------------------------------
# dialogs

_DIALOGS = """
<dialog id="dlg-upload"><form class="composer" onsubmit="return false">
<h3 id="u-title">Upload documents</h3>
<div class="cfiles">
  <label class="btn" for="u-files">📎 Choose files</label>
  <input type="file" id="u-files" multiple hidden>
  <span id="u-list" class="cfile-list">No files chosen yet</span>
</div>
<textarea id="u-note" rows="3" placeholder="Optional note — anything the
oversight system or Claude should know about these documents"></textarea>
<p class="hint" id="u-hint">Files are sent straight into the month's
records; processing runs automatically.</p>
<div class="status" id="u-status"></div>
<div class="btnrow">
  <button type="button" class="btn primary" id="u-send">Send</button>
  <button type="button" class="btn" data-close>Close</button>
</div></form></dialog>

<dialog id="dlg-accept"><form class="composer" onsubmit="return false">
<h3 id="a-title">Accept as expected</h3>
<p class="hint" id="a-sub"></p>
<div id="a-vendor-row" style="display:none">
  <label class="lbl" for="a-category">What kind of spending is this
  vendor?</label>
  <select id="a-category"></select>
</div>
<label class="lbl" for="a-reason">Why is this expected?</label>
<textarea id="a-reason" rows="3" placeholder="e.g. Monthly payroll run —
verified against the payroll register"></textarea>
<p class="hint">Your decision is remembered: the same situation is
explained automatically in future months.</p>
<div class="status" id="a-status"></div>
<div class="btnrow">
  <button type="button" class="btn primary" id="a-send">Accept</button>
  <button type="button" class="btn" data-close>Close</button>
</div></form></dialog>

<dialog id="dlg-confirm"><form class="composer" onsubmit="return false">
<h3 id="c2-title"></h3>
<p id="c2-body"></p>
<div class="status" id="c2-status"></div>
<div class="btnrow">
  <button type="button" class="btn primary" id="c2-go"></button>
  <button type="button" class="btn" data-close>Close</button>
</div></form></dialog>

<dialog id="dlg-note"><form class="composer" onsubmit="return false">
<h3>Leave a note for Claude</h3>
<textarea id="n-text" rows="5" placeholder="Questions, context, anything
that needs judgement — Claude reads these when working on the
oversight records"></textarea>
<div class="status" id="n-status"></div>
<div class="btnrow">
  <button type="button" class="btn primary" id="n-send">Save note</button>
  <button type="button" class="btn" data-close>Close</button>
</div></form></dialog>
"""


# ---------------------------------------------------------------------------
# page assembly

def render(data: dict) -> str:
    k: Knowledge = data["k"]
    months = data["months"]
    latest = next((m for m in reversed(months) if m["analysis"]), None)
    focus = next((m for m in months if m["status"] != "approved"), None)

    wizard_month, wizard_html = _wizard(data, focus)
    categories = [{"id": cid, "label": k.category_label[cid],
                   "group": k.category_group[cid]}
                  for cid in k.category_group]
    boot = {
        "gh": data["repo"],
        "root": "kv-fos",
        "wizardMonth": wizard_month,
        "latestMonth": latest["month"] if latest else None,
        "snapshot": data["commit"],
        "categories": categories,
        "today": data["today"],
    }

    ua_tab = (
        _exception_queue(data, latest)
        + _gaps_panel(latest)
        + _ua_accounts_panel(k, latest)
        + _card("Money in vs money out", "By month — both bars labeled",
                _bar_chart_months(data))
        + (_card("Where the money went",
                 f"{month_name(latest['month'])} — colored by purpose",
                 _bar_chart_categories(k, latest)) if latest else "")
        + (_card("Program share",
                 f"{month_name(latest['month'])} — share of total spending",
                 _split_bar(k, latest)) if latest else "")
        + (_card("Impact", f"{month_name(latest['month'])} — what the "
                 "spending achieved", _impact(k, latest)) if latest else ""))
    us_tab = (_us_panel(data, latest) + _platforms_panel(k, latest)
              + _traces_panel(latest))

    body = (
        _masthead(data)
        + _summary_tiles(data, focus, latest)
        + _now_panel(data, focus)
        + _months_panel(data)
        + '<nav class="tabs" role="tablist">'
          '<button class="tab active" data-tab="ua" role="tab">Ukraine</button>'
          '<button class="tab" data-tab="us" role="tab">United States</button>'
          '</nav>'
        + f'<div class="tabpane active" data-pane="ua">{ua_tab}</div>'
        + f'<div class="tabpane" data-pane="us">{us_tab}</div>'
        + _footer())
    return ("<title>KV Treasurer Console</title>\n"
            f"<style>{_CSS}</style>\n"
            f'<main class="wrap">{body}</main>\n'
            f"{_DIALOGS}\n{wizard_html}\n"
            f"<div id='tip' role='tooltip'></div>\n"
            f'<script id="kvfos-boot" type="application/json">'
            f"{json.dumps(boot)}</script>\n"
            f"<script>{_JS}</script>")


_CSS = """
:root{color-scheme:light;
--page:#f7f8f6;--surface:#fdfdfc;--surface-2:#f0f2ef;
--ink:#122234;--ink-2:#4d5c6b;--ink-3:#8a949e;
--line:#e2e5e1;--hair:rgba(18,34,52,.10);
--accent:#1E5FA8;--accent-ink:#fff;--brand-yellow:#FFC93C;
--s1:#1E5FA8;--s2:#eda100;--s3:#1baf7a;--sneutral:#8a949e;
--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;
--good-text:#006300;--tip-bg:#122234;--tip-ink:#fff}
@media(prefers-color-scheme:dark){:root:where(:not([data-theme=light])){color-scheme:dark;
--page:#0e1420;--surface:#16202e;--surface-2:#1c2836;
--ink:#e8edf4;--ink-2:#a8b4c0;--ink-3:#71818f;
--line:#243244;--hair:rgba(232,237,244,.10);
--accent:#4FA8E0;--accent-ink:#0e1420;
--s1:#3987e5;--s2:#c98500;--s3:#199e70;--sneutral:#71818f;
--good-text:#0ca30c;--tip-bg:#e8edf4;--tip-ink:#122234}}
:root[data-theme=dark]{color-scheme:dark;
--page:#0e1420;--surface:#16202e;--surface-2:#1c2836;
--ink:#e8edf4;--ink-2:#a8b4c0;--ink-3:#71818f;
--line:#243244;--hair:rgba(232,237,244,.10);
--accent:#4FA8E0;--accent-ink:#0e1420;
--s1:#3987e5;--s2:#c98500;--s3:#199e70;--sneutral:#71818f;
--good-text:#0ca30c;--tip-bg:#e8edf4;--tip-ink:#122234}
:root[data-theme=light]{color-scheme:light;
--page:#f7f8f6;--surface:#fdfdfc;--surface-2:#f0f2ef;
--ink:#122234;--ink-2:#4d5c6b;--ink-3:#8a949e;
--line:#e2e5e1;--hair:rgba(18,34,52,.10);
--accent:#1E5FA8;--accent-ink:#fff;
--s1:#1E5FA8;--s2:#eda100;--s3:#1baf7a;--sneutral:#8a949e;
--good-text:#006300;--tip-bg:#122234;--tip-ink:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
-webkit-text-size-adjust:100%}
.wrap{max-width:980px;margin:0 auto;padding:0 16px 48px;display:flex;
flex-direction:column;gap:18px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
font-size:.85em}
h1,h2,h3{margin:0;text-wrap:balance}
.eyebrow{display:block;font-size:11px;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;color:var(--accent)}
.mast{padding:22px 0 4px;border-bottom:3px solid var(--brand-yellow)}
.mast-brand{display:flex;align-items:center;gap:10px;margin-bottom:14px;
flex-wrap:wrap}
.mast-mark{background:var(--accent);color:var(--accent-ink);font-weight:800;
padding:3px 8px;border-radius:4px;letter-spacing:.04em}
.mast-org{font-size:11.5px;font-weight:600;letter-spacing:.05em;
text-transform:uppercase;color:var(--ink-2);flex:1;min-width:180px}
.mast-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.curswitch{display:inline-flex;border:1px solid var(--hair);border-radius:7px;
overflow:hidden;background:var(--surface)}
.cur-btn{border:0;background:transparent;color:var(--ink-2);font-weight:700;
font-size:12.5px;padding:6px 12px;cursor:pointer}
.cur-btn.active{background:var(--accent);color:var(--accent-ink)}
.mast h1{font-size:28px;font-weight:800;letter-spacing:-.01em}
.mast-stamp{margin:6px 0 0;color:var(--ink-3);font-size:12.5px}
.mast p:last-child{margin-bottom:12px}
#conn-note:empty{display:none}
#conn-note{color:var(--serious);font-weight:600}
.btn{border:1px solid var(--hair);background:var(--surface);color:var(--accent);
font-weight:700;font-size:13px;border-radius:7px;padding:8px 14px;
cursor:pointer;font-family:inherit}
.btn:hover{border-color:var(--accent)}
.btn.primary{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btn[disabled]{opacity:.5;cursor:default}
.btn.sm{padding:5px 10px;font-size:12px}
.btnrow{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
gap:12px}
.tile{background:var(--surface);border:1px solid var(--hair);border-radius:8px;
padding:13px 15px;display:flex;flex-direction:column;gap:6px;min-width:0}
.tile.sm{padding:10px 12px}
.tile-k{font-size:11px;font-weight:700;letter-spacing:.06em;
text-transform:uppercase;color:var(--ink-3)}
.tile-v{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;
overflow-wrap:anywhere}
.tile-v.hero{font-size:32px}
.tile-v small{font-size:.55em;font-weight:600;color:var(--ink-3)}
.tile-s{font-size:12px;color:var(--ink-2)}
.tile .chip{align-self:flex-start}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:10px;
padding:16px 18px}
.card>header{margin-bottom:12px}
.card h2{font-size:16.5px;font-weight:700;margin-top:2px}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;
font-weight:700;padding:2px 9px;border-radius:99px;max-width:100%;
white-space:normal;line-height:1.35}
.chip-good{background:color-mix(in srgb,var(--good) 14%,transparent);color:var(--good-text)}
.chip-warning{background:color-mix(in srgb,var(--warn) 20%,transparent);color:var(--ink)}
.chip-critical{background:color-mix(in srgb,var(--crit) 14%,transparent);color:var(--crit)}
.chip-accent{background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent)}
.chip-neutral{background:var(--surface-2);color:var(--ink-2)}
.tabs{display:flex;gap:6px;border-bottom:2px solid var(--line);
position:sticky;top:0;background:var(--page);z-index:5;padding-top:4px}
.tab{border:0;background:transparent;color:var(--ink-2);font-weight:700;
font-size:14px;padding:10px 16px;cursor:pointer;border-bottom:3px solid
transparent;margin-bottom:-2px;font-family:inherit}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tabpane{display:none;flex-direction:column;gap:18px}
.tabpane.active{display:flex}
.stepper{display:flex;list-style:none;margin:0 0 14px;padding:0}
.stepper li{flex:1;text-align:center;font-size:12px;font-weight:600;
color:var(--ink-3);position:relative;padding-top:18px}
.stepper li i{position:absolute;top:0;left:50%;transform:translateX(-50%);
width:12px;height:12px;border-radius:50%;background:var(--surface-2);
border:2px solid var(--line)}
.stepper li::before{content:"";position:absolute;top:6px;left:-50%;width:100%;
height:2px;background:var(--line)}
.stepper li:first-child::before{display:none}
.stepper li.done{color:var(--ink-2)}
.stepper li.done i{background:var(--good);border-color:var(--good)}
.stepper li.cur{color:var(--accent);font-weight:800}
.stepper li.cur i{background:var(--accent);border-color:var(--accent)}
.checklist{list-style:none;margin:0 0 8px;padding:0;display:flex;
flex-direction:column;gap:6px}
.checklist li{font-size:13.5px;color:var(--ink-2)}
.checklist li b{font-weight:800;margin-right:4px}
.checklist li.have b{color:var(--good-text)}
.checklist li.need b{color:var(--ink-3)}
.next{margin:10px 0 0;font-weight:600}
.mrow{display:flex;align-items:center;gap:10px;padding:9px 0;
border-bottom:1px solid var(--line)}
.mrow:last-child{border-bottom:0}
.mrow b{min-width:110px}
.mrow-s{flex:1;font-size:13px;color:var(--ink-2)}
.mrow-a{display:flex;gap:6px;flex-wrap:wrap}
.mrow.ghost{color:var(--ink-3)}
.findings{display:flex;flex-direction:column;gap:12px}
.finding{border:1px solid var(--hair);border-left:4px solid var(--sneutral);
border-radius:6px;padding:10px 14px}
.finding.critical{border-left-color:var(--crit)}
.finding.serious{border-left-color:var(--serious)}
.finding.warning{border-left-color:var(--warn)}
.finding-head{display:flex;gap:8px;align-items:center;margin-bottom:2px}
.sev{font-size:10px;font-weight:800;letter-spacing:.08em;color:var(--ink-3)}
.finding.critical .sev{color:var(--crit)}
.rule{font-size:11px;color:var(--ink-3);text-transform:capitalize}
.finding p{margin:4px 0;font-size:13px;color:var(--ink-2)}
.refs{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.refs code{background:var(--surface-2);padding:1px 6px;border-radius:4px;
font-size:11px}
details summary{cursor:pointer;font-size:13px;font-weight:600;
color:var(--accent);list-style:none}
details summary::-webkit-details-marker{display:none}
details.auto{margin-top:12px}
details.auto ul{margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--ink-2)}
.allclear{color:var(--good-text);font-weight:600}
.gap{border:1px solid var(--hair);border-left:4px solid var(--sneutral);
border-radius:6px;padding:8px 14px;margin-bottom:10px}
.gap.critical{border-left-color:var(--crit)}
.gap.serious{border-left-color:var(--serious)}
.gap.neutral{border-left-color:var(--line)}
.gap p{margin:3px 0;font-size:13px;color:var(--ink-2)}
.gap .sev{display:block;margin-bottom:2px}
.arow{display:flex;align-items:center;gap:10px;padding:8px 0;
border-bottom:1px solid var(--line);font-size:14px}
.arow:last-child{border-bottom:0}
.arow>span:first-child{flex:1;color:var(--ink-2)}
.arow .money{font-variant-numeric:tabular-nums;font-weight:700}
.arow.total{font-weight:800}
.arow.total>span:first-child{color:var(--ink)}
.arow.big .money{font-size:20px}
.trace{border:1px solid var(--hair);border-radius:8px;padding:10px 14px;
margin-bottom:10px}
.trace summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
color:var(--ink)}
.trace summary .money{font-variant-numeric:tabular-nums;color:var(--ink-2)}
.tdots{display:flex;gap:5px;flex:1;min-width:90px}
.tdot{width:13px;height:13px;border-radius:50%;display:inline-block}
.tdot.ok{background:var(--good)}
.tdot.miss{background:var(--surface-2);border:2px dashed var(--crit)}
.tsteps{list-style:none;margin:12px 0 2px;padding:0;display:flex;
flex-direction:column;gap:8px}
.tsteps li{font-size:13px;display:flex;flex-direction:column}
.tsteps li b{font-weight:700}
.tsteps li.ok b{color:var(--good-text)}
.tsteps li.miss b{color:var(--crit)}
.chart{width:100%;height:auto;display:block}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .axis{stroke:var(--ink-3);stroke-width:1}
.chart .s1,.hbar-fill.s1,.seg.s1,.dot.s1{fill:var(--s1);background:var(--s1)}
.chart .s2,.hbar-fill.s2,.seg.s2,.dot.s2{fill:var(--s2);background:var(--s2)}
.hbar-fill.s3,.seg.s3,.dot.s3{background:var(--s3)}
.hbar-fill.sneutral{background:var(--sneutral)}
.chart .val{fill:var(--ink-2);font-size:11px;font-variant-numeric:tabular-nums}
.chart .tick{fill:var(--ink-3);font-size:11px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);
margin-bottom:10px}
.legend .dot{width:10px;height:10px;border-radius:3px;display:inline-block;
margin-right:5px;vertical-align:-1px}
.hbars{display:flex;flex-direction:column;gap:7px}
.hbar{display:grid;grid-template-columns:140px 1fr 92px;gap:10px;
align-items:center;font-size:13px}
.hbar-label{color:var(--ink-2);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}
.hbar-track{background:var(--surface-2);border-radius:4px;height:16px;
overflow:hidden}
.hbar-fill{display:block;height:100%;border-radius:4px 0 0 4px}
.hbar-val{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink)}
@media(max-width:560px){.hbar{grid-template-columns:96px 1fr 84px;font-size:12px}
.mrow{flex-wrap:wrap}.mrow b{min-width:90px}.mrow-s{flex-basis:100%;order:3}
.mast h1{font-size:24px}}
.stack{display:flex;gap:2px;height:26px;border-radius:6px;overflow:hidden;
margin-bottom:10px}
.seg{display:block;height:100%}
.empty{color:var(--ink-3)}
.foot{border-top:1px solid var(--line);padding-top:14px;font-size:12.5px;
color:var(--ink-3)}
dialog{border:1px solid var(--hair);border-radius:12px;background:var(--surface);
color:var(--ink);max-width:540px;width:calc(100vw - 40px);padding:0}
dialog::backdrop{background:rgba(14,20,32,.45)}
.composer{padding:20px;display:flex;flex-direction:column;gap:12px}
.composer h3{font-size:16px}
.composer textarea,.composer select{width:100%;border:1px solid var(--line);
border-radius:8px;background:var(--surface-2);color:var(--ink);padding:10px;
font:inherit;font-size:14px}
.composer textarea{resize:vertical}
.composer .hint{margin:0;font-size:12.5px;color:var(--ink-3)}
.lbl{font-size:12.5px;font-weight:700;color:var(--ink-2)}
.status{font-size:13px;font-weight:600;white-space:pre-line}
.status:empty{display:none}
.status.ok{color:var(--good-text)}
.status.err{color:var(--crit)}
.status.busy{color:var(--ink-2)}
.wiz{max-height:82vh;overflow-y:auto}
.wlist h4{margin:10px 0 2px;font-size:11px;font-weight:800;
letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3)}
.wrow{display:flex;align-items:center;gap:10px;padding:8px 0;
border-bottom:1px solid var(--line);flex-wrap:wrap}
.wrow:last-child{border-bottom:0}
.wrow-t{flex:1;min-width:150px;display:flex;flex-direction:column}
.wrow-t b{font-size:13.5px}
.wrow-t span{font-size:12px;color:var(--ink-3)}
.wrow .btn{padding:5px 10px;font-size:12px}
.cfiles{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
background:var(--surface-2);border:1px dashed var(--line);border-radius:8px;
padding:8px 12px}
.cfile-list{font-size:12.5px;color:var(--ink-3);flex:1;min-width:140px}
.cfile-list.has{color:var(--ink);font-weight:600}
#tip{position:fixed;z-index:10;background:var(--tip-bg);color:var(--tip-ink);
font-size:12px;font-weight:600;padding:5px 9px;border-radius:5px;
pointer-events:none;opacity:0;transition:opacity .1s;max-width:300px}
@media(prefers-reduced-motion:reduce){#tip{transition:none}}
"""

_JS = r"""
(function(){
'use strict';
var BOOT=JSON.parse(document.getElementById('kvfos-boot').textContent);
var GH=BOOT.gh, SERVER='GitHub MCP';
var TEXT_EXT=['csv','txt','md','yaml','yml','json'];

// ---- currency toggle -------------------------------------------------------
var CUR=localStorage.getItem('kvfos-cur')||'usd';
function applyCur(){
  document.querySelectorAll('.money').forEach(function(el){
    var v=el.getAttribute('data-'+CUR); if(v)el.textContent=v;});
  document.querySelectorAll('.cur-btn').forEach(function(b){
    b.classList.toggle('active',b.getAttribute('data-cur')===CUR);});
}

// ---- GitHub connection ------------------------------------------------------
function mcpReady(){return window.claude&&window.claude.mcp;}
var FIX={
  needs_reauth:'Reconnect GitHub: claude.ai Settings → Connectors → GitHub.',
  server_not_connected:'To act directly from this portal, add the GitHub '+
    'connector: claude.ai Settings → Connectors → add GitHub, then reload.',
  selection_required:'Choose which GitHub connection this page should use '+
    'when claude.ai asks, then try again.',
  not_in_manifest:'This page hasn’t been granted that permission — '+
    'reload and allow GitHub access when asked.',
  not_granted:'Allow this page to use your connectors when claude.ai asks, '+
    'then try again.',
  blocked_by_policy:'Your organization’s settings block this action.',
  approval_required:'Your organization requires approval for this action; '+
    'it can’t run from the page.',
  capability_disabled:'This view can’t reach your connectors — reload '+
    'the page and try again.'
};
function errText(e,isWrite){
  var code=e&&e.code||'upstream_error';
  if(FIX[code])return FIX[code];
  if(code==='tool_error'){
    if(/not accessible by integration|403/i.test(e.message||''))
      return 'Your GitHub connection can read but not write this '+
        'repository. On github.com: Settings \u2192 Applications \u2192 '+
        'find \u201cGitHub MCP Server\u201d \u2192 grant it read-and-write '+
        'access to puzzo33/KinderVelt, then try again.';
    return 'GitHub reported: '+(e.message||'a problem');}
  if(code==='server_unavailable'||code==='upstream_error')
    return isWrite?
      'GitHub didn’t confirm — it may still have gone through. Use '+
      '“Check for updates” before retrying.':
      'GitHub is briefly unreachable — try again in a moment.';
  return 'Something went wrong ('+code+').';
}
function call(tool,input){
  if(!mcpReady())
    return Promise.reject({code:'server_not_connected'});
  return window.claude.mcp.callTool(SERVER,tool,input);
}
function commitFile(path,content,message,sha){
  var input={owner:GH.owner,repo:GH.repo,branch:GH.branch,
    path:path,content:content,message:message};
  if(sha)input.sha=sha;
  return call('create_or_update_file',input);
}
function getRaw(path){
  return call('get_file_contents',{owner:GH.owner,repo:GH.repo,
    path:path,ref:'refs/heads/'+GH.branch}).then(function(r){
      var txt='';
      (r.content||[]).forEach(function(b){
        if(b.type==='text'&&b.text)txt+=b.text;
        if(b.resource&&b.resource.text)txt+=b.resource.text;});
      if(!txt&&typeof r.payload==='string')txt=r.payload;
      return txt;});
}
function fileSha(path){
  return getRaw(path).then(function(t){
    var m=t.match(/SHA:\s*([0-9a-f]{40})/i);
    return m?m[1]:null;});
}
// create; if the file already exists, fetch its sha and update instead
function putFile(path,content,message){
  return commitFile(path,content,message).catch(function(e){
    if(e&&e.code==='tool_error'){
      return fileSha(path).then(function(sha){
        if(!sha)throw e;
        return commitFile(path,content,message,sha);});
    }
    throw e;});
}
function ts(){return new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);}
function yamlStr(s){return '"'+String(s).replace(/\\/g,'\\\\')
  .replace(/"/g,'\\"').replace(/\n/g,' ')+'"';}

// connection probe — diagnoses the exact state so the fix is never a guess
function connProbe(){
  var note=document.getElementById('conn-note');
  if(!note)return;
  if(!mcpReady()){
    note.textContent='Direct actions need this page opened on claude.ai — '+
      'connector access is not available in this view.';
    return;}
  window.claude.mcp.listTools().then(function(res){
    var servers=res.servers||[];
    var gh=servers.filter(function(s){return s.server===SERVER})[0];
    if(gh&&gh.tools&&gh.tools.length){
      note.textContent=(gh.authStatus==='needs_reauth')?FIX.needs_reauth:'';
      return;}
    var names=servers.map(function(s){return s.server});
    if(gh){
      note.textContent='GitHub is connected but not ready for this page — '+
        'if claude.ai asks you to choose or allow a connection, do so, '+
        'then reload. Otherwise reconnect GitHub in Settings → Connectors.';
    }else if(names.length){
      note.textContent='Connections this page can see: '+names.join(', ')+
        ' — “GitHub” is not among them. If your GitHub connection has a '+
        'different name, tell Claude what it is called and the console '+
        'will be re-wired. Otherwise add GitHub in claude.ai Settings → '+
        'Connectors, then reload.';
    }else{
      note.textContent='No connections are visible to this page yet. Two '+
        'things must both be true: the GitHub connector is added in '+
        'claude.ai Settings → Connectors, AND you allowed this page to '+
        'use your connectors when claude.ai asked (reload the page to be '+
        'asked again).';
    }
  }).catch(function(e){
    note.textContent='Connection check: '+errText(e,false);
  });
}
connProbe();

// ---- status helpers ---------------------------------------------------------
function setStatus(id,cls,msg){var el=document.getElementById(id);
  el.className='status '+cls;el.textContent=msg;}
function successNote(id,what){
  setStatus(id,'ok','✓ '+what+' Processing runs automatically — use '+
    '“Check for updates” in a couple of minutes.');}

// ---- upload action ----------------------------------------------------------
var upCtx={month:null,context:'',finding:'',files:[]};
function openUpload(btn){
  upCtx={month:btn.getAttribute('data-month')||BOOT.wizardMonth,
    context:btn.getAttribute('data-context')||'',
    finding:btn.getAttribute('data-finding')||'',files:[]};
  document.getElementById('u-title').textContent=
    (upCtx.context?upCtx.context.charAt(0).toUpperCase()+
      upCtx.context.slice(1):'Upload documents')+
    ' — '+monthLabel(upCtx.month);
  document.getElementById('u-files').value='';
  document.getElementById('u-note').value='';
  renderUList();setStatus('u-status','','');
  document.getElementById('dlg-upload').showModal();
}
function renderUList(){
  var el=document.getElementById('u-list');
  if(upCtx.files.length){el.textContent=upCtx.files.map(function(f){
    return f.name}).join(', ');el.classList.add('has');}
  else{el.textContent='No files chosen yet';el.classList.remove('has');}
}
function readFile(f){
  return new Promise(function(res,rej){
    var ext=f.name.split('.').pop().toLowerCase();
    var isText=TEXT_EXT.indexOf(ext)>=0;
    var r=new FileReader();
    r.onerror=function(){rej(new Error('could not read '+f.name))};
    if(isText){r.onload=function(){res({name:f.name,content:r.result})};
      r.readAsText(f);}
    else{r.onload=function(){
      var b=new Uint8Array(r.result),s='';
      for(var i=0;i<b.length;i+=0x8000)
        s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000));
      res({name:f.name+'.b64',content:btoa(s)})};
      r.readAsArrayBuffer(f);}
  });
}
function doUpload(){
  var note=document.getElementById('u-note').value.trim();
  if(!upCtx.files.length&&!note){
    setStatus('u-status','err','Choose at least one file or write a note.');
    return;}
  var btn=document.getElementById('u-send');btn.disabled=true;
  var base=BOOT.root+'/months/'+upCtx.month;
  var chain=Promise.resolve(),done=0;
  upCtx.files.forEach(function(f){
    chain=chain.then(function(){return readFile(f)}).then(function(r){
      setStatus('u-status','busy','Sending '+r.name+'…');
      return putFile(base+'/inputs/'+r.name,r.content,
        'Portal upload: '+r.name+' for '+upCtx.month+
        (upCtx.context?' ('+upCtx.context+')':''));
    }).then(function(){done++});
  });
  if(note){
    chain=chain.then(function(){
      var p=base+'/notes/'+(upCtx.finding?'adjust-'+upCtx.finding+'-':'note-')
        +ts()+'.md';
      return putFile(p,'# Treasurer note — '+upCtx.month+'\n\n'+
        (upCtx.context?'Context: '+upCtx.context+'\n\n':'')+note+'\n',
        'Portal note for '+upCtx.month);
    });
  }
  chain.then(function(){
    successNote('u-status',(done?done+' file'+(done!==1?'s':'')+' sent.':
      'Note saved.'));
    btn.disabled=false;refreshWizardRow();
  }).catch(function(e){btn.disabled=false;
    setStatus('u-status','err',errText(e,true));});
}
function refreshWizardRow(){/* received-state refreshes on next republish */}

// ---- accept action ----------------------------------------------------------
var acCtx={};
function openAccept(btn){
  acCtx={finding:btn.getAttribute('data-finding'),
    rule:btn.getAttribute('data-rule'),
    vendor:btn.getAttribute('data-vendor'),
    title:btn.getAttribute('data-title'),
    isNew:btn.getAttribute('data-newvendor')==='1',
    name:btn.getAttribute('data-name'),
    month:btn.getAttribute('data-month')};
  document.getElementById('a-title').textContent=
    acCtx.isNew?'Confirm vendor: '+acCtx.name:'Accept as expected';
  document.getElementById('a-sub').textContent=acCtx.title;
  var vrow=document.getElementById('a-vendor-row');
  vrow.style.display=acCtx.isNew?'':'none';
  if(acCtx.isNew){
    var sel=document.getElementById('a-category');
    sel.innerHTML=BOOT.categories.map(function(c){
      return '<option value="'+c.id+'" data-group="'+c.group+'">'+
        c.label+' ('+c.group+')</option>'}).join('');
  }
  document.getElementById('a-reason').value='';
  setStatus('a-status','','');
  document.getElementById('dlg-accept').showModal();
}
function doAccept(){
  var reason=document.getElementById('a-reason').value.trim();
  if(!reason){setStatus('a-status','err',
    'Say briefly why this is expected — it becomes the explanation shown '+
    'in future months.');return;}
  var btn=document.getElementById('a-send');btn.disabled=true;
  setStatus('a-status','busy','Saving your decision…');
  var path,body;
  if(acCtx.isNew){
    var sel=document.getElementById('a-category');
    var opt=sel.options[sel.selectedIndex];
    path=BOOT.root+'/knowledge/learned/portal/vendor-'+acCtx.finding+'.yaml';
    body='kind: new_vendor\nname: '+yamlStr(acCtx.name)+
      '\ncategory: '+opt.value+'\nclassification: '+
      opt.getAttribute('data-group')+'\nconfirmed: "'+BOOT.today+
      '"\nby: treasurer-portal\nnote: '+yamlStr(reason)+'\n';
  }else{
    path=BOOT.root+'/knowledge/learned/portal/accept-'+acCtx.finding+'.yaml';
    body='kind: resolution\nrule: '+acCtx.rule+'\n'+
      (acCtx.vendor?'vendor: '+acCtx.vendor+'\n':'')+
      'explanation: '+yamlStr(reason)+'\naccepted: "'+BOOT.today+
      '"\nby: treasurer-portal\n';
  }
  putFile(path,body,'Portal: accept '+acCtx.rule+' ('+acCtx.month+')')
    .then(function(){btn.disabled=false;
      successNote('a-status','Decision saved and remembered.');})
    .catch(function(e){btn.disabled=false;
      setStatus('a-status','err',errText(e,true));});
}

// ---- approve / process ------------------------------------------------------
function openConfirm(title,body,goLabel,run){
  document.getElementById('c2-title').textContent=title;
  document.getElementById('c2-body').textContent=body;
  var go=document.getElementById('c2-go');
  go.textContent=goLabel;go.disabled=false;
  go.onclick=function(){go.disabled=true;
    setStatus('c2-status','busy','Working…');
    run().then(function(msg){successNote('c2-status',msg);})
      .catch(function(e){go.disabled=false;
        setStatus('c2-status','err',errText(e,true));});};
  setStatus('c2-status','','');
  document.getElementById('dlg-confirm').showModal();
}
function actApprove(m){
  openConfirm('Approve '+monthLabel(m),
    'This signs off the month and locks its figures. Approval is refused '+
    'automatically if anything required is still missing.',
    'Approve',function(){
      return putFile(BOOT.root+'/months/'+m+'/APPROVE_REQUESTED.txt',
        'requested '+ts()+' via Treasurer Console\n',
        'Portal: approval requested for '+m)
        .then(function(){return 'Approval requested.'});});
}
function actProcess(m){
  openConfirm('Process '+monthLabel(m),
    'Runs the month through the oversight system with everything '+
    'currently uploaded.','Process',function(){
      return putFile(BOOT.root+'/months/'+m+'/inputs/.process-'+ts()+'.txt',
        'process requested via Treasurer Console\n',
        'Portal: process '+m)
        .then(function(){return 'Processing requested.'});});
}

// ---- note action ------------------------------------------------------------
var noteMonth=null;
function openNote(btn){noteMonth=btn.getAttribute('data-month');
  document.getElementById('n-text').value='';
  setStatus('n-status','','');
  document.getElementById('dlg-note').showModal();}
function doNote(){
  var t=document.getElementById('n-text').value.trim();
  if(!t){setStatus('n-status','err','Write the note first.');return;}
  var btn=document.getElementById('n-send');btn.disabled=true;
  putFile(BOOT.root+'/months/'+noteMonth+'/notes/note-'+ts()+'.md',
    '# Treasurer note — '+noteMonth+'\n\n'+t+'\n',
    'Portal note for '+noteMonth)
    .then(function(){btn.disabled=false;
      setStatus('n-status','ok','✓ Saved. Claude reads these when working '+
        'on the oversight records.');})
    .catch(function(e){btn.disabled=false;
      setStatus('n-status','err',errText(e,true));});
}

// ---- check for updates ------------------------------------------------------
function actCheckLatest(){
  openConfirm('Check for updates','Fetches the latest processed results '+
    'from the oversight records and reloads this console if newer data '+
    'is available.','Check now',function(){
      return getRaw(BOOT.root+'/dashboard/console.html').then(function(t){
        var i=t.indexOf('<title>');
        if(i<0)throw {code:'tool_error',message:'latest console unreadable'};
        var html=t.slice(i);
        var m=html.match(/snapshot ([0-9a-f]{7,12})/);
        if(m&&BOOT.snapshot&&m[1]===BOOT.snapshot)
          return 'You already have the latest data.';
        document.open();document.write(html);document.close();
        return 'Loaded the latest console.';});});
}

// ---- shared UI plumbing -----------------------------------------------------
function monthLabel(m){
  var d=new Date(m+'-01T00:00:00');
  return d.toLocaleString('en-US',{month:'long',year:'numeric'});}
document.addEventListener('change',function(e){
  if(e.target.id==='u-files'){
    upCtx.files=Array.prototype.slice.call(e.target.files);renderUList();}
});
document.addEventListener('click',function(e){
  var cb=e.target.closest('.cur-btn');
  if(cb){CUR=cb.getAttribute('data-cur');
    localStorage.setItem('kvfos-cur',CUR);applyCur();return;}
  var tb=e.target.closest('.tab');
  if(tb){switchTab(tb.getAttribute('data-tab'));return;}
  var cl=e.target.closest('[data-close]');
  if(cl){cl.closest('dialog').close();return;}
  var wz=e.target.closest('[data-wizard]');
  if(wz){document.getElementById('wizard').showModal();return;}
  var go=e.target.closest('[data-goto]');
  if(go){var id=go.getAttribute('data-goto');
    var pane=document.querySelector('.tabpane [id="'+id+'"]');
    if(pane){switchTab(pane.closest('.tabpane').getAttribute('data-pane'));
      pane.scrollIntoView({behavior:'smooth',block:'start'});}
    return;}
  var act=e.target.closest('[data-act]');
  if(act){
    var wd=document.getElementById('wizard');
    if(wd&&wd.open&&act.closest('#wizard'))wd.close();
    var a=act.getAttribute('data-act');
    if(a==='upload')openUpload(act);
    else if(a==='accept')openAccept(act);
    else if(a==='approve')actApprove(act.getAttribute('data-month'));
    else if(a==='process')actProcess(act.getAttribute('data-month'));
    else if(a==='note')openNote(act);
    else if(a==='checklatest')actCheckLatest();
    return;}
  if(e.target.id==='u-send'){doUpload();return;}
  if(e.target.id==='a-send'){doAccept();return;}
  if(e.target.id==='n-send'){doNote();return;}
  var h=e.target.closest('.hit');
  if(h){showTip(h,e.clientX,e.clientY);}else{hideTip();}
});
function switchTab(t){
  document.querySelectorAll('.tab').forEach(function(x){
    x.classList.toggle('active',x.getAttribute('data-tab')===t);});
  document.querySelectorAll('.tabpane').forEach(function(p){
    p.classList.toggle('active',p.getAttribute('data-pane')===t);});
}
var tip=document.getElementById('tip');
function tipText(h){
  return h.getAttribute('data-tip-'+CUR)||h.getAttribute('data-tip')||'';}
function showTip(h,x,y){
  var t=tipText(h);if(!t){hideTip();return;}
  tip.textContent=t;tip.style.opacity='1';
  var px=Math.min(x+14,window.innerWidth-tip.offsetWidth-8);
  var py=Math.min(y+14,window.innerHeight-tip.offsetHeight-8);
  tip.style.left=px+'px';tip.style.top=py+'px';}
function hideTip(){tip.style.opacity='0'}
document.addEventListener('mousemove',function(e){
  var h=e.target.closest('.hit');
  if(h&&tipText(h)){showTip(h,e.clientX,e.clientY)}else{hideTip()}
});
applyCur();
})();
"""


def generate(root: Path, out: Path | None = None) -> Path:
    data = gather(Path(root))
    out = out or Path(root) / "dashboard" / "console.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    return out
