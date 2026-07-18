"""Treasurer Console — self-contained HTML dashboard generator.

Renders the orchestration + analytics console from the repo's current
state (months/*/derived, knowledge/). Output is one static HTML file:
inline CSS/SVG, no external requests, both themes, treasurer-level
detail (named vendors allowed, payroll only as category totals — SPEC §8).

Regenerate any time with:  python -m kvfos dashboard
"""

from __future__ import annotations

import html
import json
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
            "documents": _j(d / "derived" / "documents.json")
                          or _j(d / "documents.json") or [],
        })
    current_period = f"{today.year}-{today.month:02d}"
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                cwd=root, capture_output=True, text=True,
                                timeout=5).stdout.strip() or None
    except Exception:
        commit = None
    return {
        "k": k, "months": months, "today": today.isoformat(),
        "current_period": current_period, "commit": commit,
        "generated": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
    }


NEXT_ACTION = {
    "awaiting_inputs": ("Collect the month's documents",
                        "python -m kvfos init-month {m}"),
    "inputs_ready": ("Run the monthly close",
                     "python -m kvfos close --month {m}"),
    "stale_inputs_changed": ("Inputs changed — re-run the close",
                             "python -m kvfos close --month {m}"),
    "closed": ("Review the Treasurer Report, then approve",
               "python -m kvfos approve --month {m}"),
    "approved": ("Nothing — month is locked", ""),
}

CHIP = {  # status chips: icon + label, color never alone
    "awaiting_inputs": ("chip-neutral", "⏰", "Awaiting inputs"),
    "inputs_ready": ("chip-accent", "▶", "Ready to close"),
    "stale_inputs_changed": ("chip-warning", "↻", "Stale — re-close"),
    "closed": ("chip-accent", "☑", "Closed — review"),
    "approved": ("chip-good", "✓", "Approved"),
    "blocked": ("chip-critical", "⛔", "Blocked"),
}

STEPS = ["Collect", "Close", "Review", "Approve"]
STEP_OF = {"awaiting_inputs": 0, "inputs_ready": 1,
           "stale_inputs_changed": 1, "closed": 2, "approved": 3}


def _fmt_uah(v) -> str:
    return f"₴{money(v):,.0f}"


def _fmt_usd(v) -> str:
    return f"${money(v):,.0f}"


# ---------------------------------------------------------------------------
# SVG charts (light/dark via CSS classes on tokens)

def _bar_chart_months(months: list[dict]) -> str:
    """Grouped bars: income vs expenses per closed month. Two series —
    legend + direct labels (relief for the sub-3:1 yellow)."""
    closed = [m for m in months if m["analysis"]]
    if not closed:
        return "<p class='empty'>No closed months yet.</p>"
    W, H, pad_l, pad_b, pad_t = 640, 240, 8, 26, 14
    n = len(closed)
    peak = max(max(Decimal(m["analysis"]["financial"]["income_uah"]),
                   Decimal(m["analysis"]["financial"]["expenses_uah"]))
               for m in closed) or Decimal(1)
    group_w = (W - pad_l * 2) / max(n, 4)
    bar_w = min(44.0, group_w / 2.6)
    plot_h = H - pad_b - pad_t
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Income vs expenses by month" class="chart">']
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = H - pad_b - plot_h * frac
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_l}" '
                     f'y2="{y:.1f}" class="grid"/>')
    parts.append(f'<line x1="{pad_l}" y1="{H - pad_b}" x2="{W - pad_l}" '
                 f'y2="{H - pad_b}" class="axis"/>')
    for i, m in enumerate(closed):
        fin = m["analysis"]["financial"]
        cx = pad_l + group_w * i + group_w / 2
        for si, (key, cls) in enumerate((("income_uah", "s1"),
                                         ("expenses_uah", "s2"))):
            v = Decimal(fin[key])
            h = float(v / peak) * plot_h
            x = cx - bar_w - 1 + si * (bar_w + 2)   # 2px surface gap
            y = H - pad_b - h
            label = _fmt_uah(v)
            parts.append(
                f'<g class="hit" data-tip="{E(m["month"])} · '
                f'{"Income" if si == 0 else "Expenses"}: {E(label)}">'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                f'height="{h:.1f}" rx="4" class="{cls}"/>'
                f'<text x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" '
                f'class="val" text-anchor="middle">{E(label)}</text></g>')
        parts.append(f'<text x="{cx:.1f}" y="{H - 8}" class="tick" '
                     f'text-anchor="middle">{E(m["month"])}</text>')
    parts.append("</svg>")
    legend = ('<div class="legend"><span><i class="dot s1"></i>Income</span>'
              '<span><i class="dot s2"></i>Expenses</span></div>')
    return legend + "".join(parts)


def _bar_chart_categories(k: Knowledge, latest: dict) -> str:
    """Horizontal bars, colored by group (program/admin/taxes)."""
    fin = latest["analysis"]["financial"]
    cats = list(fin["by_category"].items())[:8]
    if not cats:
        return "<p class='empty'>No expenses recorded.</p>"
    peak = max(Decimal(a["uah"]) for _, a in cats)
    rows = []
    group_cls = {"program": "s1", "administration": "s2", "taxes": "s3"}
    for cid, a in cats:
        w = float(Decimal(a["uah"]) / peak) * 100
        cls = group_cls.get(k.category_group.get(cid, ""), "sneutral")
        rows.append(
            f'<div class="hbar hit" data-tip="{E(a["label"])}: '
            f'{E(_fmt_uah(a["uah"]))} ({a["count"]} txns)">'
            f'<span class="hbar-label">{E(a["label"])}</span>'
            f'<span class="hbar-track"><span class="hbar-fill {cls}" '
            f'style="width:{w:.1f}%"></span></span>'
            f'<span class="hbar-val">{E(_fmt_uah(a["uah"]))}</span></div>')
    legend = ('<div class="legend"><span><i class="dot s1"></i>Program</span>'
              '<span><i class="dot s2"></i>Administration</span>'
              '<span><i class="dot s3"></i>Taxes</span></div>')
    return legend + '<div class="hbars">' + "".join(rows) + "</div>"


def _split_bar(latest: dict) -> str:
    fin = latest["analysis"]["financial"]
    parts = [("Program", Decimal(fin["program_uah"]), "s1"),
             ("Administration", Decimal(fin["admin_uah"]), "s2"),
             ("Taxes", Decimal(fin["taxes_uah"]), "s3")]
    total = sum(p[1] for p in parts) or Decimal(1)
    # integer percentages that sum to exactly 100 (largest remainder)
    exact = [float(v / total) * 100 for _, v, _ in parts]
    ints = [int(x) for x in exact]
    for i in sorted(range(len(exact)), key=lambda i: exact[i] - ints[i],
                    reverse=True)[: 100 - sum(ints)]:
        ints[i] += 1
    segs, labels = [], []
    for (name, v, cls), pct, ipct in zip(parts, exact, ints):
        if pct <= 0:
            continue
        segs.append(f'<span class="seg {cls} hit" style="width:{pct:.2f}%" '
                    f'data-tip="{name}: {E(_fmt_uah(v))} ({ipct}%)"></span>')
        labels.append(f'<span><i class="dot {cls}"></i>{name} '
                      f'<b>{ipct}%</b></span>')
    return ('<div class="stack">' + "".join(segs) + "</div>"
            '<div class="legend">' + "".join(labels) + "</div>")


# ---------------------------------------------------------------------------
# panels

def _summary_tiles(data: dict, focus: dict | None, latest: dict | None) -> str:
    k: Knowledge = data["k"]
    tiles = []
    if focus:
        cls, icon, label = CHIP[focus["status"]]
        tiles.append(f'<div class="tile"><div class="tile-k">Focus month</div>'
                     f'<div class="tile-v">{E(focus["month"])}</div>'
                     f'<div class="chip {cls}">{icon} {label}</div></div>')
    else:
        tiles.append('<div class="tile"><div class="tile-k">Focus month</div>'
                     '<div class="tile-v">—</div>'
                     '<div class="chip chip-good">✓ All months approved</div></div>')
    if latest and latest["confidence"]:
        c = latest["confidence"]
        band = {"LOW": "chip-good", "MEDIUM": "chip-warning",
                "HIGH": "chip-critical"}[c["risk"]]
        tiles.append(f'<div class="tile"><div class="tile-k">Confidence · '
                     f'{E(latest["month"])}</div>'
                     f'<div class="tile-v hero">{c["overall"]}<small>/100</small></div>'
                     f'<div class="chip {band}">Risk {c["risk"]}</div></div>')
    if latest and latest["reconciliation"]:
        total = Decimal("0")
        for a in latest["reconciliation"]["accounts"]:
            if a["book_closing"]:
                total += Decimal(a["book_closing"])
        fx = k.fx_rate(f"{latest['month']}-28")
        usd = f" · ≈{_fmt_usd(total / fx[0])}" if fx else ""
        tiles.append(f'<div class="tile"><div class="tile-k">Cash · end of '
                     f'{E(latest["month"])}</div>'
                     f'<div class="tile-v">{E(_fmt_uah(total))}</div>'
                     f'<div class="tile-s">{E(usd.lstrip(" ·"))} across '
                     f'{len(latest["reconciliation"]["accounts"])} accounts</div></div>')
    if latest:
        n_open = sum(1 for f in latest["exceptions"] if f["status"] == "open")
        n_auto = sum(1 for f in latest["exceptions"]
                     if f["status"] == "auto_explained")
        blocking = sum(1 for g in latest["gaps"] if g["severity"] == "blocking")
        cls = ("chip-good" if n_open == 0 and blocking == 0 else
               "chip-critical" if blocking else "chip-warning")
        icon = "✓" if cls == "chip-good" else "⚠"
        tiles.append(f'<div class="tile"><div class="tile-k">To review · '
                     f'{E(latest["month"])}</div>'
                     f'<div class="tile-v">{n_open}<small> open</small></div>'
                     f'<div class="chip {cls}">{icon} {blocking} blocking gaps · '
                     f'{n_auto} auto-explained</div></div>')
    return '<section class="tiles">' + "".join(tiles) + "</section>"


def _now_panel(data: dict, focus: dict | None) -> str:
    k: Knowledge = data["k"]
    if focus is None:
        m = data["current_period"]
        body = (f'<p>All finished months are approved. The current period '
                f'<b>{E(m)}</b> is still in progress — collect documents as '
                f'they arrive; it appears here for closing once the month ends '
                f'(reminder issue opens on the 1st).</p>'
                + _cmd_block(f"python -m kvfos init-month {m}"))
        return _card("Now", "What needs the Treasurer", body)
    m = focus["month"]
    step = STEP_OF[focus["status"]]
    stepper = "".join(
        f'<li class="{"done" if i < step else "cur" if i == step else ""}">'
        f'<i></i>{s}</li>' for i, s in enumerate(STEPS))
    checklist = ""
    if focus["status"] in ("awaiting_inputs", "inputs_ready",
                           "stale_inputs_changed"):
        wanted = ([("Accounting workbook", f"workbook_{m}.xlsx")]
                  + [(f"Bank statement — {a['name']}", f"bank_{a['id']}_{m}.csv")
                     for a in k.active_accounts()]
                  + [("Center statistics", f"CenterUpdates_{m}.csv")])
        inputs_dir = k.root / "months" / m / "inputs"
        have = ({p.name for p in inputs_dir.iterdir()}
                if inputs_dir.exists() else set())
        items = "".join(
            f'<li class="{"have" if fn in have else "need"}">'
            f'<b>{"✓" if fn in have else "○"}</b> {E(label)} '
            f'<code>{E(fn)}</code></li>' for label, fn in wanted)
        checklist = f'<ul class="checklist">{items}</ul>'
    gaps_html = ""
    blocking = [g for g in focus["gaps"] if g["severity"] == "blocking"]
    if blocking:
        gaps_html = "".join(
            f'<div class="gap critical"><b>{E(g["title"])}</b>'
            f'<p>{E(g["action"])}</p></div>' for g in blocking)
    title, cmd = NEXT_ACTION[focus["status"]]
    body = (f'<ol class="stepper">{stepper}</ol>{checklist}{gaps_html}'
            f'<p class="next"><span class="eyebrow">Next action</span> '
            f'{E(title)}</p>' + (_cmd_block(cmd.format(m=m)) if cmd else ""))
    return _card("Now", f"{m} — what needs the Treasurer", body)


def _pipeline_board(data: dict) -> str:
    cards = []
    for m in data["months"]:
        cls, icon, label = CHIP[m["status"]]
        conf = (f'{m["confidence"]["overall"]}/100'
                if m["confidence"] else "—")
        n_open = sum(1 for f in m["exceptions"] if f["status"] == "open")
        _, cmd = NEXT_ACTION[m["status"]]
        cards.append(
            f'<div class="mcard"><div class="mcard-head"><b>{E(m["month"])}</b>'
            f'<span class="chip {cls}">{icon} {label}</span></div>'
            f'<div class="mcard-body">Confidence {conf} · {n_open} open '
            f'exceptions</div>'
            + (_cmd_block(cmd.format(m=m["month"]), small=True) if cmd else "")
            + "</div>")
    cp = data["current_period"]
    if all(m["month"] != cp for m in data["months"]):
        cards.append(
            f'<div class="mcard ghost"><div class="mcard-head"><b>{E(cp)}</b>'
            f'<span class="chip chip-neutral">◌ In progress</span></div>'
            f'<div class="mcard-body">Current period — closes after month-end; '
            f'reminder issue opens on the 1st.</div></div>')
    return _card("Month pipeline", "Every month since oversight began",
                 f'<div class="mgrid">{"".join(cards)}</div>')


_RES_TMPL = """\
# append to kv-fos/knowledge/learned/resolutions.yaml
  - rule: {rule}
    # vendor: <vendor_id>   # optional: scope to one vendor
    explanation: "<why this is expected — shown on future findings>"
    accepted: "{today}"
    by: treasurer"""

_ALIAS_TMPL = """\
# append to kv-fos/knowledge/learned/vendor_aliases.yaml (existing vendor)
  - alias: "{name}"
    vendor: <existing_vendor_id>
    confirmed: "{today}"
    by: treasurer
# — or add a new vendor entry to kv-fos/knowledge/vendors.yaml"""


def _exception_queue(data: dict, latest: dict | None) -> str:
    if not latest:
        return ""
    sev_cls = {"high": "critical", "medium": "serious", "low": "warning"}
    open_f = [f for f in latest["exceptions"] if f["status"] == "open"]
    auto = [f for f in latest["exceptions"] if f["status"] == "auto_explained"]
    cards = []
    for f in open_f:
        ev = "".join(f'<code>{E(e.get("file", ""))} {E(e.get("locator", ""))}'
                     f'</code>' for e in f["evidence"][:3])
        if f["rule"] == "new_vendor":
            name = f["title"].split(":", 1)[-1].strip()
            snippet = _ALIAS_TMPL.format(name=name, today=data["today"])
            teach = "Confirm this vendor"
        else:
            snippet = _RES_TMPL.format(rule=f["rule"], today=data["today"])
            teach = "Accept as expected"
        cards.append(
            f'<div class="finding {sev_cls[f["severity"]]}">'
            f'<div class="finding-head"><span class="sev">'
            f'{E(f["severity"].upper())}</span>'
            f'<span class="rule">{E(f["rule"].replace("_", " "))}</span></div>'
            f'<b>{E(f["title"])}</b><p>{E(f["explanation"])}</p>'
            f'{f"<div class=refs>{ev}</div>" if ev else ""}'
            f'<details><summary>{E(teach)} — copy the YAML</summary>'
            f'<div class="cmd"><pre>{E(snippet)}</pre>'
            f'<button class="copy" data-copy="{E(snippet)}">Copy</button>'
            f'</div></details></div>')
    auto_html = ""
    if auto:
        rows = "".join(f'<li>✓ {E(f["title"])} — <i>{E(f["resolution"] or "")}'
                       f'</i></li>' for f in auto)
        auto_html = (f'<details class="auto"><summary>{len(auto)} auto-explained '
                     f'by the knowledge base</summary><ul>{rows}</ul></details>')
    body = ((f'<div class="findings">{"".join(cards)}</div>' if cards else
             '<p class="allclear">✓ No open exceptions — nothing needs review.</p>')
            + auto_html)
    return _card("Exception queue",
                 f'{latest["month"]} — work top-down, teach as you go', body)


def _gaps_panel(latest: dict | None) -> str:
    if not latest or not latest["gaps"]:
        return ""
    sev_cls = {"blocking": "critical", "material": "serious", "info": "neutral"}
    rows = "".join(
        f'<div class="gap {sev_cls[g["severity"]]}">'
        f'<span class="sev">{E(g["severity"].upper())}</span>'
        f'<b>{E(g["title"])}</b><p>{E(g["detail"])} '
        f'<b>Action:</b> {E(g["action"])}</p></div>'
        for g in latest["gaps"])
    return _card("Data gaps", f'{latest["month"]} — fix, re-upload, re-run '
                 "(reprocessing never duplicates)", rows)


def _traces_panel(latest: dict | None) -> str:
    if not latest or not latest["traces"]:
        return ""
    rows = []
    for t in latest["traces"]:
        dots = "".join(
            f'<span class="tdot {"ok" if l["status"] == "matched" else "miss"} hit" '
            f'data-tip="{E(l["step"].replace("_", " "))}: {E(l["status"])} — '
            f'{E(l["detail"][:90])}"></span>' for l in t["links"])
        state = ("chip-good\">✓ complete" if t["chain_complete"] else
                 "chip-warning\">⚠ incomplete")
        rows.append(f'<div class="trace"><b>{E(t["transfer_id"])}</b>'
                    f'<span class="amt">{E(_fmt_usd(t["amount_usd"]))}</span>'
                    f'<span class="tdots">{dots}</span>'
                    f'<span class="chip {state}</span></div>')
    return _card("US transfer traceability",
                 f'{latest["month"]} — request → Wise → bank → books',
                 "".join(rows) + '<p class="hint">Each dot is one link of the '
                 'chain — hover for detail.</p>')


def _analytics(data: dict, latest: dict | None) -> str:
    if not latest or not latest["analysis"]:
        return ""
    k = data["k"]
    ops = latest["analysis"]["operational"]
    t = ops["totals"]
    ue = ops["unit_economics"]
    impact = "".join(
        f'<div class="tile sm"><div class="tile-k">{E(lbl)}</div>'
        f'<div class="tile-v">{E(str(v))}</div></div>'
        for lbl, v in (("Children served", t["children_served"]),
                       ("Consultations", t["consultations"]),
                       ("Classes", t["classes"]),
                       ("New children", t["new_children"]),
                       ("Cost / child", "₴" + (ue["cost_per_child_served_uah"] or "—")),
                       ("Cost / class", "₴" + (ue["cost_per_class_uah"] or "—"))))
    return (
        _card("Income vs expenses", "By month, UAH — both series direct-labeled",
              _bar_chart_months(data["months"]))
        + _card("Where the money went",
                f'{latest["month"]} — colored by group',
                _bar_chart_categories(k, latest))
        + _card("Program share", f'{latest["month"]} — of total spending',
                _split_bar(latest))
        + _card("Impact", f'{latest["month"]} — program metrics '
                "(unit costs are Estimated; method in the Treasurer Report)",
                f'<section class="tiles">{impact}</section>'))


def _card(eyebrow: str, title: str, body: str) -> str:
    return (f'<section class="card"><header><span class="eyebrow">{E(eyebrow)}'
            f'</span><h2>{E(title)}</h2></header>{body}</section>')


def _cmd_block(cmd: str, small: bool = False) -> str:
    return (f'<div class="cmd{" sm" if small else ""}"><pre>{E(cmd)}</pre>'
            f'<button class="copy" data-copy="{E(cmd)}">Copy</button></div>')


# ---------------------------------------------------------------------------
# page

def render(data: dict) -> str:
    months = data["months"]
    latest = next((m for m in reversed(months) if m["analysis"]), None)
    focus = next((m for m in months if m["status"] != "approved"), None)
    body = (
        _masthead(data)
        + _summary_tiles(data, focus, latest)
        + '<div class="cols"><div class="col-main">'
        + _now_panel(data, focus)
        + _exception_queue(data, latest)
        + _gaps_panel(latest)
        + '</div><div class="col-side">'
        + _pipeline_board(data)
        + _traces_panel(latest)
        + "</div></div>"
        + _analytics(data, latest)
        + _footer(data)
    )
    return ("<title>KV Treasurer Console</title>\n"
            f"<style>{_CSS}</style>\n"
            f'<main class="wrap">{body}</main>\n'
            f"<div id='tip' role='tooltip'></div>\n"
            f"<script>{_JS}</script>")


def _masthead(data: dict) -> str:
    stamp = f'Data as of {E(data["generated"])}'
    if data["commit"]:
        stamp += f' · commit {E(data["commit"])}'
    return (f'<header class="mast"><div class="mast-brand">'
            f'<span class="mast-mark">KV</span>'
            f'<span class="mast-org">Friends of Kinder Velt USA · '
            f'Financial Oversight</span></div>'
            f'<h1>Treasurer Console</h1>'
            f'<p class="mast-stamp">{stamp}</p></header>')


def _footer(data: dict) -> str:
    return (
        '<footer class="foot"><p><b>To refresh this console:</b> after any '
        'close or approval, run <code>python -m kvfos dashboard</code> and '
        'republish <code>kv-fos/dashboard/dashboard.html</code> (or ask '
        'Claude to regenerate and republish it). Every figure here is a '
        'snapshot of the repo at the commit above — the reports remain the '
        'authoritative record.</p>'
        '<p>The confidence score is an aid to the Treasurer’s review, '
        'not an audit opinion (SPEC §11). Payroll appears only as category '
        'totals (SPEC §8).</p></footer>')


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
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 48px;display:flex;
flex-direction:column;gap:20px}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
font-size:.86em}
h1,h2{margin:0;text-wrap:balance}
.eyebrow{display:block;font-size:11px;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;color:var(--accent)}
.mast{padding:26px 0 4px;border-bottom:3px solid var(--brand-yellow)}
.mast-brand{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.mast-mark{background:var(--accent);color:var(--accent-ink);font-weight:800;
padding:3px 8px;border-radius:4px;letter-spacing:.04em}
.mast-org{font-size:12px;font-weight:600;letter-spacing:.06em;
text-transform:uppercase;color:var(--ink-2)}
.mast h1{font-size:30px;font-weight:800;letter-spacing:-.01em}
.mast-stamp{margin:6px 0 14px;color:var(--ink-3);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:12px}
.tile{background:var(--surface);border:1px solid var(--hair);border-radius:8px;
padding:14px 16px;display:flex;flex-direction:column;gap:6px}
.tile.sm{padding:10px 12px}
.tile-k{font-size:11px;font-weight:700;letter-spacing:.07em;
text-transform:uppercase;color:var(--ink-3)}
.tile-v{font-size:24px;font-weight:800;font-variant-numeric:tabular-nums}
.tile-v.hero{font-size:34px}
.tile-v small{font-size:.5em;font-weight:600;color:var(--ink-3)}
.tile-s{font-size:12px;color:var(--ink-2)}
.cols{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:20px}
@media(max-width:840px){.cols{grid-template-columns:1fr}}
.col-main,.col-side{display:flex;flex-direction:column;gap:20px;min-width:0}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:10px;
padding:18px 20px}
.card>header{margin-bottom:12px}
.card h2{font-size:17px;font-weight:700;margin-top:2px}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;
font-weight:700;padding:2px 9px;border-radius:99px;width:max-content}
.chip-good{background:color-mix(in srgb,var(--good) 14%,transparent);color:var(--good-text)}
.chip-warning{background:color-mix(in srgb,var(--warn) 20%,transparent);color:var(--ink)}
.chip-critical{background:color-mix(in srgb,var(--crit) 14%,transparent);color:var(--crit)}
.chip-accent{background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent)}
.chip-neutral{background:var(--surface-2);color:var(--ink-2)}
.stepper{display:flex;gap:0;list-style:none;margin:0 0 14px;padding:0}
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
.checklist{list-style:none;margin:0 0 12px;padding:0;display:flex;
flex-direction:column;gap:6px}
.checklist li{font-size:13px;color:var(--ink-2)}
.checklist li b{font-weight:800;margin-right:4px}
.checklist li.have b{color:var(--good-text)}
.checklist li.need b{color:var(--ink-3)}
.checklist code{background:var(--surface-2);padding:1px 6px;border-radius:4px}
.next{margin:10px 0 6px;font-weight:600}
.cmd{display:flex;align-items:stretch;gap:8px;background:var(--surface-2);
border:1px solid var(--hair);border-radius:6px;padding:8px 10px;
margin-top:8px;overflow-x:auto}
.cmd pre{margin:0;flex:1;white-space:pre;align-self:center}
.cmd.sm{padding:5px 8px;font-size:12px}
.copy{border:1px solid var(--hair);background:var(--surface);color:var(--accent);
font-weight:700;font-size:12px;border-radius:5px;padding:4px 10px;cursor:pointer}
.copy:hover{background:var(--accent);color:var(--accent-ink)}
.copy:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.mgrid{display:flex;flex-direction:column;gap:10px}
.mcard{border:1px solid var(--hair);border-radius:8px;padding:10px 12px;
background:var(--surface)}
.mcard.ghost{border-style:dashed;color:var(--ink-2)}
.mcard-head{display:flex;justify-content:space-between;align-items:center;gap:8px}
.mcard-body{font-size:12px;color:var(--ink-2);margin-top:4px;
font-variant-numeric:tabular-nums}
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
details summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--accent)}
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
.trace{display:flex;align-items:center;gap:10px;padding:8px 0;
border-bottom:1px solid var(--line);flex-wrap:wrap}
.trace:last-of-type{border-bottom:0}
.trace .amt{font-variant-numeric:tabular-nums;color:var(--ink-2)}
.tdots{display:flex;gap:6px;flex:1}
.tdot{width:14px;height:14px;border-radius:50%;display:inline-block}
.tdot.ok{background:var(--good)}
.tdot.miss{background:var(--surface-2);border:2px dashed var(--crit)}
.hint{font-size:12px;color:var(--ink-3);margin:8px 0 0}
.chart{width:100%;height:auto;display:block}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .axis{stroke:var(--ink-3);stroke-width:1}
.chart .s1,.hbar-fill.s1,.seg.s1,.dot.s1{fill:var(--s1);background:var(--s1)}
.chart .s2,.hbar-fill.s2,.seg.s2,.dot.s2{fill:var(--s2);background:var(--s2)}
.hbar-fill.s3,.seg.s3,.dot.s3{background:var(--s3)}
.hbar-fill.sneutral{background:var(--sneutral)}
.chart .val{fill:var(--ink-2);font-size:11px;font-variant-numeric:tabular-nums}
.chart .tick{fill:var(--ink-3);font-size:11px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);
margin-bottom:10px}
.legend .dot{width:10px;height:10px;border-radius:3px;display:inline-block;
margin-right:5px;vertical-align:-1px}
.hbars{display:flex;flex-direction:column;gap:7px}
.hbar{display:grid;grid-template-columns:150px 1fr 90px;gap:10px;
align-items:center;font-size:13px}
.hbar-label{color:var(--ink-2);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}
.hbar-track{background:var(--surface-2);border-radius:4px;height:16px;
overflow:hidden}
.hbar-fill{display:block;height:100%;border-radius:4px 0 0 4px}
.hbar-val{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink)}
@media(max-width:560px){.hbar{grid-template-columns:110px 1fr 80px}}
.stack{display:flex;gap:2px;height:26px;border-radius:6px;overflow:hidden;
margin-bottom:10px}
.seg{display:block;height:100%}
.empty{color:var(--ink-3)}
.foot{border-top:1px solid var(--line);padding-top:14px;font-size:12.5px;
color:var(--ink-3)}
.foot code{background:var(--surface-2);padding:1px 5px;border-radius:4px}
#tip{position:fixed;z-index:10;background:var(--tip-bg);color:var(--tip-ink);
font-size:12px;font-weight:600;padding:5px 9px;border-radius:5px;
pointer-events:none;opacity:0;transition:opacity .1s;max-width:300px}
@media(prefers-reduced-motion:reduce){#tip{transition:none}}
"""

_JS = """
document.addEventListener('click',function(e){
  var b=e.target.closest('.copy'); if(!b)return;
  var t=b.getAttribute('data-copy');
  function done(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1400)}
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).then(done,function(){fallback()})
  }else{fallback()}
  function fallback(){var ta=document.createElement('textarea');ta.value=t;
    document.body.appendChild(ta);ta.select();
    try{document.execCommand('copy');done()}catch(err){}
    document.body.removeChild(ta)}
});
var tip=document.getElementById('tip');
document.addEventListener('mousemove',function(e){
  var h=e.target.closest('.hit');
  if(h&&h.getAttribute('data-tip')){
    tip.textContent=h.getAttribute('data-tip');
    tip.style.opacity='1';
    var x=Math.min(e.clientX+14,window.innerWidth-tip.offsetWidth-8);
    var y=Math.min(e.clientY+14,window.innerHeight-tip.offsetHeight-8);
    tip.style.left=x+'px';tip.style.top=y+'px';
  }else{tip.style.opacity='0'}
});
"""


def generate(root: Path, out: Path | None = None) -> Path:
    data = gather(Path(root))
    out = out or Path(root) / "dashboard" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    return out
