# Support chat: operation and contracts

The chat is opt-in (`CHAT_ENABLED=false` by default). It is not a Fuse mock.
Customers have one private support conversation; all active ADMIN users share the
inbox. Existing print-request messages and notifications are unchanged.

## Isolated local environment

### Current store on port 4201

The local store has been migrated with explicit approval and a write-locked
pre-migration archive, retaining `clara_rosa_mongodb_data` and existing accounts.
`docker-compose.yml` runs MongoDB as `store-rs`; its idempotent `mongodb-init`
service initializes fresh local volumes. This is a local single-node setup,
not a production high-availability deployment.

The current local `.env` enables chat and uses
`mongodb://127.0.0.1:27017/?replicaSet=store-rs&directConnection=true`,
Redis DB **1** (`redis://127.0.0.1:6380/1`) and WS origins for localhost/127.0.0.1
on port 4201. DB 1 separates store tickets/events from isolated chat DB 0.
Redis and ClamAV are supplied by the separate chat Compose services:

```sh
docker compose up -d mongodb mongodb-init
docker compose -p clara-rosa-chat -f docker-compose.chat.yml up -d redis scanner
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --ws-max-size 1024 --ws-max-queue 8 --no-access-log
```

In another API terminal run `.venv/bin/python -m app.workers.chat`; in the Angular
directory run `npm start`. Open **http://localhost:4201** and sign in with an
existing account. The right-hand drawer opens on the first eligible page.
The normal proxy preserves Origin for WS ticket/handshake validation.

### Separate test store on port 4203

From the API directory:

```sh
docker compose -p clara-rosa-chat -f docker-compose.chat.yml up -d
cp .env.chat.example .env.chat
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.chat_cli api
```

In another terminal, from the API directory:

```sh
.venv/bin/python -m app.chat_cli worker
```

From the Angular directory:

```sh
npm run start:chat
```

Open **http://localhost:4203**. The API is on port 8001, MongoDB on 27018,
Redis on 6380 and ClamAV on 3311. Only loopback ports are published.
These are separate containers, volume and database (`clara_rosa_chat_dev`):
the store database on 27017 is not converted or copied. Create test accounts here;
use the API's existing bootstrap-admin configuration for an administrator.
Never reuse the default development credentials in production.

The first scanner start downloads its private signature database and may take
several minutes. Check `docker compose -p clara-rosa-chat -f docker-compose.chat.yml
logs scanner`. The scanner image currently requires amd64 emulation on Apple
Silicon. A scanner failure keeps uploads quarantined, with worker errors logged;
it never marks an unscanned file ready.

Stop these services without deleting their data:

```sh
docker compose -p clara-rosa-chat -f docker-compose.chat.yml stop
```

Do not use `down -v` on an environment whose data must be retained. The API/worker
CLI requires an explicit env file and never silently falls back to the store DB.
`--env-file .env.chat.example` is also supported for disposable local checks.

## REST

All endpoints are under `/api/v1/chat`, require the existing Bearer token and
return 503 when disabled. Responses containing binaries are never public.

| Method and suffix | Contract |
|---|---|
| POST `/conversations` | CUSTOMER only; idempotently creates/returns own conversation |
| GET `/conversations?cursor=&limit=50&q=` | Authorized summaries `{items,hasMore,nextCursor}`; at most 100; admin name search |
| GET `/conversations/{id}` | Authorized summary, `lastSeq`, current user's `lastReadSeq` and received-message unread count |
| GET `/conversations/{id}/messages?beforeSeq=&afterSeq=&limit=50` | Ascending messages in each page; before/after mutually exclusive |
| POST `/conversations/{id}/messages` | `{clientMessageId: UUID,text,attachmentIds:[]}`; server assigns sender, timestamp, sequence |
| PUT `/conversations/{id}/read` | `{lastReadSeq}`; monotonic and not beyond persisted history |
| POST `/conversations/{id}/attachments` | Multipart `file`; returns quarantined metadata |
| GET `/conversations/{id}/attachments/{aid}` | Status; unbound files visible only to their uploader |
| DELETE `/conversations/{id}/attachments/{aid}` | Cancels own unbound file; worker removes bytes |
| GET `/conversations/{id}/attachments/{aid}/content` | Authenticated download; ready/attached only; private/no-store/nosniff |
| POST `/ws-ticket` | Origin-checked single-use 30-second ticket; no-store |

Messages accept up to **5,000 characters**, or attachments without text.
At most **3 files of 10 MiB** each; JPEG/PNG, PDF, STL and a deliberately restricted
3MF subset. No generic ZIP, scripts, HTML, SVG, encrypted/active PDFs or 3D viewer.
An account may have at most 6 pending files, 30 upload attempts/day and 60 message
attempts/minute. These conservative operational quotas are explicit in the API;
adjust them only with capacity testing. Rate-limit failures have `Retry-After`.

Images are decoded, stripped of metadata and normalized to JPEG up to 2048 px;
the filename changes to `.jpg`. Original alpha is not retained. Input images have
at most 16 million pixels and one frame. PDF parsing rejects encryption, forms,
open actions and named/embedded resources; limit 500 pages. STL limit 200,000
triangles. 3MF ZIP entry count, paths, expansion and XML entities are bounded;
only core model/relationship/content-type entries are accepted in this version,
not arbitrary packaged textures or extensions.

Every file is scanned privately with ClamAV and parsed in a disposable subprocess
(10-second CPU, 20-second wall budget; 768 MiB address/data limits on Linux).
macOS development enforces CPU/wall time; production workers **must use Linux**
for memory isolation. No uploaded document is sent to a public scanning service.
App middleware limits raw JSON/multipart payloads before multipart parsing.

Errors: 401 identity; 403 role/origin; 404 inaccessible conversation/file;
409 divergent retry or attachment not ready/owned; 413 size; 415 type;
422 content; 429 quota; 503 infrastructure. Drafts are preserved on failure.

## WebSocket and consistency

Connect to `/api/v1/chat/ws` (WSS in production), then send:

```json
{"type":"authenticate","ticket":"ticket-from-rest"}
```

Authenticate within 5 seconds. JWTs/tickets never appear in URLs. WS Origin must
match `CHAT_WS_ORIGINS`; CORS is not WS authorization. The server verifies active
identity/role/expiration repeatedly, limits frame sizes/rate, and allows at most
5 live sockets per account via expiring Redis leases.

Events use `{v:1,type,eventId,conversationId,seq,data}`. `ready` and heartbeat
`ping` omit conversation data. Reply to ping with exactly `{"type":"pong"}`.
Message/read events invalidate authorized state; fetch authoritative data over REST.
The Angular root owns one socket per tab and retries with backoff/jitter. It syncs
on reconnect/focus and reconciles HTTP/WS ordering by ID/sequence. The page and
Fuse drawer share drafts/history; minimized drawers do not mark messages read.

Message sequence, summary, attached-file binding and outbox insert commit in one
MongoDB replica-set transaction. Same sender/clientMessageId/payload returns the
original message; differing content returns 409. Redis is not durable storage.
The worker publishes the outbox at least once; duplicate delivery is possible and
clients deduplicate. A Redis restart cannot undo committed history. GridFS uploads
precede message transactions and are private while pending.

## Retention and operations

The worker removes cancelled uploads and unbound files older than **24 hours**,
including GridFS files/chunks and interrupted-write orphans. Published outbox
records are removed after 24 hours; pending outbox is retained. Sent history and
attachments have no automatic TTL, per the initial approved development policy.
Backups/restores must include collections **and** GridFS files/chunks.

For production: use authenticated/TLS private MongoDB replica set and Redis,
separate persistent API and worker processes, current scanner signatures, WSS
reverse-proxy upgrades, bounded request/concurrency/time limits, and explicit
HTTP/WS origin allowlists. Start Uvicorn with `--ws-max-size 1024 --ws-max-queue 8`
and an appropriate `--limit-concurrency`. Do not expose the development Compose
services publicly. Fail startup if replica-set/index/Redis requirements fail.
Disable access logging (`--no-access-log`) or redact search/cursor query strings
at both API and reverse proxy; never log Authorization, WS frames or document bytes.

Enable the Angular build separately with `CHAT_ENABLED=true` using the existing
`build:vercel`/environment generator. `API_URL` also determines the native WS origin
(`https` becomes `wss`); the HTTP interceptor cannot configure native sockets.
Both backend and frontend flags must be enabled. Local `npm start` enables chat
against the current store; production defaults keep it hidden. Disabled deep links display unavailable.

Publication remains gated on an approved privacy/retention/account-erasure policy,
target-host WSS/upload smoke tests, load/latency measurement, and backup/restore
rehearsal. This local implementation does not claim production SLA certification
or provide an operational metrics dashboard.

## Tests

Start the isolated Compose stack first:

```sh
.venv/bin/python -m pytest tests/test_chat.py -q
```

Tests use unique `clara_rosa_chat_test_*` databases on 27018, dedicated Redis DB 15,
actual ClamAV, and two disposable Uvicorn processes for cross-process WS delivery.
They delete only their own databases. The pre-existing test harness also requires
the normal local test MongoDB on 27017. Never point Redis DB 15 at a shared service.
