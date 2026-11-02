# Custom print request API

All routes are versioned under `/api/v1`. Customer operations require a bearer
token. Admin operations require a bearer token for an `ADMIN` user. Requests
are stored in MongoDB, with a unique reference index and compound indexes for
owner/status list ordering.

## Endpoints

| Method and path | Access | Result |
|---|---|---|
| `POST /print-requests` | `CUSTOMER` only | Create request; returns the full request (`201`). |
| `GET /print-requests?page=1&pageSize=10&q=&status=&sort=newest` | `CUSTOMER`, `ADMIN` | Paginated requests owned by the authenticated user. |
| `GET /print-requests/{id}` | `CUSTOMER`, `ADMIN` | Retrieve only a request owned by the authenticated user. |
| `POST /print-requests/{id}/messages` | `CUSTOMER` | Add a customer-visible message; body `{version,message}`. |
| `POST /print-requests/{id}/actions` | `CUSTOMER` | Approve/request changes to the current quote, or cancel; body `{version,action,quoteVersion?,message}`. |
| `GET /admin/print-requests?page=1&pageSize=10&q=&status=&sort=newest` | `ADMIN` | Paginated cross-customer list. |
| `GET /admin/print-requests/{id}` | `ADMIN` | Retrieve any request. |
| `POST /admin/print-requests/{id}/messages` | `ADMIN` | Add a customer-visible message; body `{version,message}`. |
| `POST /admin/print-requests/{id}/quote` | `ADMIN` | Publish a new immutable quote revision. |
| `POST /admin/print-requests/{id}/transition` | `ADMIN` | Apply an allowed workflow transition. |

List responses are `{items,total,page,pageSize}`. `sort` is `newest` or
`oldest`; `pageSize` is limited to 100. Search is server-side and matches
reference, title, and customer name/email within the authorized owner scope. Status filters
use the status values below. An unknown or another customer's request ID
returns `404`, including customer message/action attempts.

The full typed request response includes identity/contact snapshots, request
details, current status/version, quote revisions, customer-visible history,
tracking data and the role-specific `allowedTransitions` / `allowedActions`.
No private notes or payment credentials are returned. Names use camelCase,
including `allowedActions` and `allowedTransitions`. Optional unset fields
(`material`, `color`, `trackingUrl`, `estimatedShipping`, quote `approvedAt`)
are omitted, not serialized as `null`. Customer reads expose customer actions;
admin reads expose admin actions. Actions include `message`, `publish_quote`
(admin only), `approve_quote`, `request_changes`, and `cancel` as applicable.
Transitions are target status values and are empty for customer responses.
An expired quote is still visible for audit, but `approve_quote` is removed
from customer `allowedActions`. The mutation endpoint also enforces expiry;
UI action availability is not an authorization mechanism.

## Input validation

Creation requires title (3–150 characters), description (10–5000), positive
integer quantity (maximum 1000), dimensions (maximum 200), optional
material/color (maximum 100 each), and at most five reference URLs (maximum
2048 characters each). Reference URLs must be absolute `http` or `https`
links and cannot include credentials. These are stored as links only: the API
does not fetch them or accept binary uploads.

Messages and transition reasons are non-blank and at most 5000 characters.
`approve_quote` alone accepts an omitted/empty message: the server then writes a
descriptive approval history event. Cancellation and quote-change actions
require non-blank reasons. Quotes require positive
`amountCents` (maximum 100,000,000), `currency: "EUR"`, non-blank scope (at
most 5000 characters), positive `leadDays` (maximum 365), and a future
timezone-qualified `validUntil`. New quote versions are append-only; only the
current quote can be approved, and an expired quote cannot be approved.

## Workflow and concurrency

Every mutation requires the current request `version`. Updates use a single
MongoDB conditional update on ID, owner where applicable, version and current
status; stale or invalid mutations return `409` without partial writes. Unknown
IDs or IDs owned by another customer return `404`; schema validation returns
`422`; unauthenticated access returns `401`; a wrong actor role returns `403`.
Timestamps are UTC. Each accepted create, message, quote or status change
appends a customer-visible history event.

| Current status | Admin transitions | Customer actions |
|---|---|---|
| `submitted` | `under_review`, `rejected`, `cancelled` | `cancel` |
| `under_review` | `information_required`, `rejected`, `cancelled` | `cancel` |
| `information_required` | `rejected`, `cancelled` | `cancel` |
| `quote_changes_requested` | `rejected`, `cancelled` | `cancel` |
| `awaiting_quote_approval` | `rejected`, `cancelled` | `approve_quote`, `request_changes`, `cancel` |
| `awaiting_payment` | `payment_verification`, `payment_confirmed`, `rejected`, `cancelled` | `cancel` |
| `payment_verification` | `payment_confirmed`, `awaiting_payment`, `rejected`, `cancelled` | `cancel` |
| `payment_confirmed` | `in_production`, `cancelled` | — |
| `in_production` | `production_paused`, `shipped`, `cancelled` | — |
| `production_paused` | `in_production`, `cancelled` | — |
| `shipped` | `delivered`, `cancelled` | — |
| `delivered`, `rejected`, `cancelled` | — | — |

Each transition in the **Admin transitions** column requires an `ADMIN` actor
and a non-blank reason. Customer actions require the `CUSTOMER` owner. The
additional preconditions and non-transition operations are:

| Operation / actor | Preconditions and effect |
|---|---|
| Create / customer | Valid request details; ownership and contact snapshot derived from authenticated identity; starts `submitted`. |
| Publish quote / admin | From `under_review`, `quote_changes_requested`, or `awaiting_quote_approval`; positive EUR cents/lead time, future timezone-qualified validity; appends a new revision and enters `awaiting_quote_approval`. |
| Approve quote / owner | From `awaiting_quote_approval`; `quoteVersion` must match the latest saved, non-expired revision; records `approvedAt` and enters `awaiting_payment`. |
| Request quote changes / owner | From `awaiting_quote_approval`; latest `quoteVersion` and non-blank reason; enters `quote_changes_requested` without rewriting the quote. |
| Message / customer or admin | Non-terminal request, current version, non-blank message; preserves status, except an owner's reply to `information_required` returns to `under_review`. |
| Confirm payment / admin | From `awaiting_payment` or `payment_verification`; quote approval already completed; non-blank manual verification reason. Customers cannot confirm payment. |
| Start/resume production / admin | From `payment_confirmed` or `production_paused`; requires payment already confirmed and a reason. |
| Ship / admin | From `in_production`; reason required. `trackingUrl` is optional (omitted, null or blank); if supplied, it must be an absolute HTTP(S) URL. Optional `estimatedShipping` ISO date. |
| Deliver / admin | Only from `shipped`; reason required. |
| Cancel / owner | Only before `payment_confirmed`, including `payment_verification`; non-blank reason. |
| Cancel / admin | Any non-terminal state; non-blank reason, including after payment; no automatic refund. |
| Reject / admin | Only before payment confirmation; non-blank reason. |

Quote publication is accepted from `under_review`, `quote_changes_requested`
or `awaiting_quote_approval`, and moves the request to
`awaiting_quote_approval`. A customer reply while information is required
moves it back to `under_review`; other messages preserve status. Customers can
cancel through `payment_verification`, but not after payment confirmation.
Admin rejection is limited to pre-payment states. Admin cancellation is
available from any non-terminal state and requires a reason; it does not issue
or imply a refund. Transition messages are required, including manual payment
verification/confirmation. A tracking URL is mandatory for `shipped`.

Payment verification is manual. There is no payment gateway, payment proof
upload, shipping integration, notification/email delivery, automatic refund,
or external URL fetching.

## Verification and API compatibility

These ten routes exist under `/api/v1` only, without new legacy aliases.
All successful writes return the full typed request (`POST` create: `201`;
other writes: `200`). Request versions and quote versions are separate
positive integers. There are no delete or arbitrary patch endpoints.

Run `python -m pytest tests/test_print_requests.py -q` inside the configured
environment. These are API/MongoDB integration tests, not in-memory mocks.
The shared fixture forces local MongoDB, the isolated test database and console
email; the test database is removed on session completion. They do not start a
runtime server. The ordered Postman flow is part of the main generated
collection and uses the same per-run customer/admin sessions as the existing
account/catalog tests; see [the Postman guide](../postman/README.md).
