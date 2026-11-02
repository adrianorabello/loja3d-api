import asyncio
import hashlib
import math
import json
import re
import socket
import struct
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from PIL import ImageOps
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import settings
from app.models.chat import MAX_FILE_BYTES
from app.services.chat import identifier, now
from app.services.images import validated_image

TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".pdf": "application/pdf", ".stl": "model/stl", ".3mf": "model/3mf",
}


def safe_filename(name):
    name = re.sub(r"[\x00-\x1f\x7f/\\]", "_", name or "file")
    return name[:160]


def scan(data):
    # ClamAV INSTREAM never sends user paths or files to an external provider.
    with socket.create_connection((settings.CHAT_SCANNER_HOST, settings.CHAT_SCANNER_PORT), 5) as conn:
        conn.settimeout(45)
        conn.sendall(b"zINSTREAM\0")
        for offset in range(0, len(data), 65536):
            chunk = data[offset:offset + 65536]
            conn.sendall(struct.pack("!I", len(chunk)) + chunk)
        conn.sendall(b"\0\0\0\0")
        reply = bytearray()
        while b"\0" not in reply and len(reply) < 4096:
            part = conn.recv(4096)
            if not part:
                break
            reply.extend(part)
    if b" FOUND" in reply:
        raise HTTPException(422, "File rejected by malware scanner.")
    if bytes(reply).rstrip(b"\0") != b"stream: OK":
        raise OSError("Scanner did not confirm a clean file.")


def validate_file(data, name, declared_type):
    ext = PurePosixPath(name.lower()).suffix
    mime = TYPES.get(ext)
    if not mime:
        raise HTTPException(415, "Use JPEG, PNG, PDF, STL or 3MF.")
    allowed_declared = {mime, "application/octet-stream", ""}
    if ext == ".stl":
        allowed_declared.update({"application/sla", "application/vnd.ms-pki.stl"})
    if ext == ".3mf":
        allowed_declared.add("application/vnd.ms-package.3dmanufacturing-3dmodel+xml")
    if declared_type not in allowed_declared:
        raise HTTPException(415, "File extension and MIME type disagree.")
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "File must be between 1 byte and 10 MiB.")
    try:
        if mime.startswith("image/"):
            with validated_image(data, mime, MAX_FILE_BYTES) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                normalized.thumbnail((2048, 2048))
                output = BytesIO()
                normalized.save(output, "JPEG", quality=90)
                normalized.close()
                data = output.getvalue()
            return data, "image/jpeg"
        if ext == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise ValueError("Invalid PDF signature.")
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
                raise ValueError("PDF must be unencrypted and have 1–500 pages.")
            root = reader.trailer["/Root"]
            if any(key in root for key in ("/OpenAction", "/AA", "/AcroForm")) or "/Names" in root:
                raise ValueError("Active or embedded PDF content is not allowed.")
        elif ext == ".stl":
            binary_count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else 0
            if binary_count and len(data) == 84 + binary_count * 50:
                if binary_count > 200000:
                    raise ValueError("Too many STL triangles.")
                for values in struct.iter_unpack("<12fH", data[84:]):
                    if not all(math.isfinite(value) for value in values[:12]):
                        raise ValueError("Invalid STL geometry.")
            else:
                text = data.decode("ascii")
                if not re.fullmatch(
                    r"\s*solid[^\r\n]*\s+(?:facet\s+normal\s+[-+\deE.\s]+"
                    r"outer\s+loop\s+(?:vertex\s+[-+\deE.\s]+){3}endloop\s+endfacet\s+)+"
                    r"endsolid[^\r\n]*\s*", text
                ):
                    raise ValueError("Invalid STL structure.")
                if text.count("endfacet") > 200000:
                    raise ValueError("Too many STL triangles.")
        elif ext == ".3mf":
            with zipfile.ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                if not 1 <= len(entries) <= 200:
                    raise ValueError("Invalid 3MF entry count.")
                total = 0
                model_found = False
                for entry in entries:
                    path = PurePosixPath(entry.filename)
                    if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or entry.flag_bits & 1:
                        raise ValueError("Unsafe 3MF path.")
                    if entry.is_dir():
                        continue
                    total += entry.file_size
                    if total > 30 * 1024 * 1024 or entry.file_size > 100 * max(1, entry.compress_size):
                        raise ValueError("3MF expansion limit exceeded.")
                    if not (entry.filename == "[Content_Types].xml" or
                            (path.suffix in {".model", ".rels"} and path.parts[0] in {"3D", "_rels"})):
                        raise ValueError("Unsupported 3MF content.")
                    document = fromstring(archive.read(entry))
                    if path.suffix == ".model":
                        model_found = document.tag.endswith("}model")
                    for element in document.iter():
                        if element.attrib.get("TargetMode") == "External":
                            raise ValueError("External 3MF resources are not allowed.")
                if not model_found:
                    raise ValueError("3MF model missing.")
    except (ValueError, UnicodeError, zipfile.BadZipFile, PdfReadError, DefusedXmlException, ParseError) as exc:
        raise HTTPException(422, "Invalid or unsupported document structure.") from exc
    return data, mime


async def store_upload(db, cid, uid, upload):
    # Redis serializes uploads per user; this quota therefore cannot be bypassed by parallel requests.
    pending = await db.chat_attachments.count_documents({
        "owner_id": uid, "status": {"$ne": "attached"}
    })
    if pending >= 6:
        raise HTTPException(429, "Remove pending attachments before uploading more.", headers={"Retry-After": "60"})
    data = await upload.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "File must be between 1 byte and 10 MiB.")
    name = safe_filename(upload.filename)
    if PurePosixPath(name.lower()).suffix not in TYPES:
        raise HTTPException(415, "Use JPEG, PNG, PDF, STL or 3MF.")
    aid = identifier()
    grid_id = identifier()
    doc = {
        "_id": aid, "conversation_id": cid, "owner_id": uid, "grid_id": grid_id,
        "name": name, "content_type": upload.content_type or "", "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(), "status": "uploading", "created_at": now(),
    }
    await db.chat_attachments.insert_one(doc)
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="chat_files")
    await bucket.upload_from_stream_with_id(grid_id, aid, data)
    await db.chat_attachments.update_one({"_id": aid}, {"$set": {"status": "quarantined"}})
    doc["status"] = "quarantined"
    return doc


async def process_attachment(db, doc):
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="chat_files")
    stream = await bucket.open_download_stream(doc["grid_id"])
    data = await stream.read()
    try:
        await asyncio.to_thread(scan, data)
        clean, mime = await asyncio.to_thread(validate_in_process, data, doc["name"], doc["content_type"])
    except HTTPException as exc:
        await db.chat_attachments.update_one({"_id": doc["_id"], "status": "quarantined"}, {
            "$set": {"status": "rejected", "error": exc.detail}
        })
        return
    # A new ID makes a crash during normalization recoverable; cleanup removes the orphan.
    clean_id = identifier()
    await bucket.upload_from_stream_with_id(clean_id, doc["_id"], clean)
    name = str(PurePosixPath(doc["name"]).with_suffix(".jpg")) if mime == "image/jpeg" else doc["name"]
    result = await db.chat_attachments.update_one({"_id": doc["_id"], "status": "quarantined"}, {
        "$set": {"status": "ready", "grid_id": clean_id, "content_type": mime, "size": len(clean), "name": name}
    })
    if result.modified_count:
        await bucket.delete(doc["grid_id"])


def validate_in_process(data, name, mime):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.services.chat_file_validator", name, mime],
            input=data, capture_output=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(422, "File validation exceeded its time budget.") from exc
    header, separator, clean = result.stdout.partition(b"\n")
    if not separator or result.returncode not in {0, 2}:
        raise HTTPException(422, "File could not be validated within resource limits.")
    info = json.loads(header)
    if result.returncode == 2:
        raise HTTPException(422, info["error"])
    return clean, info["mime"]
