# Phase 2 — Sample Data & Scenarios

**Goal:** deterministic, fictional JSON datasets that cover every case in spec §4, and a final scenario table (resolves decision **D1**).

**Depends on:** Phase 1 · **Estimate:** 25 min · **Skills:** `python-engineering`

## Deliverables

| File | Content |
|---|---|
| `data/orders.json` | ~15 orders |
| `data/customers.json` | ~12 customers (fictional names, `@example.com`) |
| `data/support_tickets.json` | ~8 tickets |
| `data/subscriptions.json` | ~10 subscriptions |
| `src/common/schemas/enums.py` | Shared enums (below) |
| `src/common/schemas/domain.py` | Pydantic models: `Order`, `Customer`, `SupportTicket`, `Subscription` |
| `src/common/schemas/__init__.py` | Re-exports |
| `specs/specification.md` | §7 example ticket → ORD-1008; §16 scenario IDs finalized; "under revision" note removed |

## Shared enums (`src/common/schemas/enums.py`)

Use these everywhere: data, tools, `AgentProposal`, and guardrails.

- `OrderStatus`: `pending | processing | shipped | delivered | delayed | cancelled`
- `IssueType`: `delivery_delay | missing_order | cancelled_order | refund_request | subscription_issue | address_issue | other`
  The spec §3.1 example uses `delayed_order`, which maps to `delivery_delay`.
- `TicketStatus`: `open | in_progress | resolved | closed`. Only `open` and `in_progress` count as duplicates.
- `TicketPriority`: `low | medium | high | critical`
- `SubscriptionStatus`: `active | paused | cancelled | payment_failed`

## Reference date

`REFERENCE_DATE=2026-10-10`. Days late = `reference_date − expected_delivery_date`, applied when `actual_delivery_date` is null and the status is `delayed`/`shipped`. With this date, ORD-1007 (expected 2026-09-25) is exactly **15 days late** and ORD-1001 is **2 days late**, matching the scenario texts.

## Key records (proposal)

| Order | Customer | Status | Expected / actual | Total | Purpose |
|---|---|---|---|---|---|
| ORD-1001 | CUS-101 | delayed | 2026-10-08 / – | 89.50 | **Scenario 1**: 2 days late, no tickets |
| ORD-1002 | CUS-104 | pending | 2026-10-16 / – | 45.00 | Normal order |
| ORD-1003 | CUS-103 | processing | 2026-10-14 / – | 120.00 | Normal order |
| ORD-1004 | CUS-104 | shipped | 2026-10-12 / – | 64.99 | "Where is my order?" → LOW |
| ORD-1005 | CUS-105 | delivered | 2026-09-27 / 2026-09-26 | 150.00 | Delivered order |
| ORD-1006 | CUS-106 | cancelled | – | 75.00 | Cancelled order |
| ORD-1007 | CUS-102 | delayed | 2026-09-25 / – | 249.99 | **Scenario 2**: 15 days late + refund, **no open ticket** |
| ORD-1008 | CUS-107 | delayed | 2026-10-03 / – | 132.40 | **Scenario 3**: open ticket TCK-2001 exists |
| ORD-1009 | CUS-108 | delivered | 2026-10-01 / 2026-10-02 | 39.99 | Small refund (< $50) still needs approval |
| ORD-1010 | CUS-109 | shipped | 2026-10-13 / – | 560.00 | High-value, on time |
| ORD-1011 | CUS-110 | delayed | 2026-09-30 / – | 210.00 | Duplicate refund requests (2 open refund tickets) → CRITICAL |
| ORD-1015 | CUS-111 | delayed | 2026-09-22 / – | 1200.00 | **Optional scenario**: high-value refund |
| ORD-9999 | — | — | — | — | **Must not exist** (Scenario 4) |

Fill the rest (ORD-1012…1014) with ordinary orders to reach ~15.

Tickets:
- **TCK-2001** (CUS-107, ORD-1008, open, high, `delivery_delay`, 2026-10-05)
- **TCK-2002** and **TCK-2003** (CUS-110, ORD-1011, open, `refund_request`)
- **TCK-2004** (CUS-101, ORD-1001, **closed**, `delivery_delay`). A closed ticket must *not* block a new one.
- A few others.

Customer CUS-102 = "Alex Johnson" (spec §6). Subscriptions include SUB-301 (CUS-102, active, premium), one `payment_failed`, one `paused`, and one `cancelled`.

## Final scenarios (update spec §16 / §17)

| # | Input | Expected outcome |
|---|---|---|
| 1 | "My order ORD-1001 is two days late. Can you check what is happening?" | `completed`, MEDIUM; ticket + notification auto; no high-risk action |
| 2 | "My order ORD-1007 is 15 days late. I want a refund." | `awaiting_approval`, HIGH; ticket + notification auto; draft response; `issue_refund` → approval |
| 3 | "Please help with my delayed order ORD-1008." | Existing TCK-2001 reported; `create_support_ticket` **blocked** (duplicate); notification/follow-up recommended |
| 4 | "Please check order ORD-9999." | `not_found`; no invented data; no actions |
| 5 | "My order hasn't arrived and I want a refund." | `needs_more_info`; the LLM asks for the order ID in its own words; **no tool executes** and no actions run (D5) |
| 5b | Follow-up reply: "It's ORD-1007." (with Scenario 5 as `history`) | Continues as Scenario 2: refund → approval. Shows the agent resuming with full context |
| 6 (opt.) | "My order ORD-1015 is delayed. Please refund the order." | `awaiting_approval`, CRITICAL; refund → approval; ticket + notification auto with `critical` priority (D2) |

## Tasks

- [ ] Write the 4 JSON files following the tables above. Dates are ISO strings, amounts are numbers, currency is `USD`.
- [ ] Write `common/schemas/enums.py` and `domain.py` (no logic, no I/O). Every record must validate.
- [ ] Update spec §7 (ticket example → ORD-1008, CUS-107), §16, and §17 with the final table, and remove the "under revision" note.
- [ ] Write `test/test_data.py`. It asserts:
  - all records validate against the models;
  - IDs are unique;
  - every `customer_id` / `order_id` reference resolves;
  - ORD-9999 does not exist;
  - ORD-1007 has no open ticket;
  - ORD-1008 has an open ticket;
  - days late for ORD-1001 = 2 and for ORD-1007 = 15 at the reference date.

## Acceptance criteria

`uv run pytest test/test_data.py` passes. The scenario table matches the data.

## Out of scope

Loading data in the app (Phase 3).
