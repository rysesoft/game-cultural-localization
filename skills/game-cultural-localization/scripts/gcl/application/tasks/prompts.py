"""Prompt templates, chunking budgets and cache priming utilities for batched LLM tasks."""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, TypeVar

__layer__ = "application"
__pattern__ = "Policy Constants and Chunking"
__owns__ = "task system prompts, everyday word rules, batch row/char budgets and chunking"

KEYED_ATTEMPTS = 3
SPLIT_DEPTH = 2
T = TypeVar("T")

ISSUE_TYPES: Tuple[str, ...] = (
    "translationese", "register", "tense", "regional_leak", "gender_leak",
    "ui_verb", "placeholder_grammar", "terminology", "other", "none",
)
REGISTERS: Tuple[str, ...] = ("ui", "tutorial", "dialogue_casual", "dialogue_formal")

DEFAULT_SYSTEM: Dict[str, str] = {
    "pass1": (
        "You are a senior game localizer. Translate each source line into natural, native {locale} as a real player "
        "would say or read it. Keep every placeholder, tag and leading or trailing space exactly. Reply with JSON only."
    ),
    "literal": (
        "Translate each English line into {locale} word for word. Keep the English word order and sentence structure, "
        "do not use idioms or everyday expressions, translate every word literally. Keep placeholders and tags. "
        "Reply with JSON only."
    ),
    "roundtrip": (
        "Translate each {locale} line back into English as literally as possible, keeping its structure and word order. "
        "Do not polish the English. Reply with JSON only."
    ),
    "jury": (
        "You are a native {locale} gamer and LQA lead. You never see the source text. Score how natural each line sounds "
        "to a native player from 1 (broken) to 5 (native born). Reply with JSON only."
    ),
    "pairwise": (
        "You are a native {locale} gamer. For each pair, choose the line a native speaker would more naturally write "
        "or say. Reply with JSON only."
    ),
}

EVERYDAY_CAP = 3
EVERYDAY_MIN_JURORS = 2
EVERYDAY_CHECK = (
    "First ask of every word of the line whether it belongs to everyday use of the target language. Would a native "
    "speaker use it in daily life for this meaning, or read it in this kind of game text? A rare, bookish, archaic, "
    "made up, word for word or dictionary choice is not everyday, even when it is correct. Proper names, placeholders, "
    "tags and the game's own terms that the context map names are not judged this way. List the words of the line "
    'that are not everyday in "odd_words", an empty list when there is none. This answer weighs heavily. When two of '
    "the three jurors list a word of the same line, the line scores 3 at most. "
)

INSTRUCTIONS: Dict[str, str] = {
    "pass1": 'Translate every row. Reply with {"rows": [{"key": "...", "target": "..."}]} and nothing else.',
    "literal": 'Translate every row literally. Reply with {"rows": [{"key": "...", "target": "..."}]} and nothing else.',
    "roundtrip": 'Back-translate every row into English. Reply with {"rows": [{"key": "...", "back": "..."}]} and nothing else.',
    "jury": (
        EVERYDAY_CHECK + 'Then score every entry. Reply with {"votes": [{"key": "...", "odd_words": ["..."], "score": 1-5, '
        '"issue_type": "translationese|register|tense|regional_leak|gender_leak|ui_verb|placeholder_grammar|terminology|other|none", '
        '"reason": "...", "suggested": "..."}]}. Use issue_type "none" and empty reason and suggested for score 5.'
    ),
    "pairwise": 'For every pair reply with {"choices": [{"id": "...", "choice": "a" or "b"}]} and nothing else.',
    "pass2": (
        'Rewrite every row. A row may carry "odd_words", words the jurors found not everyday for a native speaker. Replace '
        "them with words a native uses every day, unless the context map names one as the game's own term. Reply with "
        '{"rows": [{"key": "...", "candidates": ["...", "...", "..."]}]}, exactly the requested number of different candidates '
        "per row, and nothing else."
    ),
    "pick": (
        'For every item choose the candidate a native player would find most natural for this context. Reply with '
        '{"picks": [{"key": "...", "choice": "<candidate id>"}]} and nothing else.'
    ),
    "deliberate": (
        'You already scored this line ("own"). "others" are the anonymous votes of two other jurors and "evidence" is the '
        "mechanical evidence package (ban list hits, closest approved translation memory lines, back-translation signal). "
        "Weigh them and vote once more. You may keep or change your score. " + EVERYDAY_CHECK + "Reply with "
        '{"odd_words": ["..."], "score": 1-5, "issue_type": "...", "reason": "...", "suggested": "..."} and nothing else.'
    ),
    "deliberate_many": (
        'You already scored every line in "lines" ("own"). For each line "others" are the anonymous votes of two other '
        "jurors and \"evidence\" is the mechanical evidence package (ban list hits, closest approved translation memory "
        "lines, back-translation signal). Weigh them and vote once more on every line, each on its own. You may keep "
        'or change your score. ' + EVERYDAY_CHECK + 'Reply with {"votes": [{"key": "...", "odd_words": ["..."], '
        '"score": 1-5, "issue_type": "...", "reason": "...", "suggested": "..."}]}, one vote per line, and nothing else.'
    ),
}

BATCH_ROWS: Dict[str, int] = {
    "pass1": 100, "literal": 100, "roundtrip": 100, "jury": 100, "pairwise": 50, "pass2": 30, "pick": 50, "deliberate": 25,
}
BATCH_CHARS: Dict[str, int] = {
    "pass1": 20000, "literal": 20000, "roundtrip": 20000, "jury": 24000,
    "pairwise": 24000, "pass2": 10000, "pick": 24000, "deliberate": 16000,
}
BATCH_WORKERS = 64


def chunked(items: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield consecutive slices of at most size items."""
    step = max(1, int(size))
    for i in range(0, len(items), step):
        yield list(items[i:i + step])


def chunked_budget(items: Sequence[T], size: int, max_chars: int, text_of: Callable[[T], str]) -> List[List[T]]:
    """Consecutive slices bounded by both item count and total text character budget."""
    step, cap = max(1, int(size)), max(1, int(max_chars))
    out: List[List[T]] = []
    cur: List[T] = []
    used = 0
    for it in items:
        n = len(text_of(it))
        if cur and (len(cur) >= step or used + n > cap):
            out.append(cur)
            cur, used = [], 0
        cur.append(it)
        used += n
    if cur:
        out.append(cur)
    return out


def _text_len(*fields: str) -> Callable[[Dict[str, Any]], str]:
    return lambda item: "".join(str(item.get(f, "")) for f in fields)


def primes(provider: Any) -> bool:
    """True when first wave batch should run alone to prime prompt cache."""
    caps = getattr(provider, "capabilities", None)
    batched = bool(caps.batched) if caps is not None else bool(getattr(provider, "batched", False))
    return not batched


def system_for(task: str, locale: str, template: Optional[str] = None) -> str:
    """Select caller prompt template or default English instruction formatted for locale."""
    return template if template else DEFAULT_SYSTEM[task].format(locale=locale)


def word_count(text: str) -> int:
    """Word count treating unspaced CJK/Hangul strings as one word per two characters."""
    words = text.split()
    if len(words) <= 1 and len(text.strip()) > 4 and any("\u3040" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for ch in text):
        return max(1, len(text.strip()) // 2)
    return len(words)


def ordered_unique(items: Iterable[T]) -> List[T]:
    """Deduplicate items while keeping first occurrence order."""
    seen: List[T] = []
    for it in items:
        if it not in seen:
            seen.append(it)
    return seen
