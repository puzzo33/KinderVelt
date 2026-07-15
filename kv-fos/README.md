# KV-FOS — Kinder Velt Financial Oversight System

Working implementation of [SPEC.md](SPEC.md): a knowledge-based oversight
system with persistent financial memory. It reconciles the Ukrainian
accountant's books, bank statements, US Wise transfers and program metrics
into board-ready monthly reports — and it learns your vendors, baselines
and recurring anomalies as months accumulate.

## The monthly cycle (Treasurer runbook)

**0. You get reminded.** On the 1st of each month a GitHub issue
("KV-FOS monthly oversight reminder") lists every month that still needs
attention and what state it's in. Locally, the same thing:

```bash
python -m kvfos remind
```

**1. Collect the documents.** Create the month folder and drop the files in:

```bash
python -m kvfos init-month 2026-07     # creates months/2026-07/inputs/ + checklist
```

Required (SPEC §6.1) — the close is *degraded* without them:

| File | Naming convention | Formats |
|---|---|---|
| Accounting workbook | `workbook_2026-07.xlsx` | Excel with `GeneralLedger`, `Balances`, `PayrollRegister`, `ChartOfAccounts` sheets (UA/EN headers both fine) |
| Bank statements (every active account) | `bank_<account>_2026-07.csv` | CSV / Excel / text-PDF |
| Center statistics | `CenterUpdates_2026-07.csv` | CSV / YAML / text-PDF |

Optional (SPEC §6.2): `wise_2026-07.csv` transfer confirmations, funding
request letters, invoices. The system only asks for optional documents
when they would actually improve reconciliation.

If a filename doesn't match the conventions, list it in
`inputs/manifest.yaml`:

```yaml
files:
  "vypiska-cherven.pdf": { type: bank_statement, account: privat_uah }
```

**2. Run the close.** Push the files (the `KV-FOS process month` workflow
runs automatically and commits reports back), or run locally:

```bash
python -m kvfos close --month 2026-07
```

**3. Review — the 15-minute path.** Open
`months/2026-07/reports/02_treasurer_report.md`: confidence score first,
then open exceptions, then variances. Everything else is drill-down.

**4. Fix gaps / re-upload.** `months/2026-07/GAPS.md` lists exactly what's
missing and what to do. Replace or add files in `inputs/` and re-run the
close. **Reprocessing is idempotent**: documents are content-addressed,
transaction ids are deterministic, and each close rebuilds the month from
scratch — replaced files supersede their predecessors and nothing ever
duplicates, no matter how many times you re-run.

**5. Teach it.** Resolve exceptions permanently in `knowledge/learned/`:

- New vendor confirmed? Add the alias to `learned/vendor_aliases.yaml` —
  it will match automatically forever.
- Benign recurring anomaly (annual insurance, payroll size)? Add it to
  `learned/resolutions.yaml` — equivalent future findings arrive
  auto-explained instead of open.

**6. Approve & lock.**

```bash
python -m kvfos approve --month 2026-07
```

Approval requires zero blocking gaps and freezes the month (SPEC §9.8).
If the accountant later restates it, re-run with `--amend`: you get an
`AMENDMENT.md` delta against the approved figures; nothing is silently
rewritten.

## Monthly outputs (per SPEC §10)

| File | Audience |
|---|---|
| `reports/01_executive_summary.md` | One page: income, expenses, cash, risks |
| `reports/02_treasurer_report.md` | Full reconciliation, exceptions, variances, named payroll allowed |
| `reports/03_board_report.md` | Board — simple, no jargon |
| `reports/04_donor_transparency_report.md` | Public **draft** — edit the narrative before publishing; aggregates only |
| `reports/05_trace_cards.md` | Every US transfer traced request → deposit → books |
| `registry/master_register.csv` | Every transaction ever, with source refs (repo-wide, cumulative) |
| `GAPS.md` | What's missing + exact re-upload instructions |

Every figure carries its source (`file` + sheet/row locator) — that's the
audit trail (SPEC §10.6): no summary number without traceability.

## Configuration (the knowledge base)

All under `knowledge/` — plain YAML, versioned by git, no code changes needed:

- `organization.yaml` — centers, bank accounts, start month
- `vendors.yaml` — vendor master (canonical name, aliases, expected ranges)
- `categories.yaml` — expense taxonomy + chart-of-accounts mapping
- `materiality.yaml` — all thresholds (SPEC §7.5)
- `fx_rates.yaml` — NBU reference rates (realized Wise rates always win)
- `confidence.yaml` — scoring rubric (SPEC §11)
- `learned/` — the memory: aliases + accepted resolutions

## Development

```bash
pip install -r requirements.txt
python -m pytest tests -q          # 14 tests: idempotency, dedupe, gaps,
                                   # reconciliation, learning, lock/amend
python tools/make_sample_data.py   # regenerate the 2026-06 sample month
```

`months/2026-06/` is a complete worked example (synthetic data).

## Automation

- `.github/workflows/kvfos-reminder.yml` — opens the monthly reminder issue
- `.github/workflows/kvfos-process.yml` — closes a month when inputs are pushed
- `.github/workflows/kvfos-ci.yml` — test suite + knowledge-base validation
