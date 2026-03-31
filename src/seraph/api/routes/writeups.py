"""Writeup submission routes (community feature).

POST /api/writeups                     — upload a markdown writeup
GET  /api/writeups/status/{task_id}    — poll Celery task status
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, UploadFile

from seraph.api.deps import SettingsDep
from seraph.api.schemas import WriteupSubmitResponse, WriteupTaskStatus

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/writeups", tags=["writeups"])

_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_CONTENT_TYPES = {"text/markdown", "text/plain", "text/x-markdown"}
_SAFE_FILENAME = re.compile(r"^[\w\-. ]+\.md$", re.IGNORECASE)


def _sanitize_filename(name: str) -> str:
    """Strip path separators and dangerous characters from a filename.

    Args:
        name: Raw filename from the upload.

    Returns:
        Safe filename with only alphanumerics, hyphens, underscores, spaces, and dots.
    """
    base = Path(name).name  # strip directory components
    safe = re.sub(r"[^\w\-. ]", "_", base)
    if not safe.endswith(".md"):
        safe = safe + ".md"
    return safe[:128]


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=WriteupSubmitResponse, status_code=202, summary="Submit writeup")
async def submit_writeup(file: UploadFile, cfg: SettingsDep) -> WriteupSubmitResponse:
    """Accept a markdown writeup file and enqueue ingestion.

    Validates file size (max 5 MB), content type (text/*), and filename
    before saving to ``data/writeups/`` and triggering the ingestion
    Celery task.

    Args:
        file: The uploaded markdown file.

    Raises:
        HTTPException: 400 for invalid file type, oversized files, or bad filenames.
    """
    # Content-type validation.
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type '{content_type}'. Only markdown files accepted.",
        )

    raw_name = file.filename or "writeup.md"
    safe_name = _sanitize_filename(raw_name)

    content = await file.read()

    # Size validation.
    if len(content) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content)} bytes). Maximum is {_MAX_SIZE_BYTES} bytes.",
        )

    # Verify it is valid UTF-8 text.
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text.") from exc

    # Reject files that contain embedded HTML script tags.
    if re.search(r"<script", text, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="File contains disallowed HTML content.")

    # Save to writeups directory.
    writeups_dir = Path("./data/writeups")
    writeups_dir.mkdir(parents=True, exist_ok=True)
    dest = writeups_dir / safe_name
    dest.write_bytes(content)

    task_id = str(uuid.uuid4())

    # Enqueue Celery task (best-effort — continue if Celery is unavailable).
    try:
        from seraph.worker import ingest_writeup_task

        task = ingest_writeup_task.delay(str(dest))
        task_id = task.id
    except Exception as exc:
        log.warning("writeups.celery_unavailable", error=str(exc))

    log.info("writeups.submitted", filename=safe_name, task_id=task_id)
    return WriteupSubmitResponse(
        task_id=task_id,
        filename=safe_name,
        status_url=f"/api/writeups/status/{task_id}",
    )


@router.get(
    "/status/{task_id}",
    response_model=WriteupTaskStatus,
    summary="Check ingestion task status",
)
async def writeup_task_status(task_id: str) -> WriteupTaskStatus:
    """Poll the Celery task status for a writeup ingestion job.

    Args:
        task_id: The Celery task ID returned by POST /api/writeups.

    Returns:
        Current task state (PENDING | STARTED | SUCCESS | FAILURE).
    """
    try:
        from celery.result import AsyncResult

        result = AsyncResult(task_id)
        state = result.state
        task_result = None
        error = ""

        if state == "SUCCESS":
            task_result = {"ingested": True}
        elif state == "FAILURE":
            error = str(result.result) if result.result else "Unknown error"

        return WriteupTaskStatus(task_id=task_id, state=state, result=task_result, error=error)
    except Exception as exc:
        log.warning("writeups.task_status_failed", task_id=task_id, error=str(exc))
        return WriteupTaskStatus(task_id=task_id, state="UNKNOWN", error=str(exc))
