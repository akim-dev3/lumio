"""PDF → plain text extractor backed by PyMuPDF."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import fitz  # PyMuPDF


logger = logging.getLogger(__name__)


MAX_PAGES = 50
MAX_CHARS = 60_000


def _extract_sync(data: bytes) -> Optional[str]:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        logger.exception("Failed to open PDF")
        return None
    try:
        chunks: list[str] = []
        for index, page in enumerate(doc):
            if index >= MAX_PAGES:
                break
            chunks.append(page.get_text("text"))
            if sum(len(c) for c in chunks) >= MAX_CHARS:
                break
        text = "\n".join(chunks).strip()
    finally:
        doc.close()
    if not text:
        return None
    return text[:MAX_CHARS]


async def extract_text(data: bytes) -> Optional[str]:
    """Extract up to :data:`MAX_CHARS` characters from the first :data:`MAX_PAGES` pages."""
    if not data:
        return None
    return await asyncio.to_thread(_extract_sync, data)
