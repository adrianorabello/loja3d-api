"""Disposable, resource-bounded parser for untrusted chat files."""
import json
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_DATA, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    from fastapi import HTTPException
    from app.models.chat import MAX_FILE_BYTES
    from app.services.chat_attachments import validate_file
    try:
        clean, mime = validate_file(sys.stdin.buffer.read(MAX_FILE_BYTES + 1), sys.argv[1], sys.argv[2])
    except (HTTPException, MemoryError, RecursionError, OverflowError, KeyError, TypeError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Document exceeds validation limits."
        sys.stdout.write(json.dumps({"error": detail}) + "\n")
        return 2
    sys.stdout.buffer.write(json.dumps({"mime": mime}).encode() + b"\n" + clean)
    return 0


if __name__ == "__main__":
    sys.exit(main())
