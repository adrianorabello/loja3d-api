import asyncio

from starlette.responses import JSONResponse

from app.models.chat import MAX_FILE_BYTES


class ChatBodyLimitMiddleware:
    """Bound chat payloads before multipart parsing/spooling."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/chat/") or scope["method"] not in {"POST", "PUT"}:
            await self.app(scope, receive, send)
            return
        maximum = MAX_FILE_BYTES + 65536 if scope["path"].endswith("/attachments") else 65536
        chunks = []
        size = 0

        async def collect():
            nonlocal size
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return False
                size += len(event.get("body", b""))
                if size > maximum:
                    return False
                chunks.append(event)
                if not event.get("more_body"):
                    return True

        try:
            complete = await asyncio.wait_for(collect(), 30)
        except asyncio.TimeoutError:
            await JSONResponse({"detail": "Chat upload timed out."}, status_code=408)(scope, receive, send)
            return
        if not complete:
            if size > maximum:
                await JSONResponse({"detail": "Chat payload exceeds its size limit."}, status_code=413)(scope, receive, send)
            return
        iterator = iter(chunks)

        async def replay():
            event = next(iterator, None)
            return event if event is not None else await receive()

        await self.app(scope, replay, send)
