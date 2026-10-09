# DECISIONS

Living document. Every meaningful design choice goes here, including ones we
later reverse. Entries are dated and marked as **Accepted**, **Reversed**, or
**Pending**.

---

## How to read this

Each entry has the same shape:
- **Context** — the situation or problem
- **Options** — what we considered
- **Decision** — what we chose
- **Consequences** — what this means going forward
- **Reversal triggers** — what would make us change our mind

---

## D-001 — Scope: which three expansion areas

**Date:** 2026-10-08
**Status:** Accepted

**Context:**
The brief requires at least three of eight expansion areas. Depth beats coverage.

**Options:**
1. Multi-cooperative tenancy
2. Disputes & corrections
3. Audit trail
4. Notifications (SMS)
5. Credit readiness
6. Reporting & export
7. Field reality (offline)
8. Background work

**Decision:**
TBD — to be decided during domain modelling.

**Reasoning:**
TBD

**Consequences:**
TBD

---

## D-002 — Tech stack

**Date:** 2026-10-08
**Status:** Accepted

**Context:**
We need a stack that (a) supports two persistence paradigms, (b) handles
money-critical transactions, (c) works for a real frontend, (d) runs on free
tiers for deployment.

**Options considered:**
- Backend: FastAPI (Python) vs. NestJS (Node) vs. Go
- DB: PostgreSQL vs. MySQL vs. SQLite
- Second store: Redis vs. MongoDB
- Frontend: React vs. Vue vs. Svelte

**Decision:**
- Backend: FastAPI (Python 3.12)
- Primary DB: PostgreSQL 16
- Second store: Redis
- Frontend: React + Vite + Tailwind + shadcn/ui

**Reasoning:**
TBD **Reasoning:**

The selected stack provides a good balance of reliability, development speed, maintainability, scalability, and compatibility with free-tier deployment requirements.

* **FastAPI (Python 3.12)** was selected for the backend because it provides strong performance, asynchronous support, automatic API documentation, and a clean structure for building REST APIs. Python also provides a mature ecosystem for data processing, automation, and future AI/analytics capabilities. Compared with NestJS, FastAPI offers a simpler and more lightweight approach for this project, while Go would introduce additional complexity without providing a significant advantage at the current scale.

* **PostgreSQL 16** was selected as the primary database because the system requires strong data integrity, transactions, relationships, and reliable handling of money-critical operations. PostgreSQL provides robust ACID transactions, constraints, indexing, and support for complex relational queries. MySQL was considered capable, but PostgreSQL provides stronger features and flexibility for the expected data model. SQLite was rejected as the primary production database because it is better suited to lightweight or single-instance applications and is less appropriate for concurrent, transaction-heavy workloads.

* **Redis** was selected as the secondary data store for caching, short-lived data, session-related workloads, rate limiting, queues, and other high-speed operations. IRedis was selected because our secondary-store needs are structure-oriented (queues, counters, rate-limit buckets, short-lived session state) rather than document-oriented. A queue is a first-class primitive in Redis; in MongoDB it would be a collection with polling — a worse fit. MongoDB was therefore rejected not on performance grounds but on data-shape grounds. MongoDB was not selected because the system's secondary-store requirements are primarily performance and temporary-state oriented rather than document-oriented persistence.

* **React + Vite** was selected for the frontend because React provides a mature ecosystem, reusable component architecture, and a large developer community. Vite provides a fast development and build experience with minimal configuration. Vue and Svelte were considered strong alternatives, but React was preferred because of its ecosystem, availability of libraries, long-term maintainability, and suitability for building a feature-rich application.

* **Tailwind CSS + shadcn/ui** were selected to provide a consistent, responsive, and maintainable UI while allowing components to remain customizable. Tailwind enables rapid styling without maintaining a large collection of custom CSS, while shadcn/ui provides accessible, reusable components that can be adapted to the application's design requirements.

Overall, this stack minimizes unnecessary complexity while providing a solid foundation for transactional workloads, multiple persistence paradigms, a modern user interface, and future scalability. It also has strong support across free and low-cost hosting options, making it appropriate for the project's initial deployment and development stages.


**Consequences:**
- Strong relational integrity for money tables
- JSONB available for flexible farmer attributes
- Redis gives us a real queue for background work + notifications
- FastAPI's Pydantic validation suits the "money safety" requirement

**Reversal triggers:**
- If we needed heavy offline-first + sync, we'd reconsider the backend language
- If the deployment target didn't support Redis free tier, we'd swap to MongoDB Atlas

---

## D-003 — UUIDs over integer primary keys

**Date:** 2026-10-08
**Status:** Accepted

**Context:**
Every table will need a primary key. Integer IDs are the traditional default.

**Options:**
- Auto-incrementing integers (BIGSERIAL)
- UUIDs (v4)
- ULIDs / UUIDv7 (time-sortable)

**Decision:**
UUID v4 via `uuid.uuid4()` in Python.

**Reasoning:**
TBD

**Consequences:**
- IDs aren't guessable in URLs (privacy for farmers)
- Safe if we ever split the DB or add multi-tenancy
- Slightly larger storage / slower index than integers
- Not chronological — a customer service rep can't say "farmer 1234" easily

**Reversal triggers:**
- If we hit scale where index size becomes a real cost, switch to UUIDv7 (time-sortable)

---

## D-004 — Alembic for all schema changes

**Date:** 2026-10-08
**Status:** Accepted

**Context:**
Schema will evolve rapidly during development.

**Decision:**
Every schema change goes through an Alembic migration. No manual DDL in `psql`.

**Reasoning:**
- Migrations are versioned and reviewable
- Deployment to staging/prod is reproducible
- The alternative — manual SQL — causes drift between code and DB, which we'd
  only discover at the worst possible time

**Consequences:**
- Every model change needs `alembic revision --autogenerate` + review
- Autogenerated migrations must be read, not blindly applied

---

## AI usage disclosure

**Tools used:** Claude (Anthropic) as a pair-programming / teaching assistant.

**For what kinds of work:**
- Explaining concepts and tradeoffs
- Reviewing design choices
- Generating boilerplate we've already reasoned about
- Debugging errors

**One example of AI output rejected or significantly reworked:**

TBD — record the first time this happens. It will.

**What is NOT delegated:**
- Data model design
- Permission model design
- Scope decisions
- Anything we cannot defend live

## D-006 — Farmer identity invariants

**Date:** 2026-10-09
**Status:** Accepted

**Context:**
The brief names "ghost farmers" — fake or duplicate records paid for produce
never delivered — as a first-class problem. We need to decide which defenses
live in the database and which in the application.

**Decision:**
Database-enforced (via CHECK/UNIQUE constraints):
- Phone must be E.164 format
- Phone must be unique
- National ID must be unique *when present* (Postgres ignores NULLs in UNIQUE)
- `merged_into_id` cannot point at self
- `status = 'merged'` if and only if `merged_into_id IS NOT NULL`
- `verified_at` and `verified_by_id` set together or not at all
- `status` must be one of a closed set

Application-enforced (business rules that cannot be expressed in DDL):
- Merged farmers cannot receive new deliveries or payments
- Merge chains (A→B→C) must be resolved to the terminal farmer when reading history
- Users are soft-deleted (deactivated), never hard-deleted, because audit records reference them

**Verification:**
Direct SQL against the running DB proved all 5 DB-level invariants reject
invalid rows, and that two farmers with NULL national_id are both accepted.

**Consequences:**
- A buggy or hostile application cannot insert corrupt farmer records
- Any write path (API, seed script, raw SQL, migration) is bound by the same rules
- The application still owns lifecycle semantics; the DB does not know what a
  "delivery" is

**Portability note:**
The "multiple NULLs allowed in UNIQUE" behavior is Postgres/MySQL. SQL Server
allows only one NULL by default. If we ever port, we'd need a partial unique
index on `national_id WHERE national_id IS NOT NULL`.

**Reversal triggers:**
- If the business needs farmers without a phone number (e.g., walk-in
  registration later digitised), we'd relax the uniqueness to a partial index.

## D-007 — Rates are effective-dated, append-only, and non-overlapping

**Date:** 2026-10-09
**Status:** Accepted

**Context:**
The price a cooperative pays per kg of coffee (or liter of milk, etc.) changes
over time. Farmers deliver continuously. We must never let the "value" of a
past delivery silently change when the current price changes, and we must
never have two different prices applying to the same produce line on the same
day.

**Options considered:**
1. Store the current rate on the produce line, and store a snapshot on each
   delivery. Simple, but the price history is lost — "what did we pay last
   season?" becomes unanswerable.
2. Store rate history in an audit table only. Queryable for forensics, but not
   the source of truth for new deliveries.
3. Store rates as effective-dated rows, and snapshot the applicable rate onto
   each delivery.

**Decision:**
Option 3. The `rates` table stores append-only, effective-dated rows.
Each `Delivery` will snapshot the exact rate applied at the moment it was
recorded (this will live in `delivery.rate_snapshot`).

**Rules enforced:**
- Rates are never edited or deleted. A price change closes the current rate
  (`effective_to = <new_start_date>`) and inserts a new row.
- Ranges are half-open `[from, to)`. This means each calendar day belongs to
  exactly one rate. No gaps, no overlaps.
- Overlap is prevented by a PostgreSQL EXCLUDE constraint using
  `daterange(effective_from, effective_to, '[)') WITH &&`.
- This requires the `btree_gist` extension (GiST doesn't index `uuid` natively).

**Consequences:**
- Historical rate queries are trivial: `WHERE effective_from <= D AND
  (effective_to IS NULL OR effective_to > D)`
- Current rate is: `WHERE effective_to IS NULL ORDER BY effective_from DESC LIMIT 1`
- Rate changes are one INSERT + one UPDATE (close the old, add the new),
  wrapped in a single transaction.
- Migration `db2c3a3decf7` must `CREATE EXTENSION btree_gist` before creating
  the `rates` table, or a fresh clone will fail on `alembic upgrade head`.

**Reversal triggers:**
- If rates need to vary by farmer segment (not just produce line), we'd add
  a `segment` column to the exclusion constraint.
- If we ever needed per-delivery negotiated prices, we'd allow rates to be
  overridden at delivery time (snapshot, still append-only).

**AI note:**
We initially wrote the constraint without realizing `btree_gist` was needed.
The first `alembic upgrade head` failed with:
`data type uuid has no default operator class for access method "gist"`.
We diagnosed and fixed it ourselves, then documented why here.

## D-008 — Delivery: the spine of the system

**Date:** 2026-10-09
**Status:** Accepted

**Context:**
Every hard problem in the brief flows through deliveries: ghost farmers,
disputed records, farmer trust, produce-line reporting, clerk accountability,
credit history. If `Delivery` is wrong, everything downstream is wrong.

**Decision — the shape of a Delivery:**

A Delivery is an immutable factual record that *"at time T, farmer F delivered
quantity Q of produce line L, recorded by clerk C."*

Two distinct timestamps:
- `delivered_at` — when the physical delivery happened
- `recorded_at` — when the clerk entered it in the system

These can differ by days. The brief explicitly calls this out
("recorded by field clerks, sometimes days later"). Storing only one
timestamp collapses two facts into one and loses the discrepancy.

**Decision — corrections are reversals, not edits:**

Confirmed deliveries are never edited or deleted. A correction is a new
delivery row with negative quantity that references the original via
`reversal_of_id`. The original remains visible in history.

Why not edit? Because the interview brief names "farmers don't trust the
math" as a first-class problem. An editable record is untrustworthy by
definition. A reversal is a *new* fact that references an *old* fact, and
both remain visible.

**Decision — reversals live in the same table:**

We considered a separate `delivery_reversals` table. We rejected it because
every "net quantity for farmer" query would require a LEFT JOIN, which is a
foot-gun for developers and a performance tax. Same-table reversals turn
"net quantity" into `SUM(quantity)`, which is elegant and cheap.

Enforcement:
- A reversal has `quantity < 0`.
- A normal delivery has `quantity > 0`.
- A reversal has `reversal_of_id` set; a normal delivery has it NULL.
- A unique constraint on `reversal_of_id WHERE NOT NULL` prevents
  double-reversal.
- A CHECK prevents self-reversal (`reversal_of_id != id`).

We do NOT support partial reversals. A reversal undoes the whole original
delivery. Partial reversals are a different design that we would only build
if a real cooperative asked for it. (Reversal trigger documented below.)

**Decision — amount is computed, not stored:**

`amount = quantity * rate_snapshot`, using Python `Decimal` with a defined
rounding policy.

We do NOT materialize `amount` in the MVP because:
- It duplicates data that can be derived
- Duplicated data can drift
- At our scale, computation is free

Reversal trigger: if a cooperative exceeds ~500k deliveries and dashboard
aggregation becomes slow, we add a materialized column with a CHECK that
enforces the invariant, or a generated column.

**Decision — a delivery's valuation is separate from a farmer's payment:**

A delivery creates a *liability* (money the cooperative owes the farmer).
A payment is a *settlement* of one or more liabilities. These are different
concepts and live in different models (`Payment`, `PaymentAllocation`).

**Decision — valuation is derived, not stored:**

We do not have a `valuation_status` column. A delivery is "pending valuation"
if `rate_snapshot IS NULL` and "valued" otherwise. Deriving means the status
can never drift from the underlying fact. If we later need a third state
(e.g., "under admin review"), we add it then.

**Decision — rate is snapshotted at record time:**

`rate_snapshot` stores the exact rate that applied when the delivery was
recorded. Future rate changes never affect historical deliveries. This is
what makes the payment math trustworthy to farmers.

**Decision — reversals inherit the original's date:**

A reversal's `delivered_at` matches the original's. This keeps the reversal
attached to the period it corrects, not to today's date. `recorded_at`
tells us when the correction was entered.

**Invariants (DB-enforced):**
- `quantity > 0` for normal deliveries, `quantity < 0` for reversals
- `rate_snapshot` is positive when present
- `currency_snapshot` matches ISO 4217 format
- `reversal_of_id != id` (no self-reversal)
- `UNIQUE (reversal_of_id)` where non-null (no double-reversal)
- `delivered_at <= recorded_at + interval '1 hour'` (allows clock skew)
- FKs with ON DELETE RESTRICT for all references (no silent orphan deletion)

**Invariants (application-enforced):**
- A rate must exist on the `delivered_at` date, otherwise the delivery is
  recorded with `rate_snapshot = NULL` and flagged for review. (See D-009.)
- A merged, archived, or suspended farmer cannot receive new deliveries.
- A deactivated produce line cannot be used in new deliveries.

**Reversal triggers:**
- If a cooperative needs partial reversals, we redesign.
- If audit requirements demand a permanent, immutable record even of
  reversals, we move to an append-only event log (event sourcing proper).
- If dashboard performance degrades at scale, we materialize `amount`.

## D-009 — Delivery invariant verification

**Date:** 2026-10-09
**Status:** Accepted

**Context:**
D-008 defined the shape of `Delivery` and asserted a set of invariants.
This entry records that those invariants were verified against the running
database with raw SQL, before any application code exists to enforce them.

**Verification method:**
Eight direct SQL tests against the live `deliveries` table.

**Results:**

| Test | Attempt | Expected | Actual |
|---|---|---|---|
| 1 | Valid delivery (positive, no reversal) | accept | ✅ accept |
| 2a | Positive qty + reversal_of_id set | reject | ✅ reject (`ck_delivery_normal_or_reversal`) |
| 2b | Negative qty + no reversal_of_id | reject | ✅ reject (`ck_delivery_normal_or_reversal`) |
| 3 | Valid reversal (negative, links to original) | accept | ✅ accept |
| 4 | Second reversal of the same original | reject | ✅ reject (`uq_delivery_reversal_of`) |
| 5 | Reversal of self | reject | ✅ reject (`ck_delivery_no_self_reversal`) |
| 6 | Future-dated delivery (+5 years) | reject | ✅ reject (`ck_delivery_delivered_at_not_future`) |
| 7 | Backdated delivery (recorded 6 months later) | accept | ✅ accept |
| 8 | Unvalued delivery (rate_snapshot NULL) | accept | ✅ accept |

**Net quantity sanity check:**
`SELECT SUM(quantity) FROM deliveries WHERE farmer_id = X`
correctly returns `+100 +25 +30 -100 = 55` — the reversal is
automatically incorporated. This is the payoff of same-table reversals
(D-008): no joins, no forgotten subtractions, no drift.

**Consequences for later work:**
- The API service layer for deliveries must enforce *the strict version*
  of these rules that the DB cannot: a reversal's quantity must be exactly
  the negative of its original's, and its `delivered_at` must match the
  original's `delivered_at`.
- Rate lookup on delivery creation is a business rule (see D-010): the
  service layer finds the applicable rate by `delivered_at`, snapshots it
  into `rate_snapshot`, and allows `NULL` if no rate exists — producing a
  "pending valuation" delivery rather than rejecting the record.