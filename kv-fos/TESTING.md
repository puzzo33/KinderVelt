# KV-FOS Testing Guide

Two layers: the **automated suite** (run it any time, CI runs it on every
push) and a **hands-on UAT walkthrough** that exercises the full Treasurer
lifecycle on synthetic data. Executed end-to-end on 2026-07-15; every
scenario behaved as specified.

## 1. Automated suite

```bash
pip install -r kv-fos/requirements.txt
python -m pytest kv-fos/tests -q     # 15 tests, ~1s
```

Covers: happy-path close, expected exceptions, byte-identical reprocessing,
re-upload supersession, missing-statement gap + recovery + approval refusal,
corrupt-file handling, FX-missing (no fabrication), reconciliation breaks,
duplicate payments, learned aliases, learned resolutions, lock/amend,
reminder state machine, knowledge-base validation.

## 2. UAT walkthrough (sandboxed)

Work in a scratch copy so the real repo is untouched:

```bash
export PYTHONPATH=$PWD/kv-fos
SANDBOX=$(mktemp -d)
cp -r kv-fos/knowledge kv-fos/months "$SANDBOX"/
```

### S1 — Reminder

```bash
python -m kvfos --root "$SANDBOX" remind
```

**Expect:** each unapproved month listed with its state and next action.
(In the repo, GitHub opens this as an issue on the 1st of each month.)

### S2 — Start a month

```bash
python -m kvfos --root "$SANDBOX" init-month 2026-07
```

**Expect:** `months/2026-07/inputs/CHECKLIST.md` naming every required file,
including one bank statement per active account.

### S3 — Close with messy data

Drop in a month of inputs containing deliberate problems (the executed run
planted: no Oschadbank statement; a vendor not in the master; the same
Нова Пошта payment booked twice; rent up 11.5%; no July NBU rates).

```bash
python -m kvfos --root "$SANDBOX" close --month 2026-07
python -m kvfos --root "$SANDBOX" approve --month 2026-07   # must FAIL
```

**Expect (all observed):**
- close completes but reports `reconciled: NO`, confidence drops
  (observed 62/100 HIGH), blocking gap for the missing statement
- `GAPS.md` gives per-gap re-upload instructions
- exceptions include `duplicate_payment` (high), `reconciliation_break`
  (the phantom double-entry breaks book-vs-bank closing), `new_vendor`,
  `rent_variance` (11.54% > 5% threshold), `missing_bank_statement`
- missing FX ⇒ USD figures are **Missing**, never interpolated — note
  that `large_one_time_expense` correctly *cannot* fire without USD values
- `approve` refuses with the blocking gap named, exit code 2

### S4 — Fix and re-run (the re-upload loop)

Replace the workbook with the accountant's corrected version (same
filename — content hash supersedes), add the missing statement, append the
missing rates to `knowledge/fx_rates.yaml`, re-run the same close command.

**Expect (observed):** reconciled yes, confidence 100/100, blocking gaps
gone, duplicate/unmatched findings gone, transaction count correct — and
the large-expense findings now appear because USD values exist.

### S5 — Teach it (persistent memory)

Add the confirmed vendor to `knowledge/vendors.yaml`; record accepted
explanations in `knowledge/learned/resolutions.yaml` (payroll size, tax
run, rent level, approved rent increase). Re-run the close.

**Expect (observed):** `open exceptions: 0 (+4 auto-explained)` — the
auto-explained items appear in the Treasurer Report with the stored
explanations. Future months inherit this knowledge automatically.

### S6 — Approve & lock

```bash
python -m kvfos --root "$SANDBOX" approve --month 2026-07
python -m kvfos --root "$SANDBOX" close --month 2026-07     # must FAIL
```

**Expect (observed):** approval recorded with timestamp; re-close without
`--amend` refused, exit 2.

### S7 — Restatement

Modify the workbook (a late invoice), then:

```bash
python -m kvfos --root "$SANDBOX" close --month 2026-07 --amend
```

**Expect (observed):** `reports/AMENDMENT.md` with approved-vs-amended
deltas per figure and per category; approved version retained in the lock.

### S8 — Idempotency / no-dupes proof

```bash
sha256sum "$SANDBOX"/registry/master_register.csv   # run close again, compare
```

**Expect (observed):** identical hash across runs; register rows = one per
ledger transaction per month; txn ids all unique.

## 3. Testing with real data (the pilot month)

1. Pick a real month you already reconciled by hand.
2. `python -m kvfos init-month <month>` on a branch; add the accountant's
   real workbook, statements, stats (see README for column conventions —
   or map odd filenames via `inputs/manifest.yaml`).
3. Run the close. Expect noise on the first pass: unknown vendors, chart
   codes not in `categories.yaml:account_map`, header names the readers
   don't know yet. Fixing these means editing knowledge YAML (and, for
   truly new headers, adding synonyms in `ingest.py:_HEADER_SYNONYMS`).
4. Compare the Treasurer Report to your manual reconciliation. Differences
   are either a bug (file an issue) or your manual process missing
   something (the point of the system).
5. Month two should be dramatically quieter — that's the memory working.
   Success criterion: review in under 15 minutes by month three.

## Known limitations to test around

- Scanned (image-only) PDFs are flagged as gaps, not OCR'd — provide CSV
  or text-PDF versions for now.
- Bank/Wise/statistics readers expect the documented column conventions;
  first contact with a new bank's export format usually needs a synonym
  or a `manifest.yaml` entry.
- The reminder issue only covers *ended* months; the current month appears
  after it ends.
