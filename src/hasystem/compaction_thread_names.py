from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

CONTINUATION_SUFFIX_RE: Final = re.compile(r"^(?P<base>.+?) continuation (?P<sequence>[2-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class ContinuationThreadName:
    original_name: str | None
    sequence: int
    next_name: str


@dataclass(frozen=True, slots=True)
class ParsedContinuationName:
    base: str
    sequence: int


def build_continuation_thread_name(
    *,
    original_name: str | None,
    current_name: str | None,
    current_sequence: int,
    fallback_name: str,
) -> ContinuationThreadName:
    parsed = _parse_continuation_name(current_name)
    base = _non_empty(original_name) or (parsed.base if parsed else _non_empty(current_name))
    if base is None:
        return ContinuationThreadName(original_name=None, sequence=current_sequence + 1, next_name=fallback_name)
    parsed_next_sequence = parsed.sequence + 1 if parsed else 2
    sequence = max(current_sequence + 1, parsed_next_sequence)
    return ContinuationThreadName(
        original_name=base,
        sequence=sequence,
        next_name=f"{base} continuation {sequence}",
    )


def _parse_continuation_name(value: str | None) -> ParsedContinuationName | None:
    clean_value = _non_empty(value)
    if clean_value is None:
        return None
    match = CONTINUATION_SUFFIX_RE.fullmatch(clean_value)
    if match is None:
        return None
    return ParsedContinuationName(base=match.group("base"), sequence=int(match.group("sequence")))


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    clean_value = value.strip()
    return clean_value or None
