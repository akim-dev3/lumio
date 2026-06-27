"""LLM service for LUMIO's four tools.

Uses OpenRouter (OpenAI-compatible chat API) under the hood. Module is still
named ``gemini`` for backwards compatibility with handler imports — the public
function signatures are unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional

import aiohttp

from bot.config import config


logger = logging.getLogger(__name__)


_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = aiohttp.ClientTimeout(total=120, connect=15)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter recommends these for analytics + free-tier eligibility.
        "HTTP-Referer": config.webapp_url or "https://lumio.bot",
        "X-Title": "LUMIO",
    }


# Strip ```json … ``` fences if the model wrapped its JSON in markdown.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _extract_first_json(text: str) -> Optional[str]:
    """Find the first balanced JSON object or array in ``text``.

    Some free models prepend a sentence like "Here is the JSON: …" before the
    payload. We scan for the first ``{`` or ``[`` and walk the bracket stack.
    """
    cleaned = _strip_fences(text)
    start = -1
    for i, ch in enumerate(cleaned):
        if ch in "{[":
            start = i
            break
    if start < 0:
        return None
    stack: list[str] = []
    in_str = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, ch) not in (("{", "}"), ("[", "]")):
                return None
            if not stack:
                return cleaned[start : i + 1]
    return None


async def _call_llm(prompt: str, *, json_mode: bool) -> Optional[str]:
    """One round-trip to OpenRouter. Returns the assistant content or ``None``.

    On HTTP 429 we honour the provider's ``Retry-After`` (capped at 20 s) and
    make exactly one extra attempt before giving up.
    """
    body: dict[str, Any] = {
        "model": config.openrouter_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are LUMIO, an AI productivity assistant. "
                    "When asked to return JSON, return ONLY the JSON value, "
                    "without any prose, explanations, or markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    data: Optional[dict] = None
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            for attempt in (1, 2):
                async with session.post(_API_URL, headers=_headers(), json=body) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        break
                    text = await resp.text()
                    logger.warning(
                        "OpenRouter HTTP %d (attempt %d): %s",
                        resp.status, attempt, text[:500],
                    )
                    if resp.status == 429 and attempt == 1:
                        retry_after = min(
                            int(resp.headers.get("Retry-After", "5")), 20
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    return None
    except asyncio.TimeoutError:
        logger.warning("OpenRouter request timed out")
        return None
    except Exception:
        logger.exception("OpenRouter request failed")
        return None

    if data is None:
        return None

    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logger.warning("OpenRouter unexpected response: %r", str(data)[:500])
        return None

    if not isinstance(content, str) or not content.strip():
        logger.warning("OpenRouter empty content. finish_reason=%r", choice.get("finish_reason"))
        return None
    return content


async def _generate_json(
    prompt: str,
    validator: Callable[[Any], Optional[str]],
) -> Optional[Any]:
    """Call the LLM, parse JSON, validate. Retry once on any failure."""
    for attempt in (1, 2):
        raw = await _call_llm(prompt, json_mode=True)
        if raw is None:
            continue
        candidate = _extract_first_json(raw) or _strip_fences(raw)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.warning(
                "JSON parse failed (attempt %d): %s :: raw=%r",
                attempt, exc, raw[:500],
            )
            continue
        error = validator(parsed)
        if error:
            logger.warning(
                "JSON validation failed (attempt %d): %s :: raw=%r",
                attempt, error, raw[:500],
            )
            continue
        return parsed
    return None


# ----------------------------------------------------------------------------
# Tool 1: Anki flashcard generator
# ----------------------------------------------------------------------------

async def generate_cards(text: str, count: int) -> Optional[list[dict]]:
    text = text.strip()
    if not text:
        return None
    count = max(1, min(count, 50))
    prompt = (
        "You are a professional educator. "
        f"Create exactly {count} Anki flashcards from the text below. "
        "Each card has a concise question on 'front' and a precise, "
        "self-contained answer on 'back'. Cover the most important facts, "
        "definitions and relationships. Avoid trivial or duplicate cards. "
        "Use the same language as the source text.\n\n"
        "Return ONLY a JSON object of the form:\n"
        '{ "cards": [ { "front": "...", "back": "..." }, ... ] }\n\n'
        f"Text:\n{text[:12000]}"
    )

    def validate(data: Any) -> Optional[str]:
        if isinstance(data, list):
            cards = data
        elif isinstance(data, dict) and isinstance(data.get("cards"), list):
            cards = data["cards"]
        else:
            return "expected list or { cards: [...] }"
        if not cards:
            return "empty cards"
        for i, item in enumerate(cards):
            if not isinstance(item, dict):
                return f"item {i} not a dict"
            front, back = item.get("front"), item.get("back")
            if not isinstance(front, str) or not front.strip():
                return f"item {i} empty 'front'"
            if not isinstance(back, str) or not back.strip():
                return f"item {i} empty 'back'"
        return None

    result = await _generate_json(prompt, validate)
    if result is None:
        return None
    cards = result if isinstance(result, list) else result["cards"]
    return cards[:count]


# ----------------------------------------------------------------------------
# Tool 2: Telegram post copywriter
# ----------------------------------------------------------------------------

_TONE_HINTS = {
    "casual": "friendly, conversational, witty",
    "professional": "expert, polished, authoritative",
    "viral": "punchy hooks, curiosity gaps, high-energy",
}


async def generate_posts(topic: str, count: int, tone: str) -> Optional[list[str]]:
    topic = topic.strip()
    if not topic:
        return None
    count = max(1, min(count, 10))
    tone_norm = tone.lower().strip()
    tone_hint = _TONE_HINTS.get(tone_norm, _TONE_HINTS["casual"])
    prompt = (
        "You are a top Telegram channel copywriter. "
        f"Write {count} engaging Telegram posts about: {topic}. "
        f"Tone: {tone_norm} ({tone_hint}). "
        "Each post is at most 900 characters. "
        "Open with a strong hook in the first line. Use emojis tastefully. "
        "Use line breaks for readability. End each post with a soft CTA or a question. "
        "Use the same language as the topic.\n\n"
        "Return ONLY a JSON object of the form:\n"
        '{ "posts": [ "post1", "post2", ... ] }'
    )

    def validate(data: Any) -> Optional[str]:
        if isinstance(data, list):
            posts = data
        elif isinstance(data, dict) and isinstance(data.get("posts"), list):
            posts = data["posts"]
        else:
            return "expected list or { posts: [...] }"
        if not posts:
            return "empty posts"
        for i, s in enumerate(posts):
            if not isinstance(s, str) or not s.strip():
                return f"item {i} empty"
        return None

    result = await _generate_json(prompt, validate)
    if result is None:
        return None
    posts = result if isinstance(result, list) else result["posts"]
    return [p[:900] for p in posts[:count]]


# ----------------------------------------------------------------------------
# Tool 3: PDF analyst
# ----------------------------------------------------------------------------

async def analyze_pdf(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None
    prompt = (
        "You are an expert analyst. Read the document text below and produce "
        "a clear executive summary and key insights. Use the same language as "
        "the document.\n"
        "Return ONLY a JSON object of the form:\n"
        "{\n"
        '  "summary": "3-5 sentence executive summary",\n'
        '  "key_points": ["takeaway 1", "takeaway 2", "..."],\n'
        '  "questions": ["check question 1", "check question 2", "..."]\n'
        "}\n"
        "Provide 3-7 items each in key_points and questions.\n\n"
        f"Document:\n{text[:8000]}"
    )

    def validate(data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return "not a dict"
        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return "empty summary"
        for key in ("key_points", "questions"):
            arr = data.get(key)
            if not isinstance(arr, list) or not arr:
                return f"empty {key}"
            if not all(isinstance(s, str) and s.strip() for s in arr):
                return f"non-string item in {key}"
        return None

    return await _generate_json(prompt, validate)


# ----------------------------------------------------------------------------
# Tool 4: Resume + cover letter generator
# ----------------------------------------------------------------------------

async def generate_resume(vacancy: str, experience: str) -> Optional[dict]:
    vacancy = vacancy.strip()
    experience = experience.strip()
    if not vacancy or not experience:
        return None
    prompt = (
        "You are a professional HR consultant and resume writer. "
        "Create a tailored resume and a cover letter that highlight the "
        "candidate's strengths for the vacancy below. Be specific, use action "
        "verbs and measurable outcomes where possible. Use the same language "
        "as the vacancy description.\n"
        "Return ONLY a JSON object of the form:\n"
        "{\n"
        '  "resume": "full resume text formatted with markdown",\n'
        '  "cover_letter": "complete cover letter text",\n'
        '  "tips": ["tip 1", "tip 2", "tip 3"]\n'
        "}\n"
        "Provide 3-5 short actionable tips.\n\n"
        f"Vacancy:\n{vacancy[:4000]}\n\n"
        f"Candidate experience:\n{experience[:4000]}"
    )

    def validate(data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return "not a dict"
        if not isinstance(data.get("resume"), str) or not data["resume"].strip():
            return "empty resume"
        if not isinstance(data.get("cover_letter"), str) or not data["cover_letter"].strip():
            return "empty cover_letter"
        tips = data.get("tips")
        if not isinstance(tips, list) or not tips:
            return "empty tips"
        if not all(isinstance(t, str) and t.strip() for t in tips):
            return "non-string item in tips"
        return None

    return await _generate_json(prompt, validate)
