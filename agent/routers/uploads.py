"""File upload endpoint for chat attachments."""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile, HTTPException

from agent.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["uploads"])

# Allowed MIME types
ALLOWED_TEXT = {"text/plain", "text/markdown", "text/csv", "application/pdf"}
ALLOWED_IMAGE = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_MIMES = ALLOWED_TEXT | ALLOWED_IMAGE
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_TEXT_CHARS = 32_000


def _uploads_root(request: Request) -> Path:
    """Get or create the uploads directory."""
    cfg = request.app.state.settings
    root = cfg.db_path.parent / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _extract_text(file_path: Path, mime: str) -> str:
    """Extract text content from a text-type file."""
    if mime == "application/pdf":
        import pdfplumber
        text_parts = []

        def _read_pdf():
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            return "\n\n".join(text_parts)

        text = await asyncio.to_thread(_read_pdf)
    else:
        # txt / md / csv
        text = await asyncio.to_thread(file_path.read_text, "utf-8")

    return text[:MAX_TEXT_CHARS]


def _image_to_data_uri(file_path: Path, mime: str) -> str:
    """Read an image file and return base64 data URI."""
    raw = file_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


@router.post("/uploads")
async def upload_files(
    request: Request,
    session_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload files for a chat session. Returns attachment metadata."""
    user = await get_current_user(request)
    uploads_root = _uploads_root(request)
    session_dir = uploads_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for f in files:
        # Validate MIME
        mime = f.content_type or "application/octet-stream"
        if mime not in ALLOWED_MIMES:
            raise HTTPException(400, f"不支持的文件类型: {mime}")

        # Read content with size check
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, f"文件过大: {f.filename} ({len(content)} bytes > {MAX_FILE_SIZE})")

        # Save with UUID filename
        ext = Path(f.filename or "file").suffix or ".bin"
        file_id = str(uuid.uuid4())[:8]
        safe_name = f"{file_id}{ext}"
        file_path = session_dir / safe_name

        # Security: ensure path stays within uploads
        if not file_path.resolve().is_relative_to(uploads_root.resolve()):
            raise HTTPException(400, "非法文件路径")

        await asyncio.to_thread(file_path.write_bytes, content)

        # Determine kind and process
        kind = "text" if mime in ALLOWED_TEXT else "image"
        extracted_text = ""
        data_uri = ""

        if kind == "text":
            extracted_text = await _extract_text(file_path, mime)
        else:
            data_uri = await asyncio.to_thread(_image_to_data_uri, file_path, mime)

        results.append({
            "id": file_id,
            "filename": f.filename or safe_name,
            "mime": mime,
            "size": len(content),
            "kind": kind,
            "extracted_text": extracted_text if kind == "text" else "",
            "data_uri": data_uri if kind == "image" else "",
            "path": str(file_path.relative_to(uploads_root)),
        })

    # Save index for this upload batch
    index_path = session_dir / "index.json"
    existing: list = []
    if index_path.exists():
        existing = json.loads(index_path.read_text("utf-8"))
    existing.extend(results)
    index_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    return results


@router.get("/uploads/{upload_id}")
async def get_upload(upload_id: str, request: Request):
    """Retrieve an uploaded file by ID (returns metadata)."""
    user = await get_current_user(request)
    uploads_root = _uploads_root(request)

    # Search across all session dirs for this upload_id
    for index_file in uploads_root.rglob("index.json"):
        items = json.loads(index_file.read_text("utf-8"))
        for item in items:
            if item["id"] == upload_id:
                return item

    raise HTTPException(404, "附件未找到")
