"""Convert a list of {front, back} cards into an .apkg file."""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from pathlib import Path
from typing import Iterable

import genanki


# Stable model id so re-imports merge rather than create duplicates.
_MODEL_ID = 1607392319
_MODEL = genanki.Model(
    _MODEL_ID,
    "LUMIO Basic",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        },
    ],
    css=(
        ".card { font-family: -apple-system, system-ui, sans-serif;"
        " font-size: 18px; color: #1a1a1a; background: #ffffff;"
        " text-align: left; padding: 16px; line-height: 1.5; }"
        "hr { border: none; border-top: 1px solid #ccc; margin: 12px 0; }"
    ),
)


def _deck_id(deck_name: str) -> int:
    # Deterministic deck id from name → consistent re-imports.
    digest = hashlib.sha1(deck_name.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _build_apkg(cards: Iterable[dict], deck_name: str, output_path: Path) -> None:
    deck = genanki.Deck(_deck_id(deck_name), deck_name)
    for card in cards:
        front = (card.get("front") or "").strip()
        back = (card.get("back") or "").strip()
        if not front or not back:
            continue
        note = genanki.Note(model=_MODEL, fields=[front, back])
        deck.add_note(note)
    genanki.Package(deck).write_to_file(str(output_path))


async def build_apkg(cards: list[dict], deck_name: str = "LUMIO Deck") -> Path:
    """Build an .apkg in a temp file. Returns the path; caller must delete it."""
    tmp = tempfile.NamedTemporaryFile(
        suffix=".apkg",
        prefix="lumio_",
        delete=False,
    )
    tmp.close()
    output_path = Path(tmp.name)
    await asyncio.to_thread(_build_apkg, cards, deck_name, output_path)
    return output_path
