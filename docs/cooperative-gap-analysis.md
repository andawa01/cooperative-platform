# Farm cooperative capability map & gap analysis

**Date:** 2026-10-31
**Status:** Working document — the backlog below is the ordered "build one by one" list.
**Progress (2026-11-07):** Wave 0 closed (statements screen, audit screen, list exports, user management, receipt numbers); Wave 1 closed (deduction ledger, payment runs, M-Pesa/bank rail files, payment advice SMS, maker-checker approvals). Wave 2 started: **2.1 collection points + structured geography is built**; clerk scoping and route planning remain (3.4 / 2.1 follow-on).
**Scope:** What a real East African farm cooperative (coffee / tea / dairy / banana) actually
runs on, what ShambaTrack covers today, and what is missing.

---

## 1. The framing

ShambaTrack today models **one leg** of a cooperative's operating cycle extremely well:

> produce in → valued at a frozen rate → money out → corrections by reversal.

That leg is the hardest to get right, and the codebase is unusually honest about it
(immutable deliveries, derived balances, idempotent payments, concurrency tests).

A real cooperative's full cycle has **six more legs** that the system does not have:

```
member joins (shares, fees, farm/plot)
      ↓
gets inputs on credit (fertiliser, seed, spray)  ← missing
      ↓
delivers to a collection point                    ← partly (no collection point, no structured location)
      ↓
produce is graded / tested / weighed / rejected    ← missing
      ↓
valued at the season price                        ← ✓ have
      ↓
deductions applied (inputs, loans, transport, levies) ← missing — this is the biggest financial gap
      ↓
paid via a payout run (M-Pesa / bank batch)        ← partly (single payments only, no batch or rail)
      ↓
patronage dividend / second payment                ← missing
      ↓
statement + dispute if the math is questioned      ← statement ✓ (API only), dispute ✗
```

The single most consequential omission: **real take-home pay is not `quantity × rate`.**
It is `quantity × rate − deductions`. Today `compute_balance()` ends at gross delivery value,
so the number the system produces is not the number the farmer is handed.

---

## 2. Capability map

Legend: **✓ built** · **◐ partial** (backend without UI, or a simplified version) · **✗ missing**

### A. Membership & cooperative structure

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Cooperative / society / branch entity | Co-op has branches, each with collection points and staff | ✗ single implicit co-op | No `cooperative` table; every query is global. Blocks multi-co-op and per-branch reporting. |
| Member register | Member number, join date, membership status, share capital, joining fee | ◐ `farmers` with status lifecycle; no member number, no join date, no shares | Farmers exist as *suppliers*, not *members*. |
| Share capital & dividends | Members buy shares; surplus is shared as dividends | ✗ | No share ledger, no dividend run. |
| Patronage refund (second payment) | Coffee paid in 2 instalments; final payment based on volume sold | ✗ | Deliberately modelled as `payment` but no "season settlement" concept. |
| Farmer group / SHG / co-op chapter | Deliveries and training often via a group | ✗ | No group entity. |
| Membership application / approval | Form → committee approval → member number issued | ◐ `pending_verification → active` + verify endpoint | Close; missing documents and a real approve/reject flow with reason. |
| Roles beyond admin/clerk | Accountant, auditor, warehouse clerk, extension officer, collection-point clerk, board (read-only) | ✗ (2 roles) | Blocks segregation of duties (see A below). |
| Staff ↔ branch assignment | A clerk only records for their collection point | ✗ | Any clerk can act on any farmer. Not a tenancy, but a scope. |

### B. Farmer & farm master data

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Farm / plot record | Plot size (acres), GPS point/polygon, soil, altitude, tenure | ✗ `farmer.location` is free text and explicitly not used in logic | The `Farm` entity is referenced in a code comment but does not exist. |
| Structured geography | County → ward → village → zone → route | ◐ county/ward/zone on the collection point (D-039) | Routes and village-level catchment still missing. |
| Household & demographics | Gender, age, household size, next of kin | ◐ `date_of_birth` only | Gender/age are required for most grant and certification reporting. |
| Identity documents | ID copy, photo, consent signature | ✗ | Only a `national_id` string. |
| Certification status | Organic / Fairtrade / Rainforest Alliance member flag | ✗ | Needed before traceability work. |
| Farmer as a system user | Farmer checks own balance/history | ✗ | D-6 states a farmer is deliberately not a `User`. Intentional, but the member-facing surface is now the largest adoption gap. |

### C. Intake, quality & weighing

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Collection point | Named point with a clerk, scale, and opening hours | ✓ `collection_points` entity, member home point, per-delivery point, scale id, retire-not-delete, production-by-point report (D-039) | Opening hours and a clerk assignment are not modelled yet. |
| Delivery ticket / receipt number | Sequential slip handed to the farmer, quoted in disputes | ✗ | No human-readable reference; UUIDs are not quotable by a farmer. |
| Weighing & scale integration | Weight from a scale, bag count, tare | ◐ a single `quantity` entered by hand | No bag/tare breakdown, no scale capture, no weighing tolerances. |
| Quality grading | Grade A/B/C, moisture content, defects, rejection | ✗ | **No grade on a delivery at all**, so quality premiums and rejections are impossible. |
| Rejections & partial acceptance | 100 kg in, 12 kg rejected (wet/mouldy), 88 kg paid | ✗ | Reversals are all-or-nothing (D-008 explicitly rules out partials). A rejection is *not* a reversal — it needs its own model. |
| Dairy-specific tests | AM/PM shift, litres, fat %, SNF, lactometer, adulteration, rejects | ✗ | Milk is priced on composition in reality; a flat KES/litre rate is a simplification. |
| Seasonal / crop windows | Coffee cherry season opens and closes | ✗ | No season entity, so no season-over-season comparison. |

### D. Pricing & settlement

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Effective-dated rate per produce line | ✓ | ✓ | — |
| Grade-based / quality premiums | Rate per grade, premium for A | ✗ | Depends on C (grading). |
| Deductions | Transport, cess/levy, input credit recovery, loan repayment, fines, union fees, withholding tax | ✗ | **Largest gap.** Needs signed ledger entries with a reason code, applied at settlement, visible on the statement. |
| Advance / first payment + final payment | Paid 60% at intake, balance after sale | ◐ overpayment = "credit on account" | No season settlement concept; credit exists but is not tied to a season. |
| Payment runs / batches | One approval, 400 farmers paid, one file to the bank | ✗ one payment per farmer per call | Needs a batch entity, selection criteria, approval, and per-row results. |
| Payout rails | M-Pesa B2C, bank EFT, cash | ◐ `method` free string | No gateway, no per-row status, no retry of failed rows. |
| Payment advice | SMS: "KES 4,120 sent, M-Pesa ref XYZ" | ◐ generic `payment_recorded` SMS | No amount breakdown/deductions in the message. |
| Statutory reporting | Levy remittance to county/ministry | ✗ | Needs a levy/deduction report. |

### E. Financial services & farm inputs

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Input / farm store | Sells fertiliser, seed, spray — cash or on credit | ✗ | No product catalog, stock, price list, or issue note. |
| Input credit against produce | "Take 2 bags now, we deduct from your cherry" | ✗ | Same gap as D (deductions) plus a receivable per farmer. |
| Farmer loans / advances | Seasonal advance, repayment schedule, guarantors, interest | ◐ advances exist as unallocated payment credit | No loan entity, no schedule, no arrears, no ageing. |
| Credit scoring / credit-readiness statement | Co-op vouches for a member to a bank using delivery history | ◐ the statement exists as evidence | No score, no exportable lender pack, no consent. |
| Savings (SACCO arm) | Deposits, withdrawals, share transfers | ✗ | Different ledger; only build if the co-op actually runs a SACCO. |
| Crop / livestock insurance | Premium collected via deduction, claims | ✗ | Depends on D. |

### F. Extension & field services

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Training sessions & attendance | Field days, attendance register, per-member training history | ✗ | |
| Extension officer visits | Visit log, advice given, follow-up | ✗ | |
| SMS advisories | Weather, pest alerts, price announcements to a segment | ◐ outbound SMS exists but only 2 templates tied to a delivery/payment | No broadcast/segment, no consent/opt-out, no cost cap. |
| Demo plots / farmer field schools | | ✗ | |
| Input distribution programmes | Donor/grant e-voucher distribution | ✗ | |

### G. Logistics & assets

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Transport & route | Pickup schedule, vehicle, driver, cost per kg | ✗ | |
| Consignment to processor/buyer | Delivery note: X kg from point A to mill B | ✗ | |
| Warehouse / store inventory | Intake to store, stock movements, dispatches, stocktake, shrinkage | ✗ | No inventory model at all. |
| Equipment / machinery hire | Tractor booking, hours, hire fee | ✗ | Common co-op revenue line. |

### H. Traceability & compliance

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Batch / lot tracking | Plot → collection point → lot → export consignment | ✗ | Deliveries have no lot linkage. |
| Certification audits | Fairtrade/RA/Organic evidence packs | ✗ | Needs member certification + input records + training records. |
| Deforestation / EUDR compliance | Plot geolocation + legality evidence | ✗ | Needs B (plots with GPS). |
| Pesticide / residue records | What was applied, when, withdrawal period | ✗ | Needs an input-application log. |
| Data-protection consent | Consent captured at registration | ✗ | |

### I. Disputes & corrections

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Correction by reversal | ✓ | ✓ | Best-in-class already. |
| Formal dispute | Farmer contests a weight/grade/payment → ticket → investigation → resolution | ✗ | A reversal is an *outcome*, not a workflow. No ticket, no SLA, no evidence, no farmer-initiated channel. |
| Partial correction | "20 kg of the 100 kg was wet" | ✗ | D-008 rules out partials. Rejections (C) are the cleaner answer. |
| Dual control on money writes | Second approver for reversals above a threshold | ✗ | A single admin can reverse any payment. |

### J. Reporting & operations

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Dashboard | ✓ (aggregate, ledger-consistent) | ✓ | |
| Farmer statement | ✓ API | ◐ **no screen in the UI** | `/statements` is unrouted in the frontend. |
| Audit trail | ✓ API, 11 action types | ◐ **no screen in the UI** | Nobody can read it without curl. |
| CSV / PDF export | Every list exported for the accountant | ✗ | Blocks month-end close in practice. |
| Production by zone / point / grade | Management's weekly question | ◐ by point (net quantity/value, unassigned included) | By zone and by grade still missing (grade is 2.2). |
| Season-over-season yield | | ✗ | Needs seasons. |
| Farmer retention / churn | Members who stopped delivering | ✗ | Derivable today, not exposed. |
| Regulatory / annual report pack | | ✗ | |
| Sorting & bulk actions on lists | | ✗ (documented in D-027) | |

### K. Field reality & access

| Capability | What a real co-op does | ShambaTrack | Gap |
|---|---|---|---|
| Works offline, syncs later | Clerks at rural points lose signal | ✗ | Named as an expansion area; nothing built. |
| Receipt printing / SMS receipt | Farmer leaves with proof | ◐ SMS on delivery | No receipt number, no print. |
| Barcode / QR member cards | Scan the member card at intake | ✗ | |
| Swahili / local language | | ✗ | UI is English-only. |
| Low-end Android performance | | ◐ mobile-first design | Not measured on a real device. |

---

## 3. The five gaps that change what the system *is*

Ranked by how much they distort the product if left out:

1. **Deductions.** Without them the ledger's output is gross value, and no co-op can pay from it.
2. **Grading / rejection.** Without them quality is invisible and every delivery is "the same stuff".
3. **Collection points + structured geography.** Without them there is no branch, no route, no zone,
   and no way to scope a clerk to their own point.
4. **Payment runs + a payout rail.** Recording payments one at a time does not match paying
   400 members on the 5th of the month.
5. **A member-facing surface.** Everything is clerk-mediated. A farmer cannot check their own balance,
   which is precisely the trust problem the brief names.

---

## 4. Build backlog (one by one)

Ordered so each item ships on top of what exists, with the fewest forced rewrites.
Sizes are relative: **S** ≈ a day, **M** ≈ a few days, **L** ≈ a week or more.

### Wave 0 — close the loops already built (no new domain)

| # | Item | Size | Notes |
|---|---|---|---|
| 0.1 | Statements screen in the frontend | S | API exists (`GET /farmers/{id}/statement`); route + print view. Highest value per hour in the whole list. |
| 0.2 | Audit log screen (admin) | S | API exists; filter by action/actor/date. Makes the security work visible. |
| 0.3 | CSV export on every list | S | Server-side streaming export; the accountant's first request in every demo. |
| 0.4 | User management (admin) | M | List users, create, change role, deactivate. Today roles can only be set at registration. |
| 0.5 | Delivery receipt number | S | Human-readable sequential ref (per co-op, per year) quoted by farmers and printed on the SMS. |

### Wave 1 — make the money match reality

| # | Item | Size | Depends on | Notes |
|---|---|---|---|---|
| 1.1 | **Deduction ledger** | L | — | New `deduction` rows (signed, reversal-capable, `reason_code`, `rate`/`amount`, source entity). `compute_balance` gains `net_payable = value − allocations − deductions`. Reason codes seeded: transport, cess, input credit, loan recovery, fee, withholding tax. Statement gains a deduction line. **Forces a D-03x decision: deductions are liabilities of the member, so they change the definition of "outstanding debt".** |
| 1.2 | **Payment runs** | L | 1.1 | `payout_batch` + `payout_item`; select members with payable > 0; approve (admin) → dispatch; per-item status (pending/sent/failed); retry failed; idempotent per item. |
| 1.3 | Payout rail (M-Pesa B2C / bank file) | M | 1.2 | Start with a generated bank/CSV file (no vendor dependency), then one gateway integration behind the same interface. Webhook or poll for per-row result. |
| 1.4 | Payment advice SMS with breakdown | S | 1.1 | "KES 3,980 sent. Cherry 80kg = 4,800, less input 620, transport 200." |
| 1.5 | Maker-checker on money writes | M | — | Reversals and rate changes above a threshold require a second admin. New `approval_request` table; endpoints stay the same. |

### Wave 2 — intake fidelity

| # | Item | Size | Depends on | Notes |
|---|---|---|---|---|
| 2.1 | **Collection points + structured geography** | M | — | **Shipped 2026-11-07 (D-039):** `collection_points` (name, unique canonical code, county/ward/zone, scale id, active flag), `farmer.collection_point_id`, `delivery.collection_point_id` (inherits the member's point, independent of later moves), delivery/farmer filters, and `GET /reports/production-by-point` (net intake, reversals included, unassigned row). **Remaining:** clerk-to-point scoping (belongs with 3.4 expanded roles) and route planning. |
| 2.2 | **Grading & quality** | L | 2.1 | `produce_grade` + rate per grade; `delivery.grade`, `delivery.moisture`, `delivery.rejected_quantity`. Rejected quantity is *not* a reversal — it is a separate fact with a reason. Forces a D-03x decision on partial acceptance. |
| 2.3 | Dairy tests (shift, fat, SNF) | M | 2.2 | Only if the co-op is dairy; otherwise skip. |
| 2.4 | Seasons | M | — | `season` entity; deliveries, rates and payouts tagged by season. Enables season-over-season reporting and the "final payment" concept. |
| 2.5 | Weighing capture (bag count, tare, scale) | S | 2.1 | Bags + tare with a computed net weight; keeps `quantity` as the single truth. |

### Wave 3 — membership & organisation

| # | Item | Size | Depends on | Notes |
|---|---|---|---|---|
| 3.1 | **Cooperative / branch tenancy** | L | — | `cooperative_id` on every tenant-owned table + a scoping dependency. The largest structural change in the list; do it before the data gets real. |
| 3.2 | Member register: member number, join date, shares | M | 3.1 | Sequential member number per co-op; share purchases as ledger entries; joining fee as a deduction. |
| 3.3 | Farm / plot records with GPS + size | M | 2.1 | Unlocks yield-per-hectare, zone maps, EUDR groundwork. |
| 3.4 | Expanded roles + scope | M | 3.1 | accountant, auditor (read-only), warehouse, extension, collection-point clerk, member. Mirrors the `require_role` model; add a resource-scope check where needed. |
| 3.5 | Committees / governance records | S | 3.1 | Board and committee membership, meeting minutes attachments. Low priority, cheap. |

### Wave 4 — services to members

| # | Item | Size | Depends on | Notes |
|---|---|---|---|---|
| 4.1 | **Farm store + input credit** | L | 1.1 | Products, stock, price list, issue note, member receivable. The receivable is settled by a deduction at payout — the loop closes with 1.1. |
| 4.2 | Loans / advances with schedules | L | 4.1 | Principal, schedule, arrears, ageing, penalty; recovery via deduction. |
| 4.3 | Credit-readiness pack | M | 4.2 | Exportable lender summary from delivery + repayment history, with member consent. |
| 4.4 | Extension: sessions, attendance, visits | M | 3.4 | Simple entities + attendance grid; feeds certification evidence. |
| 4.5 | Broadcast / segmented SMS + consent | M | — | Opt-out, per-segment targeting, spend cap. |
| 4.6 | Equipment hire | S | 1.1 | Booking + fee as a deduction. |

### Wave 5 — supply chain & compliance

| # | Item | Size | Depends on | Notes |
|---|---|---|---|---|
| 5.1 | Warehouse inventory & lot tracking | L | 2.1, 2.2 | Intake, transfers, dispatch, stocktake, shrinkage; lot id per delivery. |
| 5.2 | Consignments to buyer | M | 5.1 | Delivery note, weights, buyer, settlement back to members. |
| 5.3 | Certification & compliance records | M | 3.3, 4.4 | Member certification, input application log, evidence pack. |
| 5.4 | Disputes workflow | M | 0.1, 2.2 | Ticket (weight/grade/payment), evidence, assignee, SLA, resolution → triggers reversal/deduction. Farmer can raise via SMS/USSD. |
| 5.5 | Period close & lock | M | 1.1 | Close a month/season: no writes to locked periods without an explicit reopening (audited). |

### Wave 6 — field reality & access

| # | Item | Size | Depends on | Notes |
|---|---|---|---|---|
| 6.1 | Offline-first intake PWA + sync queue | L | 2.1, 2.2 | Client-side queue with idempotency keys (the API already supports them for payments; deliveries need the same). Conflict policy: server wins, clerk is told. |
| 6.2 | Member self-service (USSD or lightweight web) | L | 0.1, 1.1 | Balance, last 5 deliveries, last payment, raise a dispute. USSD reaches feature phones; a web portal reaches smartphones. |
| 6.3 | Receipt printing + barcode member cards | M | 0.5, 2.1 | |
| 6.4 | Swahili localization | M | — | Extract strings; do it before the UI grows further. |

---

## 5. Recommended next three

If the goal is "a cooperative could actually run a season on this", build in this order:

1. **0.1 + 0.2 + 0.3** (statement screen, audit screen, CSV export) — one short wave that makes
   the existing depth visible. A week of work at most, and it changes how the product reads.
2. **1.1 Deductions, then 1.2 Payment runs** — turns "we computed what we owe you" into
   "we paid you, and here is the arithmetic". This is the credibility milestone.
3. **2.1 Collection points + 2.2 Grading** — turns one anonymous pile of produce into
   per-point, per-grade, per-zone reality, which is what management and buyers ask for.

Everything in Wave 3+ should wait until 1.x and 2.x have been used against real data;
tenancy in particular is cheaper to add once the shape of "what belongs to a co-op" is settled
by the features that came before it.

---

## 6. Decisions this backlog will force

Record these in `DECISIONS.md` before the corresponding code lands, not after:

- **D-03x — Deductions are a third ledger direction.** Does `outstanding_debt` become
  `value − allocations`, with deductions netted only at payout, or does a deduction immediately
  reduce what is owed? The statement's running pair (D-021) must stay coherent either way.
- **D-03x — Partial acceptance vs. reversal.** Grading introduces a quantity the co-op refuses
  to pay for. Is that a field on the delivery (`rejected_quantity`) or a separate negative
  entry? The former is honest to the physical event; the latter reuses the reversal machinery
  but contradicts D-008's "reversal undoes the whole delivery".
- **D-03x — Tenancy scope.** `cooperative_id` on every table, or a co-op-per-deployment model?
  The answer determines whether Wave 3.1 is a migration or a deployment decision.
- **D-03x — Who may move money.** Maker-checker thresholds, and whether a clerk can ever
  record a payout (today a clerk can create a payment, and only admin can reverse one).
- **D-03x — A farmer is a user.** D-002/D-006 deliberately kept farmers out of `users`.
  Member self-service forces a link table and a distinct permission scope — decide the shape
  before Wave 6.2, not during it.
