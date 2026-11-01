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

## D-010 — The ledger model: deliveries as credits, payments as debits

**Date:** 2026-10-10
**Status:** Accepted

**Context:**
The brief requires money operations to be safe and farmer balances to be
trustworthy. Every financial design choice flows from one core question:
*where does the truth live?*

**Decision — the ledger:**

We model money as a two-sided ledger:

- Every **delivery** is a **credit** to the farmer (we owe them more).
- Every **payment** is a **debit** to the farmer (we owe them less).

We do NOT store any farmer balance. Not on `Farmer`, not on any summary
table. Balances are always derived from the underlying facts.

**Why derived, not stored:**
A stored balance is a duplicated fact. Every write that affects it (delivery,
reversal, payment, correction) must update it consistently. Miss one path and
the balance is wrong forever, and the farmer loses trust. A derived balance
cannot drift — as long as the underlying facts are correct.

**Reversal triggers:**
If performance measurements show aggregation is the bottleneck (e.g., dashboards
become slow at 500k+ deliveries), we introduce a materialized balance column
maintained by triggers or a scheduled job, with an automated reconciliation
check that compares it to the derived value. Until then, we accept slower reads
in exchange for correctness.

**Decision — payment allocation is a separate entity:**

A payment is a *transfer of money to a farmer*. An allocation records *which
deliveries that payment settles*. These are different concepts.

Without `PaymentAllocation`, we cannot answer "which deliveries are still
unpaid?" — a core management question.

**Decision — partial payments are allowed:**

A farmer may be paid partially now, and the remainder later. A payment
allocates a specific amount against each delivery it covers.

**Decision — payment reversal cascades to allocations (in one transaction):**

When a payment is reversed, its allocations are reversed in the same
transaction, under the same lock. This is a service-layer rule, not a DB
constraint — because the DB doesn't know about the business intent.

Failure mode if we didn't cascade: `SUM(payments)` would say "reversed"
but `SUM(allocations)` would still show the deliveries as settled. The
ledger would be internally inconsistent.

**Decision — same-table reversals for payments AND allocations:**

Both `Payment` and `PaymentAllocation` use the same reversal pattern as
`Delivery`:
- Normal row: positive amount, `reversal_of_id IS NULL`
- Reversal row: negative amount, `reversal_of_id` points at the original
- `UNIQUE (reversal_of_id) WHERE NOT NULL` prevents double-reversal
- `reversal_of_id != id` prevents self-reversal

Aggregation becomes `SUM(amount)` — sign encodes direction. No joins, no
special-casing, no risk of forgetting to subtract reversals.

**Decision — payments may exceed outstanding debt:**

A cooperative may advance money against future deliveries (common in
agriculture). We allow overpayment, and distinguish two positions:

- **Outstanding debt** — unpaid value of deliveries
- **Unallocated credit** — confirmed money received, not yet assigned to
  deliveries

We do NOT represent overpayment as a negative balance. They are different
financial positions and collapsing them into one signed number loses
information.

Application of credit to future deliveries is an explicit, auditable
transaction. We never silently rewrite the original payment.

**Decision — concurrency protocol (the financial write path):**

Every operation that changes a farmer's outstanding balance must follow the
same locking protocol:

1. Begin transaction
2. Lock all involved farmers in ascending UUID order:
   `SELECT id FROM farmers WHERE id IN (...) ORDER BY id FOR UPDATE`
3. Read authoritative state (deliveries, allocations, payments) under lock
4. Validate business rules
5. Write
6. Commit

Operations bound by this protocol:
- Creating a payment
- Creating payment allocations
- Reversing a payment (and its cascade)
- Reversing a delivery
- Applying credit to a delivery

**Why the farmer row is the lock:**
- One lock per farmer — no multi-lock ordering pitfalls in the common case
- Different farmers can be paid concurrently
- The invariant we protect ("a farmer cannot be over-paid") is farmer-scoped

**Why ascending UUID ordering:**
When a transaction must lock multiple farmers, a consistent order eliminates
deadlock cycles. Documented as a hard rule.

**Caveat — writers must go through the service:**
The lock only works if all writers obey it. Direct SQL writes bypass it.
For MVP we restrict DB write access to the application role. Adding a
materialized `unallocated_amount` column with CHECK `>= 0` on `delivery`
would provide DB-level enforcement even against rogue writers, but we
deliberately reject it for now — one materialized value, one source of
truth drift we can't afford (see "Why derived, not stored").

**The four tests that matter most:**

These map directly to the brief's "money operations are safe" requirement:

1. Two concurrent payments cannot allocate more than a delivery's
   outstanding value.
2. Retrying the same payment with the same idempotency key cannot create
   a duplicate payment.
3. Reversing a payment restores both the delivery's outstanding amount
   and the farmer's available credit correctly.
4. Concurrent delivery reversal and payment creation for the same farmer
   serialize correctly (no lost update, no double-spend against credit).

If any of these fails, the money model is broken and we stop everything
else until it's fixed.

## D-011 — Money model verified against the live database

**Date:** 2026-10-10
**Status:** Accepted

**Context:**
D-010 defined the money model. This entry records verification of the
constraints that protect it, performed with raw SQL against the running DB
before any application code exists.

**Eight tests, all constraints fired as designed:**

| # | Attempt | Result |
|---|---|---|
| 1 | Valid payment | accepted |
| 2 | Valid allocation | accepted |
| 3 | Reuse an idempotency key | rejected — `uq_payment_idempotency_key` |
| 4 | Same payment+delivery allocation again | rejected — `uq_allocation_payment_delivery_normal` |
| 5 | Reverse the payment | accepted |
| 6 | Reverse the same payment twice | rejected — `uq_payment_reversal_of` |
| 7 | Reverse the allocation | accepted |
| 8 | Reverse the same allocation twice | rejected — `uq_allocation_reversal_of` |

**Ledger symmetry proof:**

After one payment + one reversal, and one allocation + one reversal:
- `SUM(payments.amount) = 0.0000` for that farmer
- `SUM(payment_allocations.amount) = 0.0000` for that delivery

Sign-encoded amounts mean aggregation never needs a WHERE clause to
subtract reversals. This is the payoff of same-table reversals (D-010).

**Notable behaviors observed:**

- **Partial unique index works.** Test 7 (allocation reversal, same
  `(payment_id, delivery_id)` as its original) was accepted because the
  index is `WHERE reversal_of_id IS NULL`. Test 4 (a second normal
  allocation for the same pair) was correctly rejected.
- **The idempotency key is scoped globally.** Test 3 confirmed that a
  reused key is rejected regardless of farmer context.
- **Reversals of payments and allocations are independent.**
  A reversed payment and its reversal (positive + negative) net to zero,
  but the underlying allocations still exist as separate facts.

**Consequences:**

- The next slice (API + service layer) can assume these invariants hold
  and focus on the business rules the DB cannot enforce: allocating
  according to outstanding balance under the farmer row lock (D-010).
- The four tests listed in D-010 remain the "must pass" set. Tests 1–8
  here cover the DB-level subset; the concurrency tests still must be
  performed against the service layer.

## D-012 — Authentication primitives

**Date:** 2026-10-10
**Status:** Accepted

**Context:**
Authentication and authorization must exist and be enforced server-side
(brief, hard requirement 2). This entry records the primitives; the auth
*flow* (registration, login) is a later slice.

**Decision — password hashing: Argon2id via passlib.**

Options considered:
- Argon2id (chosen) — memory-hard, OWASP-recommended, defeats GPU attacks
- bcrypt — acceptable, but has a 72-byte input limit and is less memory-hard
- scrypt — also fine, less library support in Python
- SHA-256 — **never**; fast hashes are trivially brute-forced
- Plaintext — obviously not

**Decision — JWT: HS256, 12-hour lifetime.**

Options considered:
- HS256 (chosen) — symmetric, one backend, simple, fast
- RS256 — asymmetric, needed only for multi-service verification; overkill now
- Session cookies — viable, but complicates mobile clients
- Refresh tokens — out of scope for MVP; the frontend re-logs in after expiry

**Why 12 hours:**
- Long enough for a full field shift without re-login
- Short enough to halve the exposure window vs a 24-hour token
- Configurable via settings.access_token_expire_minutes for other environments

**Decision — the token asserts identity, not permission.**

The JWT includes `role` in its payload for the frontend's convenience, but
the backend NEVER trusts it for authorization. Every protected request
re-loads the user from the database and checks role + is_active at that
moment. This means a user who is downgraded from admin to clerk loses admin
privileges immediately, not after their token expires.

**Decision — two roles only: admin and clerk.**

- admin: manage rates, verify farmers, reverse payments
- clerk: register farmers, record deliveries, record payments
- (auditor would be added if we ever have a real read-only review workflow)

The `users.role` column is a VARCHAR with a CHECK constraint (mirrored from
a Python enum UserRole). Not a Postgres ENUM type — same reasoning as D-005:
cheap to extend, DB-enforced.

**Consequences:**
- `security.py` has no imports from models or services — pure utility
- Auth service and dependency layer (B.2, B.3) will build on these primitives
- Token rotation is possible in the future by rotating `JWT_SECRET_KEY` —
  no user data is lost, just all tokens become invalid (users re-login)
- `SECRET_KEY` and `JWT_SECRET_KEY` are separate so rotating one does not
  affect the other

## D-013 — Alembic autogenerate: known failure modes we've hit

**Date:** 2026-10-10
**Status:** Accepted

**Context:**
Alembic autogenerate is our migration authoring tool, but it is not
omniscient. Over the course of building the schema we have hit three
distinct failure modes. Recording them here so we always review generated
migrations rather than applying them blindly.

**Failure mode 1 — Missing model registration.**
If a model file exists but isn't imported into `app/models/__init__.py`,
Alembic sees an empty `Base.metadata` for it and generates an empty
migration (or worse, proposes to DROP the table). We hit this on the
Farmers table.
Mitigation: every new model gets an import line in `__init__.py` in the
same commit as the model file.

**Failure mode 2 — Constraint prerequisites.**
We defined an `EXCLUDE USING gist (...)` constraint on `rates`. PostgreSQL
needed the `btree_gist` extension installed first (GiST does not index
`uuid` by default). Alembic rendered the constraint correctly but did not
know to install the extension, and the first `alembic upgrade head` failed
with `data type uuid has no default operator class for access method "gist"`.
Mitigation: when a migration introduces a Postgres extension dependency,
add `op.execute("CREATE EXTENSION IF NOT EXISTS ...")` at the top of
`upgrade()`.

**Failure mode 3 — Missing CHECK constraints on existing tables.**
When we added `ck_user_role_valid` to the `users` table, autogenerate
detected the accompanying VARCHAR length change but missed the new CHECK
constraint entirely. We patched the migration by hand.
Mitigation: after any schema change that adds a constraint to an existing
table, query `pg_constraint` for that table and verify the constraint
landed.

**General rule:**
Read every generated migration line by line before applying. Autogenerate
is a starting point, not a finished artifact. Hand-edits are legitimate;
they should carry a comment explaining why.

**Consequences:**
Every migration in this project carries an implicit claim: "we read this
and confirmed it does exactly what we intended." Any migration that
doesn't meet that bar should be treated as a bug.

## D-014 — Auth flow: bootstrap, timing, and response hygiene

**Date:** 2026-10-12
**Status:** Accepted

**Context:**
D-012 defined the primitives (hashing, JWTs, roles). This entry records the
auth *flow* decisions: how the first admin is created, how login is made
safe against enumeration, and how the API response is shaped to prevent
accidental data leaks.

**Decision — first-user-bootstraps-admin, then admin-only.**

Rules:
- If `users` is empty, the first registration always creates an `admin`,
  regardless of the requested role. There is no one else to approve them.
- Subsequent registrations default to `clerk` and may request `admin` — but
  in slice B.3 the endpoint will require an authenticated admin to create
  users (open signup is disabled).

**Bootstrap race safety:**
We use a Postgres transaction-scoped advisory lock
(`pg_advisory_xact_lock(_BOOTSTRAP_LOCK_KEY)`) around the check-then-insert.
Two concurrent first-user requests serialize: one creates the admin, the
other sees a non-empty table and falls through to the normal path. Without
the lock, both could observe "table empty" and both become admins.

**Why an advisory lock over alternatives:**
- SERIALIZABLE isolation would work but is heavier and affects the entire
  transaction, not just the bootstrap check.
- Application-level threading locks don't survive multiple Uvicorn workers.
- `INSERT ... WHERE NOT EXISTS` is readable only in theory — in practice it
  fights SQLAlchemy's ORM and mis-formats timestamps and UUIDs. We chose
  clarity.

**Decision — constant-time login response.**

Login always runs an Argon2 verification:
- If the email exists and password is correct → success
- If the email exists and password is wrong → verify, fail
- If the email does NOT exist → verify against a hardcoded dummy hash, fail

All three paths take roughly the same time (~50 ms with our Argon2
parameters). Without this, an attacker could time the endpoint to learn
which emails are registered — a real information leak, not a theoretical
one.

We also return the *same* error message (`"Invalid credentials"`) for
"unknown email" and "wrong password". Message uniformity and timing
uniformity together are what actually prevent enumeration.

**Decision — `UserResponse` is an allowlist, not a blacklist.**

The response schema lists exactly the fields clients should see
(`id`, `email`, `full_name`, `role`, `is_active`). It does NOT include
`hashed_password`, and it never will. This is stronger than trying to
exclude sensitive fields from a generic serializer — if a new sensitive
field is added to the User model later, it will not appear in the API
response unless someone adds it to `UserResponse` on purpose.

**Decision — email validation is strict.**

`EmailStr` uses the `email-validator` library, which rejects reserved
TLDs (`.local`, `.test`, `.example`) by default. Test fixtures and seed
data must use realistic-looking domains (we use `@shambatrack.io`).
If we ever need to accept reserved domains in development, we'd add a
`LooseEmailStr` type that calls
`validate_email(..., check_deliverability=False)`. We deliberately did
NOT relax the validator for the API itself — production emails should
be checked strictly.

**Amended 2026-10-20:** `SECRET_KEY` was removed. It was required by
`Settings` and documented as deliberately separate from `JWT_SECRET_KEY`,
but nothing ever read it — a required environment variable that silently
does nothing is a deployment trap, not a safety margin. When a second key
gains a real use (e.g. signing cookies or a refresh token), it returns with
that use. The JWT decisions above stand unchanged.

**Consequences:**
- Auth endpoints behave identically for anonymous and authenticated
  actors up to the point of token issuance.
- The bootstrap path is race-safe under concurrent first requests.
- Any accidental addition of `hashed_password` to a response would fail
  code review, not slip through because someone forgot to add
  `exclude=True`.

**Reversal triggers:**
- If we later add multi-tenant admin bootstrapping (one admin per
  cooperative), the advisory lock key becomes per-cooperative.
- If we add rate limiting to login, the constant-time defense stays
  but is augmented by throttling.

## D-015 — Authorization: dependency-based, DB-authoritative

**Date:** 2026-10-12
**Status:** Accepted

**Context:**
D-012 defined authentication (who you are) and D-014 defined the auth flow
(register, login, constant-time, bootstrap). This entry records how
*authorization* (what you may do) is enforced on every protected endpoint.

**Decision — dependencies, not middleware.**

Authorization is expressed as FastAPI dependencies in `app/api/deps.py`:
- `get_current_user` — resolves the caller from the bearer token
- `require_role(*roles)` — factory that returns a role-checking dependency

Endpoints declare what they need:

    @router.post(
        "/rates",
        dependencies=[Depends(require_role(UserRole.ADMIN))],
    )
    def create_rate(...): ...

We chose dependencies over custom middleware because:
- Middleware doesn't see the route; it can only allow/deny by path pattern,
  which is fragile.
- Dependencies compose: an endpoint can require a role AND inject the user
  object for use in the handler.
- The permission is stated at the endpoint — visible where the decision
  matters, not hidden in a config table.

**Decision — the DB is authoritative on every request.**

`get_current_user` re-loads the user from the database, using only the
`sub` claim from the token. It does NOT trust the token's `role` claim.

Consequences:
- A user whose role changed takes effect on the *next request*, not after
  token expiry.
- A user deactivated mid-session is blocked immediately.
- We pay one DB lookup per authenticated request. For MVP this is fine. If
  it becomes a bottleneck we may cache briefly, but only after measurement.

**Decision — 401 vs 403 are used precisely.**

- 401 Unauthorized — no token, bad token, expired token, user not found,
  user is inactive. These all mean: "we don't know who you are (or you
  have no standing)."
- 403 Forbidden — token valid, user active, but the role doesn't permit
  the operation. This means: "we know who you are; you may not do this."

FastAPI's default `HTTPBearer` returns 403 for a missing header, which is
wrong per RFC 7235. We set `auto_error=False` and raise 401 ourselves with
the standard `WWW-Authenticate: Bearer` header.

**Decision — 401 responses don't leak which check failed.**

All 401 paths except "Token expired" return the same generic message
("Invalid token"). Distinguishing "bad signature" from "malformed" from
"unknown user" would give an attacker a free oracle. The single exception
is "Token expired", which the frontend legitimately needs to distinguish
(it should prompt re-login, not show "your account is invalid").

**Decision — inactive account = 401, not 403.**

A deactivated account is treated as having no standing, not as
"authenticated but forbidden". This keeps the mental model simple: 401
means "you cannot proceed", 403 means "you are known but not permitted".

**Consequences:**
- Every protected endpoint declares its requirement declaratively.
- Tests for permission boundaries are trivial: call the endpoint with a
  clerk token where an admin is required, expect 403.
- The full permission model is visible by grepping for `require_role` in
  the codebase.

**Reversal triggers:**
- If we add a third role or complex permission logic ("a clerk may approve
  deliveries under X units"), we move from role-checks to a policy
  function that takes the user + resource and returns allow/deny.
- If role changes become very frequent and DB-per-request becomes a
  measured bottleneck, we add a short-lived role cache with explicit
  invalidation on role change.

## D-016 — Phone normalization policy

**Date:** 2026-10-13
**Status:** Accepted

**Context:**
Farmers' phone numbers are the SMS destination (expansion area 4) and the
primary anti-duplicate key (D-006). The same human can be entered as
`0712345678`, `+254712345678`, or `+254 712 345 678`. If those become
three different rows, we have a ghost-farmer problem *before* we even get
to payments.

We must decide: what is the canonical phone format, and where does
normalization happen?

**Decision — canonical form is E.164.**

Examples: `+254712345678`, `+256700000001`, `+255712345678`.

The database enforces this with a CHECK (`ck_farmer_phone_e164`), so even
a buggy service cannot insert a malformed phone. The API presents the same
format — every `FarmerResponse.phone` is E.164.

**Decision — normalization happens in the service, not the schema.**

An initial design had the schema validate strictly against the E.164 regex
and reject anything else. We reversed this when we realized the service's
local-format normalizer was unreachable: any input that needed normalizing
was already rejected by Pydantic before the service ran.

We now:
- Keep the schema as a **loose shape check only** (7–20 chars).
- Let the **service** strip whitespace, accept already-E.164 values, match
  a per-country table of known local formats (`07...` / `01...` for KE),
  and either return the canonical E.164 form or raise `InvalidPhoneFormat`.

**Rationale:**
Phone format depends on country and cooperative context. A schema-level
regex would have to be updated every time we onboard a cooperative in a
new country. That's a business rule, not a shape rule — so it belongs in
the service.

The cost is that Pydantic no longer produces structured errors for phone
format problems; the service produces a plain 422 with a readable message
("phone '1234567' is not E.164 and does not match a known local format").
We judged this to be *better* UX for a field clerk than Pydantic's
"String should match pattern '^\\+[1-9][0-9]{6,14}$'".

**Consequences:**
- Adding Uganda or Tanzania means adding one entry to `_LOCAL_PREFIXES`
  in the service. No schema change. No migration.
- The frontend can pre-normalize for UX, but is not required to.
- The DB CHECK remains as defense in depth.

**Reversal triggers:**
- If we ever accept phone numbers that are *not* associated with a known
  country (e.g., a diaspora delivery), the service's per-country lookup
  becomes a problem. We would then require E.164 from the client and
  reject in the schema instead.

---

## D-017 — Service / router / schema layering

**Date:** 2026-10-13
**Status:** Accepted

**Context:**
`Farmers` was the first full CRUD resource. Its shape will be repeated for
produce lines, rates, deliveries, and payments. It's worth recording the
conventions explicitly so the rest of the project is consistent.

**Layers:**

- **`app/schemas/<resource>.py`** — Pydantic models. Request/response
  contracts. Validation of *shape* (types, lengths, ranges). No business
  rules. Response schemas are **allowlists**: if a field isn't here, it
  doesn't leave the server.
- **`app/services/<resource>.py`** — Business logic. Owns transactions.
  Owns invariants that aren't (or can't be) enforced by the DB. Raises
  *domain exceptions*, not HTTPException — the service doesn't know about
  HTTP.
- **`app/api/<resource>.py`** — HTTP handlers. Parse request, call
  service, translate domain exceptions to HTTP responses, return schema.
  Routers are thin; they should contain almost no branching beyond error
  translation.

**Rules that follow from this:**

1. **Services never import FastAPI.** This makes them testable directly
   and reusable from background jobs (SMS dispatch, credit scoring).
2. **Routers never touch the Session directly.** All DB access goes
   through the service.
3. **Schemas never import services.** They only know their own shape and,
   occasionally, model enums (e.g. `FarmerStatus`).
4. **The exception translation is centralized per router.** A single
   `_translate(exc)` helper maps domain exceptions to HTTP status codes
   with consistent messages.

**Consequences:**
- Business rules are unit-testable without spinning up a server.
- The HTTP layer is replaceable (e.g. if we later add a GraphQL or CLI
  interface) without rewriting the logic.
- Adding a new resource is mechanical: copy the `farmers` files as a
  template, adapt.

**Reversal triggers:**
- If an endpoint needs logic that is genuinely HTTP-specific (e.g.
  content negotiation, streaming), a small exception to the layering
  is acceptable — but we would note it at the endpoint.
- If we move to event-sourcing or CQRS, the service layer would split
  into commands and queries. Not planned for MVP.

## D-018 — Rate change protocol: lock, close, insert

**Date:** 2026-10-14
**Status:** Accepted

**Context:**
Rates are effective-dated and non-overlapping (D-007), enforced by an
`EXCLUDE USING gist` constraint on `rates`. Setting a new rate therefore
cannot simply INSERT — the new range would overlap the current open-ended
one, and the constraint would reject it. We need a defined protocol for
changing the price of a produce line.

**Decision — the rate change is a two-step transaction:**

1. Lock the produce line row: `SELECT ... FOR UPDATE`.
2. Find the currently-open rate (`effective_to IS NULL`) for that line.
3. Validate the requested `effective_from`:
   - If there is an open rate, `effective_from` must be strictly after
     that rate's `effective_from`. Requesting a date at or before the
     current rate's start would require rewriting the timeline, which we
     do not do.
4. Close the current rate: `current.effective_to = new.effective_from`.
5. Insert the new rate, open-ended (`effective_to = NULL`).
6. Commit atomically.

If there is no current rate (first rate for this produce line), we skip
step 4 and just insert.

**Why lock the produce line:**
Two admins setting rates concurrently would otherwise both close the same
current rate and both insert new open-ended ones. The exclusion constraint
would fire on the second commit, but the error ("conflicting key value
violates exclusion constraint ex_rate_no_overlap") is useless to an admin.
Locking the produce line serializes the operation and turns the failure
into a clean, expected case.

**Why the exclusion constraint stays:**
App-level validation is easy to bypass: a bug, a script, a future code
path that forgets the protocol. The DB constraint is the last line of
defense. We keep both; they serve different purposes.

**Decision — backdating is allowed but the client is warned.**

A rate can be set with an `effective_from` in the past, provided it is
still after the current open rate's start. This is legitimate: committee
decisions sometimes reach the system late.

When a rate is created with an `effective_from` before today, we count
deliveries in the affected window whose `rate_snapshot` no longer matches
the newly-set rate:

    affected = COUNT(deliveries
                     WHERE produce_line_id = X
                       AND delivered_at >= new.effective_from
                       AND reversal_of_id IS NULL
                       AND rate_snapshot <> new.rate_per_unit)

The count is returned in the response as `affected_deliveries`.

**We do NOT automatically rewrite affected deliveries.** Their snapshots
are frozen facts (D-008). Correcting them requires the reversal mechanism
and, in the money case, a financial correction — both of which are
explicit operations with their own audit trail. Automatic rewriting would
violate the trust model the whole system is built around.

**Decision — response shape returns both sides of the timeline.**

`POST /produce-lines/{id}/rates` returns:

    {
      "new_rate": { ... , "effective_to": null },
      "previous_rate": { ... , "effective_to": "<new effective_from>" } | null,
      "affected_deliveries": <int>
    }

One round trip updates the client's full view. The first-rate case returns
`previous_rate: null`.

**Decision — rates have no update and no delete endpoint.**

There is no `PATCH /rates/{id}` and no `DELETE /rates/{id}`. To change the
future rate, an admin sets a new rate. To undo a wrong rate that hasn't
taken effect yet, an admin sets a corrected rate with the same
`effective_from` — which fails, because `effective_from` must be strictly
after the current open rate's start.

**Reversal trigger for that last case:** if we hit it in practice (admin
sets a future rate by mistake, wants to remove it), we would need a
"revoke unstarted rate" endpoint that closes the offending rate at its
own start date. This is a documented gap, not a bug. If a cooperative
needs it, we add it deliberately.

**Consequences:**
- The rate history is append-only and queryable at any date.
- Deliveries snapshot their rate and are never retroactively changed.
- Concurrent rate changes produce clean, deterministic outcomes.
- Backdating produces a visible warning count, not a silent mutation.

**Authorization:**
Only `admin` may create, update, or deactivate produce lines, or set
rates. `clerk` may read.

## D-019 — Delivery service: valuation, reversal cascade, and ledger math

**Date:** 2026-10-14
**Status:** Accepted

**Context:**
D-008 defined the Delivery table and its invariants. D-010 defined the
ledger model. This entry records the *service-layer* rules that the DB
cannot enforce — how deliveries are valued, reversed, and summed into the
farmer's financial position.

**Decision — unvalued deliveries are allowed, then valued once.**

A delivery recorded for a produce line with no applicable rate has
`rate_snapshot = NULL`. This is a legitimate state ("pending valuation"),
not an error. It supports the brief's field-reality requirement: a clerk
must be able to record a physical event even if the price hasn't been
configured for that date.

Valuation is a **one-time, audited operation**:
  POST /deliveries/{id}/value (admin only)

It looks up the rate effective on the delivery's `delivered_at` and
snapshots it. If no rate applies even then, the operation fails with a
clear error and the delivery remains pending.

**This is a documented exception to delivery immutability.** A delivery
is immutable once valued. Before valuation, exactly one write is
permitted: the value assignment itself. It is never overwritten.

**Decision — reversal cascades to allocations, same transaction.**

Reversing a delivery:
1. Locks the delivery row, the farmer row, and the delivery's allocations.
2. Inserts a compensating delivery with negative quantity and matching
   snapshots.
3. Inserts compensating rows for every non-reversed allocation against
   the original delivery.
4. Commits atomically.

**Why cascade:**
If the delivery is reversed but its allocations are not, the ledger
becomes inconsistent: `SUM(delivery values)` drops by the reversed amount
but `SUM(allocations)` does not, producing negative "outstanding debt"
for that farmer. Negative debt is not a meaningful state.

After cascading, the reversal correctly restores both:
- The farmer's outstanding debt for that delivery (back to pre-delivery)
- The farmer's available credit (the payment that settled the delivery
  is once again unallocated and counts as credit on account)

**Decision — reversal timestamps.**

The reversal row's `delivered_at` inherits the original's
`delivered_at`. It is a reconciliation anchor, NOT evidence of a second
physical delivery. The reversal's `recorded_at` is the current time, and
`recorded_by_id` is the admin who performed it. The notes field carries
the required reason prefixed with `[reversal] `.

This preserves the invariant `delivered_at <= recorded_at + interval '1 hour'`
without special cases, and keeps the reversal attached to the period it
corrects in aggregations.

**Decision — balance formulas (canonical).**

Computed in `app/services/ledger.py`, and reused verbatim by the statement
endpoint (B.8). Both must agree.

    total_delivery_value = SUM(quantity * rate_snapshot)      -- over ALL deliveries with rate_snapshot NOT NULL
    net_allocations      = SUM(payment_allocations.amount)     -- over ALL allocations whose delivery is this farmer's
    net_payments         = SUM(payments.amount)                -- over ALL payments for this farmer

    outstanding_debt          = total_delivery_value - net_allocations
    allocated_to_deliveries   = net_allocations                  -- informational
    available_credit          = net_payments - net_allocations
    pending_valuation_count   = COUNT(deliveries WHERE rate_snapshot IS NULL)

**Critical detail:** none of the sums filter on `reversal_of_id`. Reversal
rows are signed (negative) and aggregate correctly when included. Filtering
them out (e.g. `WHERE reversal_of_id IS NULL`) would produce wrong totals
for anything that has been reversed.

**Why "allocated_to_deliveries" is reported even though it is derivable:**
It is a hint. It answers "how much of what we owed has been formally
settled" without implying it should be subtracted from debt a second time
(it already is, because debt = value - allocations). The response shape
makes the three-way distinction visible so clients cannot confuse them.

**Concurrency:**
- Recording a delivery is not financial. No farmer lock.
- Valuing a delivery takes the farmer lock (it changes financial state).
- Reversing a delivery takes the farmer lock (D-010's protocol).

**Consequences:**
- `delivery.amount` is computed, not stored (D-008).
- The balance endpoint and the future statement endpoint share code, so
  they cannot disagree.
- A delivery can sit in pending-valuation indefinitely; admins find them
  with `GET /deliveries?unvalued_only=true`.
- Reversing a delivery produces visible, auditable side effects on
  allocations — nothing is silently deleted.

## D-020 — Payment service: idempotency, allocation, cascade

**Date:** 2026-10-14
**Status:** Accepted

**Context:**
D-010 defined the payment ledger model. This entry records the service-layer
rules: idempotency handling, FIFO vs manual allocation, reversal cascade,
and the status model.

**Decision — idempotency: return replay, reject payload drift.**

Client sends `idempotency_key` (a UUID). The service stores a SHA-256
fingerprint of the request's semantically meaningful fields (farmer_id,
amount, currency, method, reference, paid_at, allocations) alongside the
key.

On a repeat request with the same key:

- **Same fingerprint** → return the existing payment with header
  `Idempotency-Replayed: true`. The client's retry is invisible to them.
- **Different fingerprint** → 409 Conflict. The client reused a key for a
  different intent, which is a bug they need to see.

**Why fingerprint and not just "trust the key":**
A key alone cannot tell us whether a request is a legitimate retry or a
mistaken reuse. The fingerprint is what makes the distinction possible.
This matches Stripe's behavior.

**Race safety:**
We check idempotency twice: once before the transaction (fast path) and
once after acquiring the farmer lock (race-safe path). Two concurrent
requests with the same key serialise on the lock; the second sees the
first's payment row and replays.

**Decision — allocation: FIFO by default, manual on request.**

Request payload may include `allocations: [{delivery_id, amount}, ...]`.

- **Manual mode** (allocations provided): the service validates each
  allocation:
  - Delivery belongs to the farmer
  - Delivery is not a reversal
  - Delivery is valued (has `rate_snapshot`)
  - Amount does not exceed the delivery's remaining unpaid value
  - No duplicate `delivery_id` within the request
  - Sum of allocations ≤ payment amount

  Any violation → 422, entire transaction rolls back.

- **FIFO mode** (allocations omitted): the service allocates greedily
  against the farmer's oldest outstanding valued deliveries
  (`delivered_at ASC, id ASC`), stopping when the payment is exhausted.
  Any leftover becomes unallocated credit on account.

**Why FIFO as default:**
A clerk recording a payment almost always wants "pay what we owe, oldest
first." Making that the default (with no request body complexity) matches
real workflow. Manual mode is for exceptional cases (a lender advances
against a specific delivery, or a correction targets a specific line).

**Decision — reversal cascades to allocations, same transaction.**

`POST /payments/{id}/reverse`:
1. Locks the payment row and farmer row.
2. Inserts a compensating negative payment row (`reversal_of_id` = original).
3. Reverses every non-reversed allocation of the original payment.
4. Commits atomically.

Same shape as delivery reversal (D-019). After the cascade, the ledger
nets correctly: the reversed payment no longer counts, and the deliveries
it settled are once again unpaid (their remaining value increases).

**Decision — original payment status stays `confirmed` after reversal.**

We do **not** flip the original payment's status to `reversed`. Reasons:

1. The original payment is a fact. It happened. It remains in the ledger
   as such. Flipping its status would imply it never happened.
2. The reversal is also a fact, in its own row. Both are visible.
3. `SUM(payments.amount)` sign-encodes the net effect naturally — no
   filter on status needed to compute balances.
4. A client that sees `status='reversed'` on the original might think
   "this payment doesn't exist", which is wrong. It exists and was
   reversed. Those are different things.

**The `PaymentStatus.REVERSED` enum value is retained but unused in MVP.**
It is reserved for a future case (integration with a real payment
gateway, where a payment can be *attempted* and then confirmed or failed).
Currently every payment — including reversals — has status `confirmed`.

**Decision — unallocated amount is derived, not stored.**

`unallocated_amount` on the response is computed:

    payment.amount - SUM(net allocations on this payment)

Never stored. Consistent with the ledger design (D-010): derivation cannot
drift from the underlying facts.

**Consequences:**
- A payment is idempotent and safe to retry.
- A payment can be partial, full, or an advance.
- Reversing a payment cleanly restores the state of the deliveries it
  settled, without any manual repair.
- The `payment_allocations` table remains the single source of truth for
  "what did this payment settle?".
- Both FIFO and manual modes share the same allocation-validation
  machinery, so the rules cannot diverge.

**Reversal triggers:**
- If we ever need partial reversals of a payment (reverse only part of
  what was paid), we redesign — current model reverses the whole payment.
- If we integrate a real gateway and payments can fail, `REVERSED` (and
  likely `PENDING` and `FAILED`) become live statuses, and the flip-status
  decision above is revisited.

## D-021 — Farmer statement: chronological view with running pair

**Date:** 2026-10-14
**Status:** Accepted

**Context:**
Balance (D-019) answers "where does this farmer stand right now?" The
statement answers "how did they get there?" — a chronological narrative
that a farmer, a clerk, or a lender can read line by line.

**Decision — the statement shows a running PAIR, not a single number.**

Each entry includes `debt_after` and `credit_after`. We deliberately do
not compute a single "balance" figure, because debt and credit are
different positions (see D-019) and collapsing them loses information.

**Decision — one entry per top-level event.**

The statement emits one row for each delivery, delivery reversal, payment,
and payment reversal — never one row per internal ledger record (e.g. per
allocation). Allocations are folded into the payment entry they belong to,
keeping the narrative readable.

**Decision — entry dates come from the business event, not the record.**

- Deliveries use `delivered_at`
- Payments use `paid_at`
- Reversals inherit the original's date (D-019, D-020)

`recorded_at` is not used for ordering. This keeps the story told in the
farmer's time, not the clerk's.

**Decision — the closing pair MUST equal /balance.**

For a statement whose `end` covers the current moment, its `closing` is
the same as what `GET /farmers/{id}/balance` returns. The statement
service uses the ledger helpers (`compute_balance_at`) and applies signed
deltas in order — it does not re-implement the math. A pytest in B.10
asserts this invariant. If it ever fails, one of the two code paths is
buggy, and the test tells us which.

**Decision — statement range is bounded.**

- Default range: last 365 days
- Maximum range: 730 days (2 years)
- `start <= end` enforced with 422 on violation

The bound protects the database from accidentally enormous queries and
matches what a real co-op would ever need to display.

**Decision — description strings are backend-generated.**

Each entry carries a human-readable `description` built by the service
(e.g. `"Coffee 100 kg @ 50 KES"` or `"Payment reversal: bank reversed the
transfer"`). For MVP this is the single source of truth. If we localize
later, we introduce an i18n layer at the service boundary.

**Consequences:**
- Clients can render a statement directly without joining additional data.
- The response shape stays stable even if internal ledger structure
  changes (e.g. if we later move allocations to an event store).
- A lender can consume a statement as evidence of production history
  (foundation for the credit-readiness expansion later).

**Reversal triggers:**
- If statements become large (thousands of entries), we move the
  computation into a window-function SQL query. The response shape stays
  identical.
- If we need multi-currency statements, `currency` moves from a single
  top-level field to per-entry, and the running pair either takes a
  conversion rate or splits into per-currency pairs.

## D-022 — Test strategy: money paths and permission boundaries, verified under concurrency

**Date:** 2026-10-15
**Status:** Accepted

**Context:**
The brief names two things that must be on the test list: money paths and
permission boundaries. It also warns that coverage numbers are not the
point — reasoning about *what* we test is.

This entry records what we test, how, and — most importantly — why those
are the tests that matter.

**Decision — we test four things:**

1. **Money correctness under concurrency.** The four tests in
   `test_money_concurrency.py` are the direct answer to "it must not be
   possible to pay for the same thing twice."

2. **Permission boundaries at the HTTP layer.** The tests in
   `test_permissions.py` exercise the actual FastAPI app (via TestClient)
   and assert 401 vs 403 vs 200 on protected endpoints. A role model that
   is not tested at the HTTP layer is not tested at all.

3. **Ledger arithmetic.** Balance and statement must agree for the same
   period (they share code by design, and the closing/balance invariant is
   asserted in the money tests).

4. **Startup.** If the app fails to import, every other test fails, but the
   failure message can be confusing. A clean import check is implicitly
   covered by the HTTP tests.

We deliberately do NOT chase coverage numbers. We do NOT test every Pydantic
field. We do NOT mock the database. The tests exercise real PostgreSQL with
real constraints and real row locks because that is where the interesting
failures live.

**Decision — two test isolation strategies coexist.**

Ordinary tests (permissions, service-level logic) share a single transaction
with the service under test. This makes them fast and isolated: the
transaction is rolled back at the end of each test, and the database stays
pristine.

Concurrency tests need *real* commits and *real* locks — because that is the
thing under test. They use independent sessions on independent connections,
one per worker thread, and they commit for real. Cleanup is explicit.

We made service transactions composable to support both:
`app/db/transaction.py` provides a `transaction(db)` context manager that
opens a real transaction on a fresh session and a savepoint on a session
that already has one. This is what lets the same service code work
correctly in production and in both test isolation strategies.

**Decision — the four concurrency tests, and what each proves.**

| # | Test | What it proves |
|---|---|---|
| 1 | Two payments, both attempting to over-allocate one delivery | The farmer-row lock serialises financial writes; no delivery is ever over-settled |
| 2 | Same idempotency key, same body, concurrent threads | Exactly one payment row is created; both threads receive the same id |
| 3 | Reversing a payment | The cascade restores both outstanding debt and available credit to their pre-payment state |
| 4 | Concurrent delivery reversal + payment creation | The farmer lock protects against lost updates; the ledger remains internally consistent |

**Decision — no coverage target.**

We measure nothing in CI except pass/fail. Coverage percentage is a
diagnostic, not a goal. Tests that assert behavior a business person would
recognise ("a clerk may not reverse a payment") earn their keep. Tests
that assert "line 42 was executed" do not.

**What we deliberately did NOT test, and why:**

- **FastAPI request/response validation for every field.** Pydantic is
  well-tested; re-testing it adds noise. We test our rules, not the
  framework's.
- **Argon2 parameters and JWT encoding.** Same reasoning. If our hash
  string parses and our token decodes, we trust the libraries.
- **Every HTTP endpoint for the happy path.** We test representative
  cases (creation, denial, one representative conflict). The permission
  matrix is exhaustively covered for denials, not for acceptances, because
  denials are the security-relevant case.
- **Frontend.** No frontend exists yet. When it does, the browser-level
  tests will live in the frontend repo, not here.

**Consequences:**
- `pytest -m "not concurrency"` runs fast; `pytest -m concurrency` runs
  slower but proves the money model.
- The four concurrency tests are the *only* tests in this project that
  would make me block a release if they failed. Everything else is
  important; these are existential.
- Service code cannot break the composition of transactions without the
  tests failing loudly.

**Reversal triggers:**
- If we add a second write path (e.g., a background job that records
  payments), we add a fifth concurrency test for that path.
- If we move to async FastAPI + AsyncSession, the test isolation strategy
  changes; the four tests' assertions stay the same.

## D-023 — Seed data: deterministic, service-layer-first, guarded

**Date:** 2026-10-16
**Status:** Accepted

**Context:**
The brief requires "seed data included in both [local and live], so we
land in a system that already has realistic activity across all your
roles and chosen expansion areas."

This is a hard requirement, not a nicety. An empty database makes the
demo unimpressive and the deployed submission harder to evaluate.

**Decision — hybrid access, service-first for business data.**

- **Reference data** (users, produce lines, rates) is inserted directly
  via the ORM. These entities have minimal business rules and no
  interesting invariants to exercise.
- **Business data** (farmers, deliveries, payments, reversals) is
  inserted via the service layer. This is deliberate: it means the seed
  exercises the same code path as production. If a service has a bug or
  an over-tight constraint, the seed surfaces it. It also means the seed
  cannot produce data that the API would refuse to produce.

**Decision — the seed is deterministic.**

All randomness flows from `random.Random(42)`. Running the seed twice
produces the same data. This matters for screenshots, documentation, and
demo reproducibility.

**Decision — the seed refuses to run against a non-empty database.**

By default, `python -m scripts.seed` checks for existing users. If any
exist, it prints an error and exits without touching anything. To
force-overwrite, pass `--reset`.

A seed script that silently destroys data is a footgun. We chose the
safer default.

**Decision — the seed deliberately includes edge cases.**

Not just the happy path. A demo that shows only "everything is fine" is
not a demo of the system's design. Seed includes:

| Category | What's seeded | What it demonstrates |
|---|---|---|
| Farmers | 24 active, 3 pending, 2 suspended, 1 archived | The farmer lifecycle, not just the "active" state |
| Produce lines | 4 (coffee, tea, dairy, banana) | The banana line has no rate, deliberately |
| Rates | 6 (two per rated line) | Effective-dating: historical + current |
| Deliveries | ~150 over 6 months | Time-distributed data |
| Unvalued deliveries | ~5 (banana) | The pending-valuation workflow |
| Payments | 12 FIFO + 1 advance | Both normal payout and credit-on-account |
| Reversals | 1 delivery + 1 payment | The correction flow in both directions |

**Decision — the seed prints demo credentials at the end.**

Known accounts (admin@shambatrack.io / demo-admin-123 and three clerks)
make the deployed demo walkable without needing to register. These are
demo credentials only; production would use `settings`-sourced values.

**Consequences:**
- A fresh clone can be running with realistic data in one command:
  `docker compose up -d && alembic upgrade head && python -m scripts.seed`
- The seed script is a smoke test for the whole business layer. If a
  service regresses in a way that breaks realistic usage, the seed fails
  loudly.
- Reset is explicit and opt-in.

**Reversal triggers:**
- If seeding becomes slow (e.g. thousands of rows), we batch direct
  inserts for the bulk and keep services for a small representative
  sample.
- If we support multi-cooperative tenancy, the seed produces data for
  one cooperative by default, with a `--cooperative` flag to target
  another.

## D-024 — Two persistence stores: Postgres for facts, Redis for dispatch

**Date:** 2026-10-16
**Status:** Accepted

**Context:**
The brief requires two persistence paradigms, each used for data it
genuinely suits, with one honest rejected alternative documented.

Notifications (expansion area 4) and background work (expansion area 8)
are the two requirements that need a queue. Together they force the
decision: what lives in Postgres, what lives in Redis, and why.

**Decision — Postgres holds the durable Notification record.**

The canonical fact is: *"at time T, we sent message M to farmer F about
entity E."* This record:

- Must survive a Redis restart. It is part of our audit trail of what we
  told a farmer.
- Joins naturally to `farmers`, and via a polymorphic pointer to
  `deliveries` and `payments`.
- Answers "what did we send this farmer last month?" — a relational query.

**Decision — Redis holds the dispatch state.**

The pipeline state is:

- The queue itself (a Redis LIST, LPUSH/BRPOP).
- A retry schedule (a Redis SORTED SET scored by due timestamp).
- Per-notification dispatch state (a Redis HASH: status, attempts,
  last_error, sent_at).

This is transient, high-churn, and TTL-friendly. Exactly the shape Redis
is optimised for.

**What we considered putting in Postgres and did not:**

We considered modelling the queue as a Postgres table (`notification_jobs`
with `status`, `locked_at`, `attempts` columns) and using `SELECT ...
FOR UPDATE SKIP LOCKED` for dequeue. This is a legitimate pattern —
`pgmq`, `que`, and others do it well — but it would:

- Multiply rows fast (every retry is a new row or an UPDATE).
- Mix operational ephemera into our money-adjacent schema.
- Require more involved query tuning to avoid table bloat.
- Lose the natural `BRPOP` blocking semantics that keep the worker simple.

We chose Redis. If we ever need *transactional* enqueue (a delivery and
its notification row must be written atomically), we would revisit — and
the answer would likely be "write the fact to Postgres and the job to
Postgres too, in one transaction, then relay to Redis".

**What we considered putting in Redis and did not:**

We considered caching the farmer balance in Redis (via
`compute_balance()`). This would trade a small amount of query time for
cache-invalidation complexity on every delivery/payment/reversal. For
MVP with a few thousand farmers, derivation is fast enough. When we need
caching, we will add it behind a documented invalidation strategy and a
reconciliation job that compares cached vs derived.

**Decision — Redis persistence is disabled.**

The Redis container runs with `--save "" --appendonly no`. On restart,
in-flight queue state is lost. This is deliberate:

- The Postgres record is the truth. Redis holds "where in the pipeline
  this is."
- If Redis restarts and loses the queue, an admin can find
  "queued but never sent" notifications via the API and call retry.
- Persistent Redis (RDB/AOF) would trade startup cost and disk usage for
  a benefit we do not need — the durable part is already elsewhere.

**Decision — at-least-once delivery, not exactly-once.**

A crash between "gateway accepted the SMS" and "we wrote sent to Redis"
means a retry may resend the SMS. For a delivery confirmation, this is
annoying; it is not dangerous. True exactly-once is impossible without
cooperation from the SMS provider, and the cost of attempting it would
outweigh the benefit for MVP. Documented rather than hand-waved.

**Consequences:**
- The notification subsystem is a small, self-contained pipeline.
- Postgres row creation is never blocked by Redis. If Redis is
  unreachable, the durable record still exists (`status="queued_redis_unreachable"`)
  and an admin can retry.
- `docker compose up` brings up both stores; both are load-bearing.
- Running the API is one process; running the worker is a second.
  Deployment must run both.

**Reversal triggers:**
- If we integrate a real SMS gateway with delivery receipts (webhooks),
  we add a `delivered_at` field to the Postgres record and stop inferring
  delivery from send success.
- If the notification volume grows past Redis's memory headroom, we move
  the queue to a managed stream (Redis Streams or Kafka) with a consumer
  group, keeping the two-store split.
- If Redis ever needs persistence, we turn it on and document why —
  persistence is a cost, not a default.

## D-025 — Frontend architecture

**Date:** 2026-10-16
**Status:** Accepted

**Context:**
The brief requires a "real frontend" that a non-technical clerk can use
day-to-day on a mid-range phone as well as a desktop. Two usage modes
must coexist:

- Clerk mode (field, phone): fast, few taps, tolerant of poor signal.
- Admin mode (office, desktop): dashboards, management, corrections.

These are different enough that the UI must adapt, not just resize.

**Decision — tech stack:**

| Concern | Choice | Why |
|---|---|---|
| Build | Vite + React 19 + TypeScript | Fast dev loop, type safety |
| Styling | Tailwind CSS v4 | Utility-first, small bundles, no design system to fight |
| Components | shadcn/ui + Radix UI | Copy-in components we own; accessible primitives |
| Data | TanStack Query | Caching, invalidation, loading/error states handled |
| Routing | React Router v7 | Standard, documented, no surprises |
| Forms | React Hook Form + Zod | Type-safe, minimal re-renders |
| Icons | lucide-react | shadcn default, tree-shakeable |
| Charts | Recharts | Simple API, works well with Tailwind |
| Auth storage | localStorage (MVP) | See below |

**Decision — mobile-first, breakpoints upward.**

Clerks use the system in the field on a phone. The default layout and
component sizes are mobile-first (larger tap targets, minimal chrome).
The admin dashboard and management screens adapt upward for desktop.
We do not design desktop-first and degrade.

**Decision — token storage: localStorage for MVP, documented risk.**

The JWT lives in `localStorage`. This is XSS-vulnerable in principle: any
script that runs on the origin can read the token. We accept this for MVP
because:

1. We control all scripts on the page. There are no third-party widgets,
   ads, or CDN-embedded scripts.
2. The alternative (`httpOnly` cookies) requires CSRF protection on the
   API, which is a meaningful addition to the backend for a small benefit
   at this stage.
3. Tokens expire in 12 hours; the blast radius of a leaked token is
   bounded.

We are honest about the trade-off in the code and here.

**Reversal triggers:**
- If we ever embed third-party widgets, iframes, or untrusted content,
  we move auth to `httpOnly` cookies with CSRF tokens.
- If we implement refresh tokens, the access token shortens and the
  refresh token goes into a cookie.

**Decision — hand-written TypeScript types for MVP.**

The frontend has hand-written types mirroring the backend's OpenAPI
schemas. Auto-generating them would add tooling complexity (codegen
step, CI check) for a marginal benefit at MVP scale. If types drift, the
API calls fail loudly — which is the right failure mode.

A generation script (`npm run gen-types`) is a B.14 polish item, not a
B.12 requirement.

**Decision — no dark mode for MVP.**

Dark mode doubles the CSS surface with no demo value. We build for one
theme, done well. Noted as future work.**Consequences:**
- Two usage modes are reflected in routing: clerk-facing views sit at
  top level; admin-only views are gated by role in both routing and
  navigation.
- The API client is thin and typed. Query hooks wrap it per resource.
- The app shell (layout, nav, header) handles role-based navigation.

## D-026 — Dashboard: one aggregate endpoint, contract-first

**Date:** 2026-10-20
**Status:** Accepted

**Context:**
The home screen fired a dozen requests, or would have. Two shapes existed:
an inline flat `DashboardResponse` on `GET /dashboard`, and a richer
`DashboardSummary` in `app/schemas/dashboard.py` that nothing served. The
frontend called `GET /dashboard/summary` — a path that did not exist — so
the screen failed on load while the schema file sat unused.

**Decision — the frontend's contract is the contract.**

`GET /dashboard/summary?days=N` serves `DashboardSummary`. The flat
endpoint is deleted rather than kept alongside it: two endpoints answering
"how are we doing?" with different shapes is a trap, not a convenience.

**Decision — the dashboard aggregates the ledger, it does not re-derive it.**

Cooperative-wide totals use the same formulas as `ledger.compute_balance`
(D-019): sum every delivery row with a non-NULL `rate_snapshot`, every
payment row, and every allocation row — **including reversals**, because
the sign is what does the work. Concretely, the invariant is:

    sum(compute_balance(f).outstanding_debt for f in farmers)
        == dashboard.outstanding_debt_total

and the same for available credit and pending-valuation count. Note the
pending count deliberately does **not** filter on `reversal_of_id`; the
per-farmer count does not either, and the two must be summable.

**Why this is tested, not asserted in prose:**
`test_dashboard.py` compares the endpoint's totals against the ledger for
the farmers it created. A manager's dashboard figure that no farmer's
balance corroborates is worse than no dashboard at all, so the test earns
its keep in the same sense as the money tests (D-022).

The same test was also run once against the seeded development database
(31 farmers, 154 deliveries, 17 payments): totals matched exactly,
413756.8241 outstanding and 40713.1835 on account.

**Decision — period semantics are stated, not implied.**

`days=N` means today plus the N-1 preceding calendar days in UTC, so N
buckets, zero-filled. Activity is dated by the business event
(`delivered_at`, `paid_at`), never `recorded_at` — the same rule as the
statement (D-021). Counts are events (reversals excluded); values are net
(reversals included). A reversed delivery therefore drops out of the money
but not out of the delivery count for the day it happened.

`days` is bounded 1..730 for the same reason the statement range is.

**Consequences:**
- One request renders the home screen.
- Dashboard figures and per-farmer figures cannot disagree without a test
  failing.
- The endpoint issues ~12 aggregate queries; measured at 36–89 ms against
  the seed data (~170 ledger rows). Fine behind the frontend's 60 s
  `staleTime`. If a cooperative outgrows it, the response shape is stable
  enough to serve from materialised views (D-010).
- Reversals of the flat endpoint have no callers to migrate.

**Reversal triggers:**
- If the dashboard needs per-cooperative scoping, every aggregate gains a
  `cooperative_id` predicate — the shape stays.
- If query count becomes the bottleneck, the per-line, per-day, and
  activity queries collapse into one windowed query.

## D-027 — List screens: one table, server-resolved names

**Date:** 2026-10-20
**Status:** Accepted

**Context:**
The five list screens (Farmers, Deliveries, Payments, Produce,
Notifications) each rendered a stacked card list with their own ad-hoc
header, filters and pagination. The same record looked different depending
on which screen you were on, and none of them was a table in the sense an
administrator expects: no columns, no scan-down-the-page reading, no
consistent footer.

The reference is the ICRMS data table: bordered card, muted header row with
small uppercase labels, ruled rows, toolbar strip, in-table empty state,
skeleton rows and a pagination footer.

**Decision — one `DataTable`, column-driven, no table library.**

`components/common/DataTable.tsx` takes `DataColumn<T>[]` and renders the
whole card. Migrating a screen is now a column list plus a toolbar slot.

We deliberately did **not** adopt `@tanstack/react-table` (which ICRMS
uses). The backend paginates and offers no sort parameter, so client-side
sorting would sort the current 25 rows and silently misrepresent the
cooperative. When the API grows `sort`/`order`, the component can swap its
internals without changing any page's column definitions.

**Decision — the footer is the ICRMS footer.**

`Showing 1 to 10 of 31 entries`, a `Rows per page` select (10 / 20 / 50 /
100, default **10**), and numbered page buttons with single-page ellipsis
gaps between chevrons. Changing the page size resets to the first page
because the offset is meaningless across a different limit.

Page size lives in each screen rather than in the table so the value can be
sent to the API; the table only renders state and emits changes.

**Decision — mobile column priority, not horizontal scrolling.**

Columns declare `hideBelow: 'sm' | 'md' | 'lg' | 'xl'`. A phone shows the two
or three columns that matter (e.g. Farmer + Status) and hides the rest;
the identifying value is repeated inside the primary cell where a hidden
column would otherwise be lost. This keeps the clerk-on-a-phone case
(D-025) working without a second, card-based layout to maintain.

**Decision — names are resolved by the API, not the client.**

`DeliveryResponse` gained `farmer_name` and `produce_line_name`;
`PaymentResponse` gained `farmer_name`. Both are resolved in the router with
**bulk lookups per page** (two queries for a delivery page, one for a
payment page), never one query per row. The alternative — the client
fetching farmer and produce-line lists and joining by id — would go stale,
break past the list page size, and put display logic in three places.

These are live joins, not snapshots: renaming a farmer updates every
historical row's label, while the delivery's rate snapshot stays frozen
(D-008). A name is a label; a rate is a fact.

**Decision — shared page header and buttons.**

`PageHeader` and `components/common/Button.tsx` replace the per-page
duplicated heading/action markup and the repeated Tailwind class strings.
`components/ui/*` is left untouched: those shadcn files import `cn` from an
unrelated npm package and are imported by nothing.

**Build note:**
`tsconfig.app.json` was missing the `@/*` path alias — referenced projects do
not inherit `paths` from the root config, so `tsc -b` failed with 148 errors
that had nothing to do with the code. Adding `paths` (without the deprecated
`baseUrl`, which TS 6 rejects) reduced that to 8 genuine ones, all fixed.
`npm run build` now passes.

**Verified in a browser** (Playwright against the dev server, seeded data):
all five screens render column headers, 25 rows/page, muted 12px uppercase
headers in a 1px rounded card; search narrows 25 → 1; pagination advances;
row click opens the detail route; `/deliveries?unvalued=1` pre-checks the
pending-valuation filter; a 390px viewport shows only Farmer + Status; zero
console errors.

**Consequences:**
- A new list screen is a column array, not a layout.
- List and detail screens agree on names because both come from the API.
- Sorting is visibly absent rather than subtly wrong.

**Reversal triggers:**
- If the API gains server-side sorting/filtering, adopt `@tanstack/react-table`
  and move the column definitions onto `ColumnDef` — pages keep their shape.
- If a table needs bulk selection, it needs a bulk endpoint first; we have none.

## D-028 — Phase 1 hardening: truthful health, constant-cost lists, indexes

**Date:** 2026-10-20
**Status:** Accepted

**Context:**
Before adding features we audited the backend for things that are wrong
rather than missing. Four were worth fixing immediately: health checks that
report success while a dependency is down, a list endpoint whose query count
grew with the page size, list queries that could not use any index, and a
set of configuration/code smells that make the system harder to reason
about than it needs to be.

**Decision — health tells the truth, and does not leak.**

`/health` stays a liveness probe (200 while the process serves).
`/health/db` and `/health/redis` are readiness probes and return **503** when
the dependency is unreachable. Previously they returned 200 with
`{"status":"error"}` in the body, which every proxy and uptime monitor
ignores.

The response body never contains the driver exception: it can carry the
DSN, host and credentials. The detail is logged server-side instead.

**Decision — list cost is a test, not a hope.**

The payments list ran two queries per row (allocations + their sum), so a
100-row page issued 201 statements. `allocation_state_for_payments` fetches
the page's allocation rows once and derives both facts from them.

`test_payments_list.py` counts statements for `limit=1` and `limit=3` and
asserts they are equal. Timing tests are flaky in CI and a passing response
body says nothing about query count; the statement count is the invariant
that matters.

The redundant `payment_service.unallocated_amount` was deleted: two
implementations of one number is how they drift.

**Decision — one index migration for list ordering and search.**

Migration `e52b47e5ff15` adds:

| Index | Serves |
|---|---|
| `deliveries (delivered_at, id)` | delivery list, newest first |
| `payments (paid_at, id)` | payment list, newest first |
| `notifications (created_at)` | notification list |
| `farmers (created_at)` | farmer list, newest first |
| `gin lower(first_name) gin_trgm_ops` | farmer search |
| `gin lower(last_name) gin_trgm_ops` | farmer search |
| `gin phone gin_trgm_ops` | farmer search |

`id` is part of the two event indexes because those lists sort by
`(timestamp DESC, id DESC)`; without it Postgres does an incremental sort
inside every equal-timestamp group, which is the wrong shape when a clerk
bulk-enters rows.

Search is `lower(col) LIKE '%q%'`. No btree can serve a leading wildcard,
so it was a sequential scan regardless of what we added; `pg_trgm`'s GIN
operator class is the index that actually applies. The extension is created
at the top of `upgrade()` — the same prerequisite class as `btree_gist` in
D-007 and D-013's failure mode 2.

Verified with `EXPLAIN` on the live database (`enable_seqscan = off`, so
the planner must choose an index): delivery and payment lists are now
**Index Only Scan Backward** with no sort node, notifications and farmers
are index scans, and farmer search is a `BitmapOr` over the three trigram
indexes. At 154 seed rows the planner still prefers a sequential scan for
the small tables — expected, and the reason the check disables it.

**Decision — configuration is configuration.**

CORS origins moved from a hardcoded list in `main.py` to `CORS_ORIGINS`, so
a new frontend origin is an env change. `SECRET_KEY` was removed as dead
config (see the amendment in D-012). Also fixed: a duplicated import in
`ledger.py` and an `__import__("datetime")` expression in the statement
router.

**Verification:**
- 27 backend tests pass (4 concurrency tests still deselected).
- Health: `GET /health/db` against an unreachable database returns
  `503 {"status":"error","database":"unreachable"}` while `/health`
  returns 200; the credentials in the failing DSN appear nowhere in the
  response or the log.
- Migration applies, reverses and re-applies cleanly.
- `EXPLAIN` output recorded above.

**Consequences:**
- A load balancer can now act on the readiness answer.
- Payments page cost is flat: 4 statements for 1 row or 100.
- Search stays index-backed as long as the predicate keeps the same
  expressions; changing it means changing the index in the same commit.

**Reversal triggers:**
- If readiness probing on every health check becomes noisy, split it into a
  cached check with a short TTL — but the 503 must stay.
- If a table gains server-side sorting on arbitrary columns, index strategy
  moves to per-endpoint analysis rather than list ordering.

## D-029 — Phase 2: request ids, structured logs, and an honest 500

**Date:** 2026-10-20
**Status:** Accepted

**Context:**
Phase 1 made the failure *paths* correct. Phase 2 makes them **legible**. An
unhandled error used to produce a bare `Internal Server Error` with no body:
a clerk reporting it had nothing to quote, and the operator had to correlate
by timestamp against interleaved uvicorn lines.

**Decision — one id per request, in a contextvar.**

`RequestContextMiddleware` generates a UUID (or echoes a client's
`X-Request-ID` when it is 1–128 chars of `[A-Za-z0-9._:-]`) and stores it in a
`ContextVar`. Every log call in the request — router, service, library — is
tagged without threading a parameter through signatures.

A caller-supplied id is only echoed when it passes the charset check. An
unvalidated value would be a log-injection and header-injection vector;
replacing it with a fresh id is the safe failure mode.

The id is returned on **every** response, not just errors, and is listed in
CORS `expose_headers` so the browser can read it.

**Decision — one JSON object per line.**

The access log line carries `method`, `path`, `status`, `duration_ms` and
`request_id`. Requests at or over `SLOW_REQUEST_MS` (default 500 ms) log at
WARNING, so slow endpoints surface without a separate metric pipeline.

Hand-rolled formatter (`app/core/logging.py`, ~60 lines) rather than adding
`structlog`/`python-json-logger`: the requirement is one shape, and a
dependency that owns the logging config is harder to keep out of pytest's
capture. `LOG_JSON=false` switches to plain lines for local work.

The handler is added to the root logger, never replacing existing handlers —
clobbering them silently disables pytest capture and any host's logging.

**Decision — a 500 is JSON, and the traceback stays server-side.**

Unhandled exceptions return:

    {"detail": "Internal server error", "request_id": "<id>"}

with the same id in the `X-Request-ID` header. The traceback is logged with
the id and never sent to the client — it is the difference between "a clerk
can report this" and "a clerk can exfiltrate the internals".

The middleware catches first; an `Exception` handler is registered as a
backstop for failures raised above it (or by middleware added later).
Middleware order matters here and is documented at the call site: CORS is
added **after** the request context so it ends up outermost, otherwise a 500
would reach the browser without CORS headers and the frontend would show a
network error instead of the message.

**Decision — timeouts and fail-fast configuration.**

- `statement_timeout` (default 5000 ms) is set per connection via the
  driver, so Postgres enforces it on any statement including lock waits. A
  stuck query cannot hold a pool slot indefinitely.
- Pool `size` / `max_overflow` / `timeout` / `recycle` are settings, not
  defaults buried in a constructor.
- Configuration is validated when `Settings` is constructed: JWT key shorter
  than 32 characters, a non-PostgreSQL `DATABASE_URL`, an unknown
  `LOG_LEVEL`, or an empty CORS list now stop the process from booting. A
  misconfigured deployment fails at start, not at 14:02 under load.

**Rejected:** OpenTelemetry tracing. Request ids plus durations answer the
questions we actually have at this stage; distributed tracing without
multiple services is ceremony. Revisit when a worker and the API need a
shared trace.

**Verified:**
- 33 tests pass (6 new in `test_observability.py`).
- Live: a response with no id gets a generated one; `X-Request-ID:
  trace-live-1` is echoed; the access line is one JSON object containing the
  id, method, path, status and duration.
- Live 500 (valid token, unreachable database): body is
  `{"detail":"Internal server error","request_id":"trace-live-500"}`, the
  header is present, the response contains no traceback, and the server log
  line for the same id carries the full `exc_info`.
- `SHOW statement_timeout` on an application connection returns `5s`.
- Boot refuses on a short `JWT_SECRET_KEY` and on a `mysql://` URL; valid
  config still imports cleanly.

**Consequences:**
- Every support report can be tied to one log line.
- Slow endpoints are visible in the log stream without new infrastructure.
- Configuration errors surface at deploy time.

**Reversal triggers:**
- If logs become a cost problem, sample successful requests (never errors).
- If a second service appears, the request id stays the correlation key and
  the id becomes a W3C `traceparent`.
- If structured logs need to be queried rather than shipped, that is a
  logging-backend decision, not an application one.

## D-030 — Phase 3: auth is a session system, not just a token

**Date:** 2026-10-20
**Status:** Accepted

**Context:**
Phase 1–2 left three holes that matter the moment this carries real
cooperative money:

1. **No cost to guessing.** `/auth/login` verified Argon2 hashes as fast as a
   client could ask. A stolen email plus a common password was a matter of
   time, not of luck.
2. **Logout was client-side theatre.** The frontend deleted its copy of the
   JWT; the token itself stayed valid for its full 12 hours. Anyone holding a
   copy — a shared laptop, a proxy log, an old device — kept access after the
   user believed they had signed out.
3. **No way to change a password**, and therefore no way to respond to a
   suspected compromise.

**Decision — throttle per account, and deliberately not per client IP.**

`LOGIN_MAX_ATTEMPTS` (5) failures inside `LOGIN_WINDOW_SECONDS` (15 min) lock
the email for `LOGIN_LOCKOUT_SECONDS` (15 min). Each further lockout for the
same account doubles, capped at 24 h, so a sustained attacker's cost grows
while a clerk who fat-fingered five times waits one window.

The obvious implementation — count failures per `request.client.host` — is
wrong for this deployment and we rejected it after writing it:

- Behind any load balancer `request.client.host` is the *balancer*, so five
  bad passwords from one person lock out the whole cooperative.
- Even with no proxy, a rural office or cybercafé shares one NAT address. One
  mistyping user must not stop their colleagues from working.

Credential spraying (one password, many accounts) is real but is the wrong
shape for this layer: it needs true client addresses and volumetric limits,
which belong at the reverse proxy / WAF. This table protects *an account from
being ground down*, which is the attack we can see and bound here. The
trade-off is documented rather than pretended away.

**Decision — the lock is checked before the password, and says so.**

The attempt that crosses the threshold answers `429` with `Retry-After`
instead of `401`, and later attempts are refused without verifying the
credential — so the correct password does not slip through a locked account.
`429` is used rather than `401` because the caller is not being told their
password is wrong; they are being told to stop.

Identifiers are SHA-256 hashed into the Redis keys. A Redis dump should not be
a list of staff email addresses, and an email containing `:` cannot forge a key
shape.

**Fail open, loudly.** If Redis is unreachable the attempt is allowed and a
warning is logged. Locking every user out of the system because the throttling
store is down is worse than briefly losing throttling — and an auth outage is
a bigger prize than a slower brute force.

**Decision — logout revokes one token; password change revokes all of them.**

Two mechanisms, because they answer different questions:

- Every JWT carries a `jti`. `POST /auth/logout` writes that `jti` to a Redis
  denylist with a TTL equal to the token's remaining lifetime, so the entry
  expires exactly when the token would have. Other sessions of the same user
  stay valid — that is what "sign out this device" should mean.
- `users.token_version` (new column, default 0) is baked into the token as
  `ver`. `get_current_user` compares it to the row on every request, and a
  password change increments it. Every token minted before the change dies at
  once, including the one that made the request. Tokens issued before this
  migration have no `ver` and read as 0, so they survive until they expire
  rather than logging everyone out on deploy.

A denylist that is checked on every request is a cache lookup on the hot
path; at our scale that is cheaper than the alternative (database-backed
sessions) and it keeps the API stateless apart from one Redis key. Missing
`jti` (a malformed or hand-made token) is treated as not revoked — signature
verification already rejected anything we did not mint.

The two checks live in one helper (`deps.assert_token_current`) because
`/auth/register` carries its own guard: it must accept *no* token when the
users table is empty (bootstrap), so it cannot simply depend on
`get_current_user`. Duplicating the logic there would have re-opened the hole
this phase closes — a revoked admin token could still create users. It now
calls the same helper, and a test pins it.

**Decision — passwords have a floor (10), not a personality.**

`MIN_PASSWORD_LENGTH = 10`, shared by registration and password change so "a
valid password" means one thing everywhere. No complexity rules: they push
people toward `Password1!` and the predictable mutations around it. Argon2id
at 64 MB / t=2 is what makes guessing expensive. Reusing the current password
is rejected (422), because a "change" that changes nothing is not a change.

**Decision — security headers on every response.**

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`.
`Strict-Transport-Security` is only sent over HTTPS — asserting it on a plain
HTTP dev server teaches browsers to remember a promise the server cannot keep.

**Bug found while testing this (and fixed at the cause):**

The new password-change test failed with a row that vanished mid-request. The
cause was not auth: `write_transaction()` closed the caller's open transaction
with a **rollback**. In tests, fixtures flush their rows into the surrounding
savepoint, so that rollback deleted them; an update-only service then updated
zero rows and the data disappeared. Delivery and payment tests only passed
because their services flush *new* objects afterwards, which re-inserted the
fixtures by accident. `write_transaction()` now **commits** the caller's work
before opening its own transaction — a rollback there was silently discarding
the caller's writes in production too, which is the worse of the two failures.
Pinned by `app/tests/test_transaction.py`.

**Verified:**
- 53 tests pass, including the 4 money-concurrency tests that had never been
  run (`pytest app/tests`, exit 0).
- Migration `3f4dcebc9d6d_add_user_token_version` applies cleanly to head.
- `tsc -b`, `oxlint` (0 errors) and `npm run build` clean; the new `/account`
  screen and the `429` path were built, not just written.

**Consequences:**
- A locked account cannot be unlocked by the user; an admin must wait out the
  window or the operator must clear the key. At 15 minutes that is acceptable.
- Redis is now on the login path (fail-open) and on every authenticated
  request (denylist). The `/health/redis` endpoint already reports it.
- The client must treat a successful password change as a sign-out. It does:
  `/account` redirects to `/login?changed=1` with a message.

**Reversal triggers:**
- If spraying becomes visible in the logs, add IP/ASN limiting at the proxy —
  not in the app, where the address is the balancer's.
- If Redis latency shows up in authenticated request p99, cache the denylist
  check per user per request or move revocation into the `ver` claim alone.
- If we add refresh tokens, `jti` revocation becomes the refresh-token store's
  job and the denylist shrinks to the access-token lifetime (minutes).

## D-031 — Deductions: money withheld, not money owed

A cooperative withholds before it pays. Transport from the collection point,
cess to the county, recovery of input credit, a loan instalment, the
membership fee, withholding tax. Without a place to record that, the ledger
says a farmer is owed the full value of their produce and every settlement is
done off-system, in a notebook.

**Decision — a deduction is a third signing direction, and it changes neither
debt nor credit.**

The obvious-looking alternative was to model a deduction as a payment with a
negative amount. That is wrong, and the reason is worth stating: a payment is
money the co-op *received on the member's behalf*, so it raises
`available_credit` and is allocatable against future deliveries. A deduction is
money the member *owes the co-op or asked it to remit elsewhere*. It is never
credit — the co-op cannot pay it out later — so folding it into `payments`
would let a member "spend" money that was withheld from them.

So the ledger gains one derived figure and no new arithmetic:

```
outstanding_debt = Σ delivery value − Σ allocations
available_credit = Σ payments − Σ allocations
deductions_total = Σ deduction amounts          (charges net of reversals)
net_payable      = outstanding_debt − available_credit − deductions_total
```

`net_payable` is the number a settlement actually hands over, and it can go
negative — that is arrears, and it is the case deductions exist to make
reachable. Before this, a member who owed the co-op simply had no
representation; `net_payable < 0` is now a query.

`deductions_total` is deliberately **not** folded into `outstanding_debt`.
Keep the two separate and a screen can say "we owe you 4,000, of which 1,200 is
transport and cess, so 2,800 is yours". Merge them and that sentence becomes
unrecoverable, because the reason codes are gone.

**Decision — reversals are same-table negative rows, as everywhere else.**

`reversal_of_id` points at the original; the amount is negative; aggregation is
`SUM(amount)` and the sign does the work. A unique constraint on
`reversal_of_id` means one reversal per charge, enforced by the database rather
than by a check-then-insert in Python. A reversal copies the original's
`applied_at`, so a correction lands in the period it corrects (D-019), and the
original keeps its amount and stays visible: a charge that was withdrawn is
part of the record.

**Decision — `reason_code` is a closed set, in the model and in the CHECK.**

Eight values: transport, cess, input_credit, loan_recovery, membership_fee,
withholding_tax, fine, other. Same reasoning as the audit action set — a typo
in a money field must fail loudly instead of creating an unreportable row. The
cost is that a real ninth reason needs a migration (woods: drop and recreate
the CHECK).

**Decision — clerks record, admins reverse.**

Recording is the field action and blocking it would push the work back into the
notebook. Reversal moves money back into a member's payable, so it is
supervisory. Same split as payments (D-020), for the same reason.

**One bug found while testing:**

The first version ordered statement events by `(date, kind, id)`. A reversal
copies its original's `applied_at`, so the two always tie, and the UUID
tie-break sometimes put the reversal *before* its charge — the running
withheld total dipped negative and then recovered, for no reason a reader could
see. Deductions now rank `deduction` before `deduction_reversal` explicitly.
Payments have the same latent tie and are left alone here: changing their order
is a separate decision with its own test, not a side effect of this one.

**Verified:**
- `pytest app/tests` — 123 tests pass, including 20 new deduction tests
  (record, closed-set reason, positive amount, permissions, double reversal,
  reversal-of-reversal, balance, statement, CSV, ordering).
- `ruff check` and `ruff format --check` clean on `app/` and `scripts/`.
- Migration `c7a3f1e05b84` creates the table and widens the audit action CHECK.

**Consequences:**
- `/farmers/{id}/balance` and the statement gained `deductions_total` and
  `net_payable`; both are additive, so existing clients keep working.
- The dashboard does not yet show withheld totals. It reads debt only, so its
  figure is "owed before withholding" — accurate but incomplete.
- A deduction is recorded as a fact; it does not allocate against a specific
  delivery. If a co-op ever needs per-delivery withholding, that is a new
  column (`delivery_id`) and a new decision, not a reinterpretation of this one.

**Reversal triggers:**
- If clerks start recording deductions that belong to one delivery, add
  `delivery_id` and a per-delivery reconciliation report.
- If `net_payable` negative goes unnoticed by the UI, add a dashboard tile for
  members in arrears — the number exists and nobody is looking at it.
- If a ninth reason code appears twice in one season, promote reason codes to a
  table instead of a CHECK.
