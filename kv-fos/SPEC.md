# Kinder Velt Financial Oversight System (KV-FOS)

## Project Specification

| | |
|---|---|
| **Version** | 1.0 (Draft for review) |
| **Status** | Proposed — pending Treasurer sign-off on §16 Open Decisions |
| **Owner** | Friends of Kinder Velt USA, Inc. |
| **Primary Owner** | Nick Kremer, Treasurer |
| **Audience** | Software team responsible for building KV-FOS |

This document defines the **product**, not the implementation. Where an
implementation-shaped choice was unavoidable (form factor, data handling), it is
recorded as a default with the rationale, and listed in §16 for confirmation.

---

## 1. Purpose

The Kinder Velt Financial Oversight System exists to help Friends of Kinder Velt
USA (FoKV-USA) fulfill its fiduciary responsibility as the primary financial
supporter of Kinder Velt Ukraine (KV-UA).

The system provides **independent financial oversight** by reconciling funding
requests, U.S. transfers, Ukrainian accounting records, bank statements, and
program outcomes into a single monthly report.

### 1.1 What KV-FOS is not

- **Not an accounting system.** The Ukrainian accountant's books remain the
  system of record. KV-FOS never creates, edits, or replaces accounting entries.
- **Not a bookkeeping system.** It does not manage payables, receivables,
  payroll, or bank connections.
- **Not an audit.** Its outputs support the Treasurer's review; they are not an
  audit opinion (see §11).

It is a **governance, transparency, and oversight system**.

### 1.2 Mission: the traceability chain

Every dollar transferred from FoKV-USA shall be traceable through the full chain:

```
Funding Request
      ↓
US Approval
      ↓
Money Transfer (Wise)
      ↓
Receipt in Ukraine
      ↓
Accounting Ledger
      ↓
Expense
      ↓
Program Impact
      ↓
Board Report
      ↓
Donor Transparency Report
```

A break anywhere in this chain is itself a reportable finding, not a silent gap.

---

## 2. Scope

### 2.1 In scope (v1)

- Oversight of **Kinder Velt Ukraine's finances**: its accounting workbook, its
  bank accounts, and expenses at its centers.
- **US transfers as inputs**: Wise transfer and delivery confirmations, and
  funding request letters, are ingested to anchor the traceability chain.
- Program metrics from center statistics reports.
- All monthly outputs listed in §10.

### 2.2 Out of scope (v1) — planned for a later phase

- FoKV-USA's own books: donation platform exports, US bank statements, US
  operating expenses, and per-donor restricted-fund balance tracking.
- Donor-facing self-service access (v1 donor report is a generated document).
- Real-time or intra-month monitoring; the operating cadence is monthly.

**Design constraint:** the data model must anticipate US-side ingestion.
Concretely: funding sources are first-class entities (§8.4), transfers carry an
optional link to a US-side funding event, and restricted/unrestricted
designation exists on transfers from day one — even if v1 populates it only from
transfer documentation.

> **Default adopted (D-1, §16):** Ukraine-side scope for v1, with the schema
> anticipating US-side expansion.

---

## 3. Users

| Role | Access level | Primary need |
|---|---|---|
| **Treasurer** (primary) | Full | Run the monthly cycle, review exceptions, approve the month |
| Board of Directors | Board Report | Concise, reliable monthly picture |
| Executive Director | Treasurer + Board Reports | Operational + financial view |
| Founder | Board Report | Confidence and continuity |
| Future CPA | Full read access + audit trail | Verify figures back to source |
| Major Donors | Donor Transparency Report | Trust that funds are well managed |
| Grant Makers | Donor Transparency Report (+ tailored extracts) | Compliance and impact evidence |

Only the Treasurer operates the system in v1. All other users are consumers of
generated reports.

---

## 4. Guiding Principles

These principles are requirements, not aspirations. Every feature must be
checked against them.

### 4.1 Accuracy — never fabricate data

Every figure in every output carries exactly one of four **data statuses**:

| Status | Meaning |
|---|---|
| **Verified** | Matches at least two independent sources (e.g., ledger + bank statement) |
| **Estimated** | Derived by a documented method (e.g., FX conversion, allocation across centers); method shown |
| **Missing** | Expected but not present in this month's inputs; shown as missing, never interpolated silently |
| **Uncertain** | Sources conflict or documentation is ambiguous; conflict shown |

The system must be structurally incapable of presenting an Estimated, Missing,
or Uncertain figure as Verified. Every reported number must be traceable back to
a source document (§10.6).

### 4.2 Transparency — every figure explainable

Every expense must be linked to **vendor, category, date, and source document**
whenever possible; where a link is impossible, the absence is flagged, not
hidden.

### 4.3 Independence

The Ukrainian accountant owns the accounting records. KV-FOS independently
reviews those records. The system never writes back to the accountant's files;
corrections flow as questions from the Treasurer to the accountant, and the
accountant's corrected workbook is re-imported (§9.4).

### 4.4 Simplicity — review by exception

The Treasurer should not need to read hundreds of transactions every month. The
system surfaces **only what requires review**: exceptions, material variances,
and anything below the confidence bar. Everything routine is summarized and
available on drill-down, never forced into the review path.

---

## 5. Operating Model (form factor)

> **Default adopted (D-2, §16):** an AI-assisted workflow over a structured,
> versioned document store — not a hosted web application in v1.

The monthly cycle works as follows:

1. **Collect.** The Treasurer places the month's input documents into a
   structured folder for that month (e.g., `2026-07/`) in a private, versioned
   store (private repository or equivalent with full history).
2. **Run.** The Treasurer initiates the monthly close. The system executes the
   pipeline (§9) end to end without further input unless it hits a blocking
   problem (e.g., an unreadable required document).
3. **Review.** The system produces the outputs (§10) plus the exception list.
   The Treasurer works only the exception list.
4. **Resolve.** Each exception is resolved per the workflow in §12. Resolutions
   are persisted to the knowledge base so the same question is never asked twice.
5. **Approve & lock.** The Treasurer approves the month. The month's data and
   reports become immutable (§9.8). Board and donor reports are distributed
   outside the system (email, board portal, website).

Rationale: this matches the "persistent financial memory" goal — the knowledge
base is plain, versioned, human-readable files that outlive any particular tool;
it is the cheapest path to the 15-minute goal; and a report-viewing web layer
can be added later (§15) without rework because reports are generated artifacts.

---

## 6. Monthly Inputs

### 6.1 Required

| Input | Contents | Typical format |
|---|---|---|
| **Accounting workbook** | General Ledger, Expense Register, Payroll Register, Chart of Accounts, Journal Entries | Excel |
| **Bank statements** | Every KV-UA organizational account, full month | PDF / Excel / scans |
| **Center statistics** | Children served, parent consultations, classes conducted, new children, activity by center (e.g., `KinderVeltCenterUpdates.pdf`) | PDF |

A monthly close cannot complete with a required input missing; it can complete
with one **degraded** (e.g., a scanned statement OCR'd at low confidence), which
caps the confidence score (§11) and is flagged.

### 6.2 Optional

Funding request letters, Wise transfer confirmations, Wise delivery
confirmations, invoices, contracts, receipts, grant agreements, budget updates,
other supporting documentation.

The system requests optional documents **only when they would improve
reconciliation** — e.g., "Transfer of $12,000 on July 3 has no Wise confirmation;
providing it would upgrade Transfer Matching from Uncertain to Verified." It
must not nag for documents that would not change any figure's status.

### 6.3 Input languages and formats

- Source documents will be in **Ukrainian and English**, with amounts in UAH
  and USD. The system must read both languages; all outputs are in English
  (with original-language vendor names preserved alongside transliterations, §8.2).
- Accepted formats: Excel, PDF (native and scanned), images. OCR when necessary,
  with OCR confidence tracked per document and reflected in data status.

---

## 7. Persistent Knowledge Base

The system maintains a permanent configuration and a growing body of learned
institutional knowledge. Both are human-readable, editable by the Treasurer, and
versioned (every change recorded with date and reason).

### 7.1 Organization

Centers:

- Kyiv
- Kharkiv
- Odessa
- Mykolaiv
- Kropyvnytskyi *(historical — retained for trend continuity; new activity at a
  closed center is an exception)*

Opening or closing a center is a configuration change, not a code change.

### 7.2 Vendor Master

One record per vendor, seeded with known vendors and grown automatically (§7.6):

| Field | Example |
|---|---|
| Canonical name (original script) | ФОП Юриев |
| Transliteration | FOP Yuriev |
| Aliases / name variants seen | (accumulated from documents) |
| Default category | Rent |
| Center(s) | Kyiv |
| Recurrence | Recurring, monthly |
| Classification | Administration |
| Expected amount range | (learned from history) |
| First seen / last seen | dates |

Seed examples: **ФОП Юриев** (Rent, Kyiv, recurring, Administration);
**Р-Технопарк** (Utilities, recurring); **Нова Пошта** (Shipping, Program
Logistics, recurring).

### 7.3 Expense Categories

Two-level taxonomy; every transaction gets exactly one leaf category. The
Program / Administration / Taxes split at the top level drives the
program-vs-admin ratio in board and donor reports.

**Program**
- Psychologist Salaries
- Therapists
- Program Staff
- Therapy Materials
- Educational Materials
- Toys
- Art Supplies
- Travel
- Shipping

**Administration**
- Rent
- Utilities
- Internet
- Accounting
- Legal
- Office Supplies
- Bank Fees
- Software
- Professional Services

**Taxes**
- Payroll Taxes
- Government Fees

Categories are configurable; renames and additions must preserve historical
mappings (a category is never silently deleted while transactions reference it).

### 7.4 Funding Sources

- Friends of Kinder Velt USA — General Donations
- Corporate Sponsors
- Restricted Campaigns
- Grant Funding
- Individual Donors

Each transfer is attributed to a funding source when documentation allows;
restricted sources carry their restriction terms so expense attribution against
them can be checked (fully automated checking is a later phase; v1 records the
restriction and flags spending that plainly contradicts it).

### 7.5 Materiality Rules

All thresholds are **configuration, editable by the Treasurer, without any
change to system logic**. Defaults:

| Rule | Default threshold |
|---|---|
| Single expense | $500 USD |
| Payroll change (month over month) | 10% |
| Rent change | 5% |
| Utility change | 20% |
| Cash balance change | 20% |

**Always flag**, regardless of amount:

- New vendor
- Missing invoice
- Duplicate payment
- Cash withdrawal
- Unknown expense
- Unmatched transfer

Threshold changes are versioned; reports state which threshold version was in
effect for the month.

### 7.6 Learned knowledge (the "financial memory")

Beyond configuration, the knowledge base accumulates:

- **Vendor aliases** — every new spelling/format of a known vendor's name,
  confirmed once by the Treasurer, matched automatically forever after.
- **Categorization precedents** — Treasurer's categorization decisions become
  rules ("Нова Пошта charges to Kharkiv center → Program/Shipping").
- **Recurring-expense baselines** — expected amount, day-of-month, and
  seasonality per recurring vendor, used to tighten anomaly detection.
- **Transfer patterns** — typical cadence, size, and FX behavior of US transfers.
- **Exception resolutions** — every resolved exception and its explanation, so
  recurring benign anomalies (e.g., annual insurance payment) are auto-explained
  in subsequent years rather than re-flagged.
- **Report conventions** — phrasing, ordering, and formatting choices the
  Treasurer has corrected, applied to future reports.

Success criterion: the exception list should get **shorter and smarter** every
month on comparable activity, because more of the organization's normal behavior
is known.

---

## 8. Data Handling and Privacy

> **Default adopted (D-3, §16):** private storage with cloud AI processing
> permitted, plus output-level minimization as below.

- All inputs and the knowledge base live in **private, access-controlled
  storage**. Nothing is public except the Donor Transparency Report, which the
  Treasurer publishes deliberately.
- **Payroll:** individual names and salaries appear in no output above the
  Treasurer Report. Board Report shows payroll only as category totals; Donor
  Report shows only Program vs Administrative aggregates. The Treasurer Report
  may show per-person detail because the Treasurer needs it for variance review.
- **Children's data:** inputs are aggregate counts by design; the system must
  never ingest or store individually identifying information about children. If
  a source document contains any (e.g., a case note in a statistics PDF), it is
  excluded from extraction and flagged to the Treasurer.
- **Processing:** commercial AI services may process the documents under
  standard enterprise/no-training terms. If the Board later prohibits this, the
  pipeline degrades gracefully (more manual steps), not fatally.
- **Retention:** permanent. The historical database is an asset (§1, §13); no
  automatic deletion. Removal of any record is a logged, Treasurer-initiated act.

---

## 9. Core Processing Pipeline

The pipeline runs as seven stages. Each stage's output is persisted, so a failed
or interrupted close resumes rather than restarts, and every derived figure can
name the stage and inputs that produced it.

### Stage 1 — Import Documents

- Detect document types automatically (accounting workbook, bank statement,
  Wise confirmation, statistics report, invoice, …).
- Read Excel, PDF, images, and scanned documents; OCR when necessary.
- Record for every document: source filename, type, period covered, language,
  extraction confidence.
- **Idempotent:** re-importing the same document must not create duplicates;
  importing a *revised* version of a document supersedes the prior version with
  both retained in history.

### Stage 2 — Normalize Data

Merge all transactions into one standardized transaction database. Normalize:

- **Vendor names** → canonical vendor via the Vendor Master (§7.2); unmatched
  names become "new vendor" exceptions, never silent new records.
- **Categories** → the taxonomy in §7.3, using the accountant's chart of
  accounts mapping plus learned precedents; low-confidence categorizations are
  marked Uncertain.
- **Currencies** → every amount stored in original currency **and** USD (§9.9).
- **Dates** → ISO dates; ambiguous formats resolved by document context or
  flagged.
- **Centers** → each transaction attributed to a center where determinable;
  shared costs may be unallocated or allocated by a documented rule (allocated
  amounts are Estimated).

### Stage 3 — Reconcile

For each bank account and for the books as a whole, verify:

- Opening balance (equals prior month's verified closing balance)
- Income
- Expenses
- Closing balance

Compare three views against each other: **accounting records**, **bank
statements**, **US transfer records**. Every discrepancy above a de minimis
tolerance becomes an exception with both sides' figures and sources shown.

### Stage 4 — Funding Traceability

Every U.S. transfer is matched to each link of the chain, and each link gets a
status (matched / missing document / mismatch):

1. Funding request (when available)
2. Wise transfer confirmation
3. Wise delivery confirmation
4. Deposit in Ukrainian bank statement
5. Accounting entries recording receipt
6. Related expenses drawn against it
7. Remaining balance

The output is a per-transfer trace card the Treasurer (or a future auditor) can
read top to bottom. Unmatched or partially matched transfers are always-flag
exceptions (§7.5).

### Stage 5 — Financial Analysis

Generate:

- Income Statement
- Expense Statement
- Cash Position (per account and total)
- Expense by Category
- Vendor Summary
- Monthly Trends (rolling 12 months once history exists)
- Program vs Administrative expense split

All statements display **both UAH and USD** (§9.9).

### Stage 6 — Operational Analysis

Combine financial data with program metrics:

- Children served, parent consultations, classes conducted, new children,
  activity by center, historical trends
- **Unit economics:** cost per child served, cost per consultation, cost per
  class, operating cost per center

Unit-economics figures are always Estimated (they depend on allocation rules)
and must state their method. Where a center's metrics are missing, its unit
costs are Missing — not computed from partial data.

### Stage 7 — Exception Analysis

Automatically detect:

- Unmatched bank transactions
- Duplicate payments
- Unknown vendors / new vendors
- Missing documentation
- Unexpected expense increases (vs. learned baselines and materiality rules)
- Unexpected payroll changes
- Large one-time expenses
- Currency discrepancies
- Potential accounting errors (e.g., balance breaks, sign errors, category
  outliers)

**Every exception includes a plain-language explanation of why it was flagged
and the supporting evidence** (the figures and source documents involved), plus
— when the knowledge base allows — a suggested resolution.

### 9.8 Month close, lock, and restatement

- When the Treasurer approves the month, its transactions, reports, and
  confidence score are **locked**. Locked months are never edited in place.
- If the accountant later restates a prior month, the re-imported workbook
  produces an **amendment**: the system reports the deltas against the locked
  version, the Treasurer approves the amendment, and both versions remain in
  history. Downstream trends use amended figures with an amendment marker.

### 9.9 Currency conversion policy

- Default USD conversion uses the **historical exchange rate applicable to the
  transaction date** when available.
- For US transfers, the **actual realized Wise rate** from the transfer
  confirmation takes precedence over any reference rate.
- For all other UAH transactions, the reference source is the National Bank of
  Ukraine official daily rate *(confirm — D-6, §16)*.
- Every converted figure records which rate and source were used; converted
  figures are Estimated unless anchored to a realized rate.

---

## 10. Monthly Outputs

All outputs are generated documents, produced together at month close, in
English, dual-currency where figures appear.

### 10.1 Executive Summary — one page

Shows **only**: Income, Expenses, Current Cash, Net Change, Largest Categories,
Major Risks, Open Questions. Nothing else. If it doesn't fit on one page, the
system is including too much.

### 10.2 Treasurer Report

Detailed reconciliation, variance analysis, vendor analysis, and the full
exception report. This is the only output that may contain named payroll detail
(§8). Ordered so the Treasurer's 15-minute path is: confidence score →
exceptions → variances → done.

### 10.3 Board Report

Simple. Focused only on: Income, Expenses, Cash Balance, Program Highlights,
Financial Risks. Written for directors without finance backgrounds; no jargon,
no transaction-level detail.

### 10.4 Donor Transparency Report

Public-facing. Shows: Income, Program Spending, Administrative Spending, Major
Categories, Impact Metrics, and a Narrative Summary. Contains only aggregate
figures (§8); the narrative is drafted by the system and edited/approved by the
Treasurer before publication — it is never auto-published.

### 10.5 Master Transaction Register

The complete, searchable, cumulative database of every transaction across all
months: date, vendor, category, center, amounts (UAH/USD), funding source where
known, data status, and source-document references. Exportable (at minimum CSV).

### 10.6 Audit Trail

Every figure in every report is **clickable (or otherwise mechanically
traceable)** back to: ledger entry → bank statement line → transfer record →
supporting documentation. **No summary number may exist without traceability.**
In the v1 form factor (§5), "clickable" means each figure carries a stable
reference (document + location) that resolves to the stored source file.

---

## 11. Confidence Assessment

Each monthly close concludes with a **Financial Oversight Confidence Score**,
e.g.:

> **Overall Confidence: 94 / 100 — Overall Risk: LOW**
>
> | Component | Status |
> |---|---|
> | Bank Reconciliation | ✓ |
> | Transfer Matching | ✓ |
> | Expense Categorization | ✓ |
> | Program Metrics | ✓ |
> | Supporting Documentation | ⚠ One missing invoice |

Requirements:

- The score is **computed, not vibes**: each component's score derives from
  measurable facts (share of transactions Verified, count of open exceptions,
  document coverage), and the derivation is inspectable.
- The scoring rubric is configuration (like §7.5), versioned, and stated on the
  report.
- The score is **an aid to the Treasurer's review, not an audit opinion**, and
  every report says so.
- Score trends over time appear in the Treasurer Report, so a slow erosion of
  documentation quality is visible.

---

## 12. Exception Workflow

Exceptions are the unit of the Treasurer's work. Each has a lifecycle:

```
Open → (Treasurer reviews) → Explained → Accepted
                           ↘ Escalated (question sent to accountant/ED)
                                 ↓
                           Resolved on re-import or reply → Accepted
```

- A month can be approved with open exceptions only by explicit Treasurer
  override, recorded with a reason; open exceptions carry into the next month.
- Every **Accepted** explanation persists to the knowledge base (§7.6) with its
  generalization ("this vendor bills annually each July") so equivalent future
  cases are auto-explained.
- The exception list is ranked by materiality so the Treasurer works
  top-down and can stop at the immaterial tail.

---

## 13. Responsibilities

| Party | Responsibilities |
|---|---|
| **Ukrainian Accountant** | Maintain accurate books; record transactions; maintain payroll; reconcile bank accounts; maintain supporting documentation; prepare official accounting records |
| **KV-FOS** | Review; analyze; reconcile; summarize; detect anomalies; produce reports; track historical trends; maintain transparency; support governance |
| **Treasurer** | Review reports; investigate exceptions; approve monthly oversight; report to the Board; request clarification when necessary |

The boundary in §4.3 is absolute: KV-FOS reviews, it never records.

---

## 14. Success Criteria

The project is successful when:

1. Monthly review consistently takes **less than 15 minutes** of Treasurer time
   (measured from opening the reports to approving the month, on a month with a
   typical exception count).
2. **Every transfer** from FoKV-USA can be traced from request to impact via its
   trace card (§ Stage 4).
3. The Board receives a concise, reliable monthly financial summary.
4. Donor transparency reports are generated with minimal manual effort (target:
   Treasurer edits the narrative only).
5. The system builds a **cumulative financial history** that measurably improves
   categorization and anomaly detection over time (falling rate of
   false-positive exceptions on comparable activity).
6. The Treasurer can confidently demonstrate meaningful financial oversight of
   KV-UA to donors, regulators, auditors, and grantmakers.

---

## 15. Phased Roadmap

**Phase 1 — Foundation (first month)**
Knowledge base seeded (centers, vendor master, categories, funding sources,
materiality defaults); ingestion of the three required inputs; Stages 1–3 and 7;
Treasurer Report + Master Transaction Register + Executive Summary. Goal: first
real monthly close, even if slow.

**Phase 2 — Traceability & full reporting (months 2–3)**
Stage 4 trace cards; Stages 5–6; Board and Donor reports; confidence score;
month lock and amendment handling. Goal: full output suite, sub-hour review.

**Phase 3 — Memory pays off (months 4–12)**
Learned baselines, auto-explained recurring anomalies, exception resolutions
feeding forward, trend reporting across accumulated history. Goal: sub-15-minute
review, falling exception counts.

**Phase 4 — Expansion (as decided)**
US-side ingestion for end-to-end donor-dollar traceability (§2.2); a
report-viewing web layer with clickable drill-down for board/CPA users;
restricted-fund compliance checking against grant agreements.

---

## 16. Open Decisions

Defaults below were adopted to keep the spec actionable; each is reversible and
awaits Treasurer confirmation.

| # | Decision | Default adopted | Alternative(s) |
|---|---|---|---|
| D-1 | Oversight scope | Ukraine-side v1; schema anticipates US-side (§2) | Both entities end-to-end from day one |
| D-2 | Form factor | AI-assisted workflow over a private versioned document store (§5) | Hosted web app; hybrid with report-viewer layer earlier |
| D-3 | Data handling | Private storage, cloud AI processing permitted, output minimization (§8) | Pseudonymize payroll before any AI processing; prohibit cloud processing |
| D-4 | Output language | English outputs, Ukrainian originals preserved for vendors/documents (§6.3) | Bilingual EN/UA report variants (e.g., for the accountant) |
| D-5 | Restatement policy | Locked months + versioned amendments (§9.8) | Reopen-and-replace (not recommended: destroys the audit trail) |
| D-6 | Reference FX source | NBU official daily rate; realized Wise rate for transfers (§9.9) | Accountant's book rate; monthly average rate |
| D-7 | Knowledge-base location | Private repository in the organization's control | Shared drive; managed database |
| D-8 | Distribution | Reports distributed manually by Treasurer | Automated distribution after approval |

---

## Appendix A — Design stance

KV-FOS should **not** be built as a generic "AI finance agent." It should be
built as a **knowledge-based system with persistent financial memory**. Over the
course of a year it should learn every recurring vendor, recurring expense,
transfer pattern, and reporting convention unique to Kinder Velt. That
accumulated institutional knowledge — not the monthly report generation — is the
compounding asset that makes the system increasingly valuable rather than simply
producing the same type of report each month.
