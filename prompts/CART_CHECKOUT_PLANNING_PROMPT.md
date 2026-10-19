Act as a senior software architect and full-stack engineer specializing in Angular, Fuse, Python, REST APIs, and MongoDB.

Investigate the existing workspace and create an implementation plan for a shopping cart with a two-step checkout and payment by bank transfer.

IMPORTANT: This is a planning task only. Do not implement features, install dependencies, or modify application code.

## 1. Save this prompt first

Identify the actual backend directory and save this entire prompt, without summarizing it, to:

loja3d-api/prompts/CART_CHECKOUT_PLANNING_PROMPT.md

Create the prompts directory if necessary.

Save the resulting implementation plan separately to:

loja3d-api/prompts/CART_CHECKOUT_IMPLEMENTATION_PLAN.md

If either file already exists, read it first and preserve relevant previous decisions. Do not overwrite unrelated content.

Only these planning documents may be created or updated during this task.

## 2. Workspace context

The workspace contains these projects:

- Fuse demo: the complete Fuse template, including reference components, layouts, and examples.
- Fuse starter: the Angular frontend of the online store.
- Loja-online-3d: visual ideas and design references for the store.
- loja3d-api: the Python backend, using or intended to use MongoDB.

Discover the actual directory names before proceeding.

Use Fuse starter as the source of truth for the current application. Use Fuse demo to identify reusable components and patterns. Treat Loja-online-3d as a visual reference rather than an implemented requirement.

Preserve existing functionality and reuse the application's established conventions.

## 3. Feature objective

Plan a shopping cart that allows customers to:

1. Add products.
2. View cart items.
3. Change quantities.
4. Remove items.
5. Review unit prices, item subtotals, and the overall total.
6. Confirm the order and view bank transfer instructions.

The checkout must have two steps:

- Step 1: Review cart items and totals.
- Step 2: View the confirmed order and bank transfer details.

Displaying bank details does not mean payment has been received. The order must remain pending payment until an authorized confirmation process updates it.

Payment gateways, card payments, automatic bank reconciliation, and payment receipt uploads are outside the initial scope.

## 4. Required investigation

### Frontend

Inspect:

- Product catalog and product details.
- Existing “Add to cart” actions.
- Existing cart components, panels, pages, services, and state.
- Product interfaces and price representations.
- HTTP services, mocks, and interceptors.
- Authentication, current-user handling, and route guards.
- Existing routing and layout conventions.
- Fuse components suitable for item lists, quantity controls, checkout steps, alerts, and order summaries.
- Responsive behavior, accessibility, translations, and currency formatting.

### Backend

Inspect:

- Python framework, dependencies, and project structure.
- Existing product and user resources.
- Authentication and authorization.
- MongoDB configuration and persistence patterns.
- Price and currency conventions.
- Existing order or cart functionality.
- OpenAPI/Swagger documentation.
- Error handling and tests.
- Previous planning documents relevant to this feature.

Distinguish implemented features, partial implementations, mocks, and missing functionality. Support findings with actual file paths.

Do not assume that a feature works simply because a UI component exists.

## 5. Step 1 — Cart review

For each item, display:

- Product photo, with a fallback if unavailable.
- Product name.
- Selected variation or options, if supported.
- Unit price.
- Quantity.
- Item subtotal: unit price multiplied by quantity.
- Remove action.

Allow customers to increase and decrease quantities according to product rules. Quantities must be positive integers. Removal must be an explicit action.

Display:

- Total number of units.
- Product subtotal.
- Additional charges only when supported by defined business rules.
- Final payable total.
- “Continue shopping” action.
- An explicit confirmation action such as “Confirm order and view bank details”.

Plan these states:

- Empty cart.
- Initial loading.
- Quantity update in progress.
- Failed request.
- Removed or inactive product.
- Unavailable product or invalid quantity.
- Price changed since the product was added.

Prevent confirmation when the cart is empty or contains invalid items.

When prices change, show the updated amounts and require the customer to review them before confirming.

The interface must work on mobile and desktop, with accessible controls and clear feedback.

## 6. Step 2 — Bank transfer instructions

Display:

- Order number.
- Beneficiary name.
- Bank name, if configured.
- IBAN or the appropriate account details for the configured country.
- BIC/SWIFT only when required.
- Exact amount and currency to transfer.
- Payment reference or transfer description.
- Payment instructions.
- “Pending payment” status.
- Order items and total.
- Copy actions for relevant fields.

Bank details must come from backend-controlled configuration. Do not hardcode them in Angular components.

Do not invent real banking information. Use clearly labeled placeholders only in documentation and examples.

Define what happens when banking configuration is missing or incomplete. Do not show unusable instructions or silently create an order that cannot be paid.

### Order creation flow

Plan this sequence:

1. The customer reviews the cart.
2. The customer explicitly confirms the order.
3. The backend revalidates products, quantities, availability, and prices.
4. The backend calculates the authoritative total.
5. The backend creates an order pending payment.
6. The frontend displays the order and transfer instructions.

Clearly distinguish the editable cart from the confirmed order.

Define behavior for:

- Returning to the previous step.
- Refreshing the page.
- Double-clicking confirmation.
- Retrying after a network timeout.
- Editing the cart after an order exists.
- Clearing or marking the cart as converted.

Do not silently modify a confirmed order's financial values.

Do not allow customers to mark their own orders as paid.

## 7. Business rules and security

The backend must be authoritative for:

- Product prices.
- Availability.
- Valid quantities.
- Item subtotals.
- Order total.
- Currency.
- Cart and order ownership.
- Payment status.

The frontend should submit product identifiers, selected options where applicable, and quantities. Never trust client-submitted prices or totals.

Plan:

- Ownership checks for every cart and order operation.
- Reuse of existing authentication.
- Protection against changes to user identity, prices, or payment status through request payloads.
- Server-side validation.
- Idempotent order confirmation.
- Concurrent cart updates and out-of-order responses.
- Safe recovery when order creation succeeds but the response is lost.

Inspect existing guest support and recommend an explicit approach:

- For authenticated carts, preserve purchase intent through login.
- If guest carts are already supported or necessary, explain secure identification, persistence, and merging after login.

Do not add a full guest checkout system without a clear justification.

## 8. Money, availability, and delivery

### Monetary values

Reuse an existing safe monetary representation. Otherwise, recommend integer minor units or an appropriate decimal representation.

Define currency, rounding rules, API serialization, and display formatting.

Avoid binary floating-point calculations for authoritative monetary totals.

### Availability

Determine whether products use stock quantities or are made to order.

Do not invent stock rules for products printed on demand.

If inventory exists, define validation, reservation, expiration, and release behavior for unpaid bank-transfer orders.

### Shipping and taxes

Check existing delivery, pickup, shipping, and tax rules.

Do not assume free shipping or invent tax calculations.

If unresolved charges prevent determining the final amount to transfer, identify them as blocking business decisions. Bank instructions must show the actual payable total.

## 9. MongoDB data model

Propose models consistent with the existing backend.

### Cart

Consider:

- Identifier.
- Owner or secure guest identity, if applicable.
- Product and variation identifiers.
- Quantities.
- Cart status.
- Creation and update timestamps.
- Version or concurrency mechanism where necessary.

### Order

Consider:

- Internal identifier and public order number.
- Customer.
- Immutable item snapshots at confirmation.
- Product identifiers and names.
- Confirmed unit prices.
- Quantities and subtotals.
- Final total and currency.
- Payment method.
- Order and payment statuses.
- Bank-transfer reference.
- Creation and update timestamps.

Order snapshots must preserve financial history when products are edited or deleted later.

Define indexes, uniqueness constraints, and a consistency strategy for converting a cart into an order without duplication or data loss.

Check the actual MongoDB deployment before relying on multi-document transactions.

## 10. API resources

Propose endpoints compatible with existing API conventions for:

- Retrieving the current cart.
- Adding a product.
- Updating an item quantity.
- Removing an item.
- Clearing the cart.
- Confirming the cart and creating an order.
- Retrieving an order and its bank-transfer instructions.

For every endpoint, document:

- HTTP method and path.
- Authentication and authorization.
- Request and response schemas.
- Validation rules.
- HTTP status codes.
- Error responses.
- Idempotency behavior where applicable.

Define whether adding the same product again increments or replaces the quantity, including how variations affect item identity.

Plan OpenAPI/Swagger documentation with examples.

Identify manual payment confirmation as an operational dependency. Check whether an administrative mechanism already exists. If missing, describe a minimal separate proposal without silently expanding the implementation scope.

## 11. Angular and Fuse integration

Identify the exact files to create or modify for:

- Cart, item, and order models.
- API services.
- Shared cart state.
- Cart icon quantity badge.
- Product “Add to cart” actions.
- Cart review page or panel.
- Bank-transfer step.
- Routes and guards.
- Loading and error feedback.

Reference actual reusable components in Fuse demo.

Preserve the store's visual identity. Avoid copying entire demo pages and unnecessary dependencies.

Explain how frontend state stays synchronized with backend responses and how repeated actions and stale totals are prevented.

## 12. Tests and acceptance criteria

Include meaningful scenarios covering:

- Adding a product and adding it again.
- Quantity changes and removal.
- Invalid quantities.
- Empty cart.
- Correct subtotals and total.
- Unavailable products.
- Changed prices.
- Client-side price tampering.
- Access to another customer's cart or order.
- Duplicate and concurrent confirmation requests.
- Network failure during order creation.
- Refreshing the second step without creating another order.
- Correct bank information and payment reference.
- Missing banking configuration.
- Orders remaining pending payment.
- Historical snapshots surviving product changes.
- Responsive end-to-end behavior.

## 13. Implementation plan structure

Write CART_CHECKOUT_IMPLEMENTATION_PLAN.md in English with:

1. Current-state analysis and file evidence.
2. Scope and exclusions.
3. Two-step user flow.
4. Fuse components to reuse.
5. Data model and indexes.
6. API contracts.
7. Security, ownership, and consistency rules.
8. Frontend integration.
9. Implementation phases ordered by dependency.
10. Files to create or modify in each phase.
11. Tests and acceptance criteria.
12. Required configuration.
13. Open decisions and genuine blockers.

Each phase must contain concrete tasks, dependencies, and verifiable acceptance criteria.

Clearly distinguish confirmed requirements, recommendations, and unresolved questions.

Make the plan detailed enough for another developer or agent to implement without repeating the entire investigation.

## 14. Final response

After saving both documents:

- Report their exact paths.
- Summarize what already exists and what is missing.
- Present the recommended implementation sequence.
- Highlight only decisions that genuinely block implementation.

Stop after planning. Do not implement the feature.