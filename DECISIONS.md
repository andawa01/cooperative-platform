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