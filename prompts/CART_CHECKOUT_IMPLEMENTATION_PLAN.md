# Cart and Two-Step Checkout (Bank Transfer) — Implementation Plan

Planning document only. No application code was changed. Paths are relative to the workspace root
(`clara-rosa-webstore/`). Labels: **[Confirmed]** = stated in the brief or verified in code,
**[Recommendation]** = proposed, **[Open]** = needs a decision.

Directories discovered: `loja3d-app/` (Angular 11.2 + Fuse 12.2, the real app),
`fuse-demo-v12.2.0/` (reference only), `loja-online-3D-responsiva/` (React prototype, visual reference only),
`loja3d-api/` (FastAPI + Motor/MongoDB).

---

## 1. Current-state analysis (with evidence)

### 1.1 Frontend

| Area | Status | Evidence |
|---|---|---|
| Cart state | **Implemented, client-only.** `CartService` keeps a `BehaviorSubject<CartItem[]>` persisted in `localStorage` key `clara_rosa_cart`. No HTTP at all. | `loja3d-app/src/app/core/cart/cart.service.ts`, `cart.utils.ts` (+ specs) |
| Cart model | `CartItem {productId, slug, name, unitPrice, quantity, colorId?}`, `MAX_LINE_QUANTITY = 99`, `CART_SCHEMA_VERSION = 1`. Line identity = `productId + colorId`. `unitPrice` is a JS `number` snapshot taken when added. | `src/app/shared/models/cart.model.ts` |
| Totals | `summarize()` returns `subtotal`, `shipping` (hard-coded `0`), `total`, rounded with `roundMoney`. Shipping is a placeholder, not a business rule. | `core/cart/cart.utils.ts` (~l.150-170) |
| Add to cart | Wired in product card, product details, catalog, kids-store, home catalog; stock clamp via `maxStock`. | `shared/components/product-card/`, `domains/storefront/{product-details,catalog,kids-store,home}/` |
| Cart badge | `cartCount$` bound in the storefront header. | `layout/layouts/storefront/storefront.component.ts` (l.12, 38, 53, 59) |
| Cart UI | `CartPanelComponent` exists (`shared/components/cart-panel/`), declared in `SharedComponentsModule`. It is **not referenced in `storefront.component.html`** (verify before reuse), so there is no reachable cart page today. | grep result |
| Routes | No `cart`/`checkout` routes. `app.routing.ts` l.85 reserves a spot: "phases (cart, checkout, 404) goes above it". Storefront is public (no sign-in redirect while filling a cart, l.47/70). | `src/app/app.routing.ts` |
| Auth | Bearer access token + refresh; `AuthGuard`, `NoAuthGuard`, `RoleGuard`; interceptor does not sign out on `/sign-in`/`/sign-up` 401. Real backend used (`useMockApi: false`), `/api` proxied to `127.0.0.1:8000`. | `core/auth/*`, `proxy.conf.json`, `environments/environment.ts` |
| Product model | `price: number` (EUR, 2dp), `stock`, `madeToOrder`, `colors`, stock state helper `stockStateOf()` (made-to-order wins over zero stock). | `shared/models/product.model.ts`, `core/product/product.utils.ts` |
| Order/checkout | **Missing.** No order model, service, page or mock. | grep "order" over `src/app` |
| i18n / currency | ngx-translate pt-PT + en (`src/assets/i18n/*.json`), EUR. | |
| Fuse reuse candidates | Demo has a Material stepper wizard `fuse-demo-v12.2.0/src/app/modules/admin/ui/forms/wizards/` (only a pattern reference), `fuse-alert`, `fuse-card`. The demo ecommerce app is inventory-only (`modules/admin/apps/ecommerce/inventory`), so there is no cart/checkout to copy. | |

### 1.2 Backend (`loja3d-api`)

| Area | Status | Evidence |
|---|---|---|
| Framework | FastAPI, Pydantic v2, Motor. Routers mounted under `/api/v1`, legacy `/api`, and `/api/clara-rosa` (the prefix the Angular app uses). | `main.py` |
| Products | Implemented. Stored price is **integer cents** (`price_cents`), exposed as float `price` with `currency` (default `EUR`), `stock`, `madeToOrder`, `active`, `colors[]`. | `app/models/product.py`, `app/routers/{products,admin_products}.py` (`price_cents = round(price*100)`) |
| Users/auth | JWT access (30 min) + rotating refresh tokens, `get_current_user`, `require_role`. Roles `ADMIN`/`CUSTOMER`. | `app/core/dependencies.py`, `app/routers/auth.py` |
| MongoDB | Single node via `docker-compose.yml` (no replica set), so **multi-document transactions are unavailable**. Indexes created in `app/database.py:init_indexes`. | `docker-compose.yml`, `app/database.py` |
| Cart / orders / payments | **Missing.** No collections, routers or tests. | grep over `app/` |
| Docs / tests | OpenAPI served by FastAPI; pytest suite (16 tests) with isolated test DB. | `tests/`, `main.py` |
| Prior plans | `prompts/API_CURRENT_STATE_ANALYSIS.md` l.124 and l.248 record the decision "do not persist the cart on the backend in this phase". This plan reverses that deliberately for the checkout step only (see 7.4). | `prompts/` |
| Admin payment confirmation | **No mechanism exists.** Admin area only manages products. | `app/routers/admin_products.py` |

### 1.3 Findings that shape the design

1. The cart already works client-side with a price snapshot, so the server cart can be postponed. **[Recommendation]** keep the cart in `localStorage` and make the **order confirmation endpoint the authoritative step**.
2. Prices are integer cents in Mongo, floats in the API/Angular. Orders must use integer cents end to end.
3. Mixed availability: stock-tracked products and `madeToOrder` products. Both exist in seed data.
4. No shipping, delivery or tax rules exist anywhere. `shipping = 0` in `cart.utils.ts` is a stub.

---

## 2. Scope and exclusions

**In scope (initial):** cart review (step 1), order confirmation and bank-transfer instructions (step 2), pending-payment order, backend-authoritative validation, order retrieval, minimal admin payment confirmation (separate phase).

**Out of scope:** payment gateways, cards, automatic bank reconciliation, receipt uploads, guest checkout, shipping/tax engines, coupons, refunds, e-mail notifications (optional later).

---

## 3. Two-step user flow

1. Customer adds items anywhere in the store (unchanged, `localStorage`).
2. `/cart` (**Step 1 — Review**): items, quantity controls, remove, totals, "Continue shopping", primary button "Confirm order and view bank details".
   - If not signed in: button routes to `/sign-in?redirectURL=/cart`, and the cart survives because it is client-side. After login the customer returns to `/cart` (purchase intent preserved).
3. Click confirm: `POST /orders` with `Idempotency-Key`. Backend revalidates and creates a `PENDING_PAYMENT` order.
4. Navigate to `/checkout/orders/:orderNumber` (**Step 2 — Bank transfer**), then clear the local cart.
5. Refresh on step 2 re-fetches `GET /orders/{orderNumber}`. It never creates another order.

Edge behaviour **[Recommendation]**:

| Case | Behaviour |
|---|---|
| Back from step 2 | Cart is already cleared; the page shows the order summary and a link "Continue shopping". The order cannot be edited. |
| Double click | Button disabled while pending; backend idempotency key makes a second request return the same order. |
| Timeout / lost response | Frontend stores the generated `Idempotency-Key` in `sessionStorage` until success; retrying sends the same key and receives the existing order (HTTP 200 instead of 201). |
| Editing cart after an order | New local cart; the confirmed order is immutable. Previous order stays reachable from "Minha conta > Pedidos" (later) or by URL. |
| Cart "converted" | Frontend clears local cart only after a successful 2xx response. |
| Price changed | Revalidation returns `409 CART_CHANGED` with the corrected lines. Frontend updates the cart prices, shows an alert and requires a new explicit confirmation. |

---

## 4. Fuse / Angular Material components to reuse

- `fuse-alert` for price-changed, unavailable and error banners (already used in auth pages).
- `fuse-card` / existing `bg-card shadow rounded-2xl` utility pattern (as in `customer/profile`).
- Angular Material: `mat-stepper` read-only header pattern from `fuse-demo-v12.2.0/.../forms/wizards/` **or** a simple two-step indicator (recommended: simple indicator, avoids stepper state coupling with routing).
- `mat-icon-button`, `mat-progress-bar`, `MatSnackBar` for "copied" feedback, `Clipboard` from `@angular/cdk/clipboard` (already in CDK).
- Existing `EmptyStateComponent`, `StockBadgeComponent`, `ConfirmDialogComponent` (remove-all confirmation), `LocalizedTextPipe`.
- Do **not** import the demo ecommerce module.

---

## 5. Data model and indexes (MongoDB)

Money is **integer minor units (cents)**, `currency: "EUR"`. Rounding: half-up at line level (`unit_price_cents * quantity` is exact, so no rounding needed). API serializes both `unitPriceCents` and a display-friendly `unitPrice` string is **not** needed; Angular formats via `Intl.NumberFormat`/`CurrencyPipe`.

### 5.1 `orders` (new)

```json
{
  "_id": "ObjectId",
  "order_number": "PT-2026-000123",
  "user_id": "ObjectId",
  "status": "PENDING_PAYMENT",
  "payment": {
    "method": "BANK_TRANSFER",
    "status": "PENDING",
    "reference": "PRT000123",
    "paid_at": null,
    "confirmed_by": null
  },
  "items": [
    {
      "product_id": "ObjectId", "slug": "...", "name": {"pt-PT": "...", "en": "..."},
      "color_id": "optional", "color_name": {"pt-PT": "..."},
      "unit_price_cents": 2490, "quantity": 2, "subtotal_cents": 4980
    }
  ],
  "subtotal_cents": 4980,
  "shipping_cents": 0,
  "total_cents": 4980,
  "currency": "EUR",
  "idempotency_key": "uuid",
  "request_hash": "sha256 of normalized items",
  "bank_snapshot": {"beneficiary": "...", "bank_name": "...", "iban": "...", "bic": "..."},
  "created_at": "...", "updated_at": "..."
}
```

Indexes:
- unique `order_number`
- unique `(user_id, idempotency_key)`
- `(user_id, created_at desc)`
- unique `payment.reference`
- `(status, created_at)` for admin lists

Item snapshots and the bank snapshot are copied at confirmation, so later product or configuration edits never alter history.

### 5.2 `counters` (new)
`{_id: "order_number:2026", seq: n}` updated with `find_one_and_update($inc, upsert, return_document=AFTER)` to generate sequential order numbers atomically without transactions.

### 5.3 Server cart (optional, **not** in the first phases)
Only if cross-device carts become a requirement: `carts {user_id unique, items[{product_id,color_id,quantity}], version, updated_at}`. Item identity = `(product_id, color_id)`. Adding the same line again **increments** the quantity (matches current `CartService`). Out of the initial scope; see Open decisions.

### 5.4 Consistency without transactions
The local Mongo has no replica set. Order creation touches one collection (`orders`) plus the counter and, if stock is tracked, `products.stock`. Strategy:
1. Insert order with the unique `(user_id, idempotency_key)` index. A duplicate-key error means "return the existing order".
2. If stock reservation applies (see 8), decrement with a conditional atomic update `update_one({_id, stock: {$gte: qty}}, {$inc: {stock: -qty}})` per line, and compensate (re-increment) if any line fails, before the order is saved.
3. Production should run a replica set so transactions are available; the code path must work without them.

---

## 6. API contracts

Base prefix: `/api/clara-rosa` (Angular) and `/api/v1` (same routers). All endpoints require a Bearer token, ownership is derived from the token (`user_id`), never from the body. Errors use `{"detail": ...}` (existing convention); business errors use `{"detail": {"code": "...", "message": "...", ...}}`.

### 6.1 `POST /orders` — confirm cart and create order
- Auth: `CUSTOMER` or `ADMIN` (any authenticated user). Header `Idempotency-Key: <uuid>` **required**.
- Body: `{ "items": [{ "productId": "str", "colorId": "str|null", "quantity": 1..99 }], "acknowledgedTotalCents": 4980 }`
  - Prices are never accepted. `acknowledgedTotalCents` is only compared with the server's total to detect staleness.
- Validation: non-empty, ≤ 50 lines, integer quantity 1..99, merge duplicate `(productId, colorId)`, product exists and `active`, color belongs to product, stock rule (see 8).
- Success: `201` with `OrderResponse` (`200` when the idempotency key was already used with an identical request).
- Errors: `400` empty/invalid; `401`; `409 CART_CHANGED` (price or availability differs; body lists corrected lines and new total); `409 IDEMPOTENCY_KEY_REUSED` (same key, different payload); `422` schema; `503 BANK_DETAILS_NOT_CONFIGURED`.
- Bank configuration missing/incomplete: **no order is created**; return `503` with a clear code, and Angular shows "Transfer details are temporarily unavailable" with the cart kept intact.

### 6.2 `GET /orders/{orderNumber}`
- Auth: owner only. Others get `404` (not `403`, to avoid enumeration). `ADMIN` can read any.
- Response `OrderResponse`: `orderNumber`, `status`, `payment {method,status,reference}`, `items[]`, `subtotalCents`, `shippingCents`, `totalCents`, `currency`, `createdAt`, `bankTransfer {beneficiary, bankName?, iban, bic?, amountCents, currency, reference, instructions}` (taken from `bank_snapshot`).

### 6.3 `GET /orders` — list own orders (`?page&pageSize`), newest first. (Nice to have, phase 6.)

### 6.4 Optional validation endpoint (recommended) `POST /cart/validate`
Same body as `POST /orders` without creating anything. Returns validated lines with authoritative prices, availability flags and total so step 1 can show "price changed" before the click. Rate limited.

### 6.5 Admin (separate, minimal) `POST /admin/orders/{orderNumber}/confirm-payment`
- `ADMIN` only. Body `{ "amountCents": 4980, "note": "..." }`. Transitions `PENDING_PAYMENT -> PAID` only if amount matches; records `confirmed_by` and `paid_at`. `409` if already paid/cancelled. Customers can never call this and no customer payload can set `status` or `payment`.
- Also `GET /admin/orders?status=PENDING_PAYMENT` and `POST /admin/orders/{n}/cancel` (releases stock). Flag as a **separate proposal**; not required to deliver steps 1-2.

### 6.6 Cart endpoints (add/update/remove/clear)
Not created in the first release. Cart operations stay client-side (`CartService`) and are revalidated by `POST /cart/validate` and `POST /orders`. If a server cart is later required, follow 5.3 with `GET /cart`, `POST /cart/items` (increment), `PATCH /cart/items/{lineId}`, `DELETE /cart/items/{lineId}`, `DELETE /cart` and optimistic concurrency by `version` (`409`/`412` on mismatch).

OpenAPI: Pydantic response models with `examples`, tag `Orders`, documented error responses, `Idempotency-Key` as a declared header parameter.

---

## 7. Security, ownership, consistency

1. Server recomputes everything from `products` (`price_cents`, `active`, `stock`, `madeToOrder`, `currency`). Request price fields are rejected (`extra="forbid"`).
2. `user_id` always from the JWT. Orders for other users return `404`.
3. `status`, `payment.*` only mutable by the admin endpoint. Customer payloads have no such fields.
4. Idempotency: unique index `(user_id, idempotency_key)` plus `request_hash`; lost response is recovered by retrying with the same key, or by `GET /orders` / the order URL.
5. Rate limit `POST /orders` (reuse `app/core/rate_limit.py`), e.g. 10/min per IP.
6. Concurrency: two parallel confirmations with the same key produce one order (unique index). With different keys they produce two legitimate orders; stock updates are atomic conditional updates.
7. Angular guards are navigation only; authorization is enforced server-side.
8. Guest approach **[Recommendation]**: keep the cart in `localStorage` for guests (already the case) and require sign-in only at confirmation. After login the same browser cart is used, so no merge logic or server guest cart is needed. Not adding guest checkout.
9. Bank details come only from backend settings; never hardcoded in Angular, never logged.

---

## 8. Money, availability, shipping, tax

- Money: integer cents, EUR only (reject other currencies server-side). Frontend continues using `number` for display only; the confirmation request sends cents.
- Availability **[Confirmed from code]**: `madeToOrder = true` is always purchasable (no stock check); otherwise `stock >= quantity` required.
- Stock reservation for unpaid transfers **[Open]**:
  - Option A (recommended for MVP): decrement stock at confirmation for non-made-to-order items, release on admin cancel or auto-expiry (e.g. 72 h, a scheduled task or an admin action).
  - Option B: do not reserve; validate only, and re-check when payment is confirmed (risk of overselling).
- Shipping and taxes: no rules exist. `shipping_cents = 0` is kept as a field with the value 0 **only if the business confirms free shipping/pickup**. VAT inclusion in displayed prices is assumed to be already included (PT consumer prices). Both are **blocking decisions** (section 13).

---

## 9. Frontend integration (Angular 11, NgModules only)

New / changed files:

| File | Purpose |
|---|---|
| `src/app/shared/models/order.model.ts` (new) + export in `shared/models/index.ts` | `Order`, `OrderItem`, `BankTransferInfo`, `CreateOrderRequest`, error code enum |
| `src/app/core/order/order.service.ts` (+spec) (new) | `validateCart()`, `createOrder(items, key)`, `getOrder(number)`, `listOrders()` via `HttpClient` on `api/clara-rosa/orders` |
| `src/app/core/cart/cart.service.ts` | Add `replacePrices(lines)` (apply server prices), keep API; `clear()` after order |
| `src/app/domains/storefront/checkout/` (new lazy module): `cart-review.page`, `bank-transfer.page`, `checkout.module`, `checkout.routing` | Steps 1 and 2 |
| `src/app/app.routing.ts` | Add `cart` (public, storefront layout, so the cart is viewable by guests) and `checkout/orders/:orderNumber` (`AuthGuard`) above the catch-all at l.85; update `app.routing.spec.ts` |
| `layout/layouts/storefront/storefront.component.html` | Cart icon links to `/cart` with `cartCount$` badge |
| `shared/components/cart-panel/` | Reuse the row template (thumbnail, quantity stepper) or retire the panel if unused |
| `src/assets/i18n/{pt-PT,en}.json` | `cart.*`, `checkout.*` keys |
| `src/app/shared/components/copy-button` (small, optional) | Copy to clipboard + snackbar |

State sync **[Recommendation]**: `CartService` stays the single source of truth for lines. Step 1 calls `validateCart()` on load and after each quantity change (debounced, using `switchMap` so older responses are discarded) and merges authoritative prices/availability into a view model. Confirm sends `acknowledgedTotalCents`; a `409 CART_CHANGED` updates the view and forces re-review. The confirm button is disabled while any request is in flight, the cart is invalid, empty, or has unacknowledged price changes. Step 2 reads only from `GET /orders/{n}` (never from the cart).

Accessibility/responsiveness: semantic list/table, labeled quantity buttons (`aria-label`), `aria-live="polite"` region for updates, focus management on error alerts, stacked layout on mobile, sticky summary on desktop.

---

## 10. Implementation phases (ordered by dependency)

### Phase 0 — Business decisions (blocking, see section 13)
Bank details, shipping/tax rule, stock-reservation policy. **Done when:** answers are recorded here.

### Phase 1 — Backend foundation
- Tasks: config (`BANK_*` settings), `orders` + `counters` collections and indexes in `app/database.py`, money helpers (cents), order number/reference generators.
- Files: `app/config.py`, `app/database.py`, `app/core/money.py`, `app/models/order.py`, `.env.example`.
- Accept: app starts, indexes exist, settings validation reports missing bank config.

### Phase 2 — Order creation and retrieval API
- Tasks: `POST /orders` (revalidation, idempotency, stock rule, snapshots, bank snapshot), `GET /orders/{n}`, `GET /orders`, optional `POST /cart/validate`; register routers in `main.py` for `/api/v1` and `/api/clara-rosa`.
- Files: `app/routers/orders.py`, `app/services/orders.py`, `main.py`.
- Accept: contract tests (section 11) pass; OpenAPI shows examples and error responses.
- Depends on: Phase 1.

### Phase 3 — Frontend data layer
- Tasks: models, `OrderService`, `CartService.replacePrices`, i18n keys.
- Accept: unit specs for service and cart utilities pass.
- Depends on: Phase 2 contracts (can start in parallel against the OpenAPI schema).

### Phase 4 — Step 1 page and routing
- Tasks: `/cart` page with all states (empty, loading, updating, error, removed/inactive, unavailable, price changed), header link, route + routing spec.
- Accept: manual and spec scenarios in section 11; keyboard-operable.
- Depends on: Phase 3.

### Phase 5 — Step 2 page
- Tasks: bank-transfer page, copy actions, refresh-safe loading, missing-bank-config error handling, clear cart after success.
- Accept: refresh does not create orders; amounts and reference match the API.
- Depends on: Phase 4.

### Phase 6 — Customer order list (optional) and admin payment confirmation (separate proposal)
- Tasks: `/account/orders`; admin endpoints in 6.5 and a minimal admin list.
- Accept: only admin can mark as paid; customer attempts return `403/404`.

### Phase 7 — Hardening
- Tasks: rate limits, stock expiry job (if Option A), responsive and a11y pass, docs in `loja3d-api/README.md`.

---

## 11. Tests and acceptance criteria

Backend (pytest, `tests/test_orders.py`):
- Valid order, subtotals and total in cents; repeated lines merged.
- Client-tampered price/total ignored or rejected; `acknowledgedTotalCents` mismatch returns `409 CART_CHANGED`.
- Empty cart, quantity 0/negative/non-integer/over 99 rejected.
- Inactive, deleted, insufficient-stock products rejected; made-to-order accepted at zero stock.
- Another user's order returns `404`; no token returns `401`; customer cannot call admin confirm.
- Duplicate request with the same key returns the same order; same key with different body returns `409`; concurrent parallel confirmations create exactly one order.
- Missing/incomplete bank config returns `503` and creates no order.
- New order is `PENDING_PAYMENT`; payload cannot set `status`/`payment`.
- Snapshot survives product price change and deletion.
- Reference and order number unique and well formed.

Frontend (Karma): `OrderService` calls, cart quantity rules, review component states, double-click prevention, out-of-order response discard, step 2 refresh, routing spec.

E2E/manual (desktop and mobile widths): add, add again (increments), change quantity, remove, price change, login redirect keeps cart, confirm, view instructions, copy fields, refresh step 2.

---

## 12. Required configuration

`loja3d-api/.env` (and `.env.example`, no real values):

```
BANK_BENEFICIARY=<beneficiary name>
BANK_NAME=<optional bank name>
BANK_IBAN=<PT50 placeholder, validate IBAN checksum at startup>
BANK_BIC=<optional>
BANK_PAYMENT_INSTRUCTIONS_PT=<text>
BANK_PAYMENT_INSTRUCTIONS_EN=<text>
ORDER_STOCK_RESERVATION_HOURS=72
```

"Configured" means beneficiary and a valid IBAN are present. Otherwise order creation fails with `503`.

---

## 13. Open decisions and genuine blockers

**Blockers**
1. Real bank details (beneficiary, IBAN, BIC if needed) and the instruction text.
2. Shipping/delivery and VAT policy: is the total the sum of product prices only (free shipping or pickup)? If shipping is charged, the rule must be defined before step 2 can show the amount to transfer.
3. Stock policy for unpaid orders (Option A reserve vs Option B no reserve) and expiry time.

**Non-blocking recommendations to confirm**
4. Keep the cart client-side now; server cart only if cross-device persistence is needed.
5. Order number format (`PT-YYYY-NNNNNN`) and payment reference format.
6. Who confirms payments and how (admin screen in Phase 6, or manual DB operation initially).
7. Whether to enable a MongoDB replica set in `docker-compose.yml` for production-like transactions.
8. Product variations: only `color` exists today; line identity stays `(productId, colorId)`.
