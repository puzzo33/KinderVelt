# Treasurer Report — 2026-06

*Friends of Kinder Velt USA, Inc. — Financial Oversight System. Generated 2026-07-15 11:55 UTC.*

## Confidence: 100/100 — LOW

| Component | | Detail |
|---|---|---|
| Bank Reconciliation | ✓ | 2/2 accounts reconciled (30.00/30) |
| Transfer Matching | ✓ | 1/1 transfers traced to a bank deposit (20.00/20) |
| Expense Categorization | ✓ | 7/7 expenses confidently categorized (20.00/20) |
| Program Metrics | ✓ | 4/4 active centers reported metrics (10.00/10) |
| Supporting Documentation | ✓ | no documentation gaps (20.00/20) |

*This score is an aid to the Treasurer's review, not an audit opinion.*

## Exceptions — 5 open

### [MEDIUM] Large expense $514.35 — ТОВ Арт-Плюс

Single expense of ₴21500.00 (~$514.35) exceeds the $500 materiality threshold.

- source: `workbook_2026-06.xlsx` sheet=GeneralLedger row=8 (doc 75f3c5ce8cc6)
- transactions: Tab1f99f4f7f6
- finding id: `X0ccd72065081`

### [MEDIUM] Large expense $4312.41 — Заробітна плата

Single expense of ₴180000.00 (~$4312.41) exceeds the $500 materiality threshold.

- source: `workbook_2026-06.xlsx` sheet=GeneralLedger row=5 (doc 75f3c5ce8cc6)
- transactions: T66cf298d9f0f
- finding id: `X0fb27c107e6e`

### [MEDIUM] Large expense $1247.00 — ФОП Юриев

Single expense of ₴52000.00 (~$1247.00) exceeds the $500 materiality threshold.

- source: `workbook_2026-06.xlsx` sheet=GeneralLedger row=3 (doc 75f3c5ce8cc6)
- transactions: T9c789d912cff
- finding id: `X32239ad2cad4`

### [MEDIUM] Large expense $948.73 — ДПС України

Single expense of ₴39600.00 (~$948.73) exceeds the $500 materiality threshold.

- source: `workbook_2026-06.xlsx` sheet=GeneralLedger row=6 (doc 75f3c5ce8cc6)
- transactions: T2a0ac8b230d6
- finding id: `X99506d0d6dc0`

### [MEDIUM] New vendor: ТОВ Арт-Плюс

Counterparty “ТОВ Арт-Плюс” is not in the vendor master or learned aliases. Confirm who this is; confirming adds an alias so it is never asked again.

- source: `workbook_2026-06.xlsx` sheet=GeneralLedger row=8 (doc 75f3c5ce8cc6)
- transactions: Tab1f99f4f7f6
- finding id: `X683bbf4a40c5`


## Reconciliation

| Account | Book opening | Income | Expenses | Computed close | Book close | Bank close | Reconciled |
|---|---:|---:|---:|---:|---:|---:|---|
| oschad_uah | 100000.00 | 120.00 | 0 | 100120.00 | 100120.00 | 100120.00 | ✓ |
| privat_uah | 250000.00 | 498000.00 | -311250.00 | 436750.00 | 436750.00 | 436750.00 | ✓ |

Ledger transactions bank-matched: 9/9; unmatched bank lines: 0.

## Vendor analysis

| Vendor | UAH | USD | Txns |
|---|---:|---:|---:|
| Заробітна плата | ₴180,000.00 | $4,312.41 | 1 |
| ФОП Юриев | ₴52,000.00 | $1,247.00 | 1 |
| ДПС України | ₴39,600.00 | $948.73 | 1 |
| ТОВ Арт-Плюс | ₴21,500.00 | $514.35 | 1 |
| Р-Технопарк | ₴14,500.00 | $347.89 | 1 |
| Нова Пошта | ₴3,200.00 | $76.67 | 1 |
| ПриватБанк | ₴450.00 | $10.77 | 1 |

## Operational metrics

- Children served: 443; consultations: 181; classes: 274; new children: 25
- Cost per child served: ₴462.08; per consultation: ₴1130.94; per class: ₴747.08 *(method: program-group expenses divided by metric totals; Estimated (allocation-dependent), UAH)*

*Materiality rules v1; confidence rubric v1.*
