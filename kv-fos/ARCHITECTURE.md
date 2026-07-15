# KV-FOS Architecture

For the team maintaining the system. The product definition is
[SPEC.md](SPEC.md); this document explains how the implementation meets it.

## Design stance

A knowledge-based pipeline over a git-versioned file store — not a hosted
app, not a generic AI agent (SPEC Appendix A, decision D-2). Everything the
system knows lives in human-readable, diffable files that outlive any tool.

## Layout

```
kv-fos/
├── SPEC.md / README.md / ARCHITECTURE.md
├── kvfos/                  the pipeline (pure Python, stdlib + openpyxl/yaml/pdfplumber)
│   ├── model.py            data model, DataStatus taxonomy, deterministic ids
│   ├── config.py           knowledge-base loading + validation + vendor matching
│   ├── registry.py         content-addressed document registry, supersession
│   ├── ingest.py           Stage 1 — readers (xlsx/csv/yaml/pdf), UA/EN headers
│   ├── normalize.py        Stage 2 — ledger→Transactions, bank→BankLines, FX
│   ├── reconcile.py        Stage 3 — bank matching + 3-way balance checks
│   ├── trace.py            Stage 4 — per-transfer trace cards
│   ├── analyze.py          Stages 5–6 — financial + operational analysis
│   ├── anomalies.py        Stage 7 — exception engine + learned resolutions
│   ├── gaps.py             input completeness → re-upload instructions
│   ├── confidence.py       computed confidence score (rubric-driven)
│   ├── reports.py          the six monthly outputs + master register
│   ├── lock.py             approve/lock/amendment (SPEC §9.8)
│   ├── pipeline.py         orchestrator: close_month()
│   └── cli.py              remind / status / init-month / close / approve
├── knowledge/              persistent financial memory (YAML, git-versioned)
│   └── learned/            aliases + resolutions accumulated over time
├── months/YYYY-MM/
│   ├── inputs/             what the Treasurer drops in (+ optional manifest.yaml)
│   ├── derived/            machine state: transactions.jsonl, reconciliation.json, …
│   ├── reports/            the generated monthly outputs
│   ├── GAPS.md             gap list + actions
│   └── approved.lock.json  present only once the Treasurer approves
├── registry/               cumulative: documents.json, master_register.csv
├── tests/                  pytest suite (idempotency, dedupe, gaps, learning, lock)
└── tools/make_sample_data.py
```

## The invariants that matter

1. **Idempotent close.** `close_month` deletes and rebuilds `derived/` and
   `reports/` from `inputs/` + `knowledge/` every run. There is no
   incremental state to corrupt.
2. **Deterministic identity.** Documents are identified by content hash;
   transactions/bank lines/findings by hashes of their content (with a
   sequence counter for genuinely identical rows). Same inputs ⇒ same ids
   ⇒ re-running can never duplicate.
3. **Supersession, not accumulation.** For unique-per-key document types
   (workbook, stats, statement-per-account) the newest file wins and the
   rest are marked superseded — kept in the registry for history, excluded
   from processing. This is what makes "fix the file and re-upload" safe.
4. **Books are the record.** The master register is built from the ledger
   only; bank lines exist to *verify* it (matching upgrades a transaction
   to Verified). Merging both sources would double-count by design, so we
   never do.
5. **Never fabricate (SPEC §4.1).** A figure that can't be derived is
   Missing and produces a gap; a conflicted figure is Uncertain and
   produces a finding. No silent interpolation anywhere, including FX.
6. **Locked months are immutable.** `approve` freezes input hashes and
   headline figures; re-closing requires `--amend` and yields a delta
   report. History lives in git.

## Data flow (one close)

```
inputs/ ──scan──▶ Document registry (hash, type, supersession)
   │
   ├─ workbook ──▶ ledger rows ──▶ Transactions (vendor match, category, FX)
   ├─ statements ─▶ bank rows ──▶ BankLines
   ├─ stats ─────▶ center metrics
   └─ wise/requests ─▶ transfer records
                       │
Transactions ⇄ BankLines   (match ⇒ Verified)
                       │
        reconcile ──▶ trace ──▶ analyze ──▶ gaps ──▶ anomalies ──▶ confidence
                       │
        derived/*.json(l) + reports/*.md + registry/master_register.csv
```

## Extension points (mapped to SPEC roadmap)

- **US-side ingestion (Phase 4):** add a reader + a `funding_events`
  store; transfers already carry `funding_source` links.
- **OCR:** `ingest._pdf_table_rows` flags scanned docs low-confidence; an
  OCR step can slot in there without touching the pipeline.
- **Report viewer:** reports are plain markdown with stable source
  locators; a static HTML layer can hyperlink them without pipeline
  changes.
- **New anomaly rules:** add a block in `anomalies.detect` and, if
  configurable, a threshold in `materiality.yaml`. Finding ids stay
  deterministic; learned resolutions apply automatically.

## Testing philosophy

The suite exercises behaviors the Treasurer depends on, not internals:
re-upload → supersede; reprocess → byte-identical outputs; missing
statement → blocking gap → approval refused → recovery on re-upload;
tampered balances → reconciliation break; learned alias/resolution →
fewer open exceptions; approve → lock → amend delta. Run with
`python -m pytest tests -q`.
