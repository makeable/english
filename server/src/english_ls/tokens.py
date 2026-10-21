"""Turn an Analysis into LSP semantic tokens for the active view."""

from __future__ import annotations

from .model import Analysis
from .positions import LineIndex

POS_TOKEN_TYPES = [
    "noun", "properNoun", "verb", "auxiliary", "adjective", "adverb", "pronoun",
    "determiner", "adposition", "conjunction", "numeral", "particle", "interjection",
]
ROLE_TOKEN_TYPES = ["subject", "predicate", "object", "complement", "adjunct"]
ENTITY_TOKEN_TYPES = [
    "entityPerson", "entityPlace", "entityOrg", "entityTime", "entityQuantity", "entityOther",
]
TOKEN_TYPES = POS_TOKEN_TYPES + ROLE_TOKEN_TYPES + ENTITY_TOKEN_TYPES
TOKEN_MODIFIERS = ["head"]

VIEWS = ("all", "pos", "roles", "entities")

_type_index = {t: i for i, t in enumerate(TOKEN_TYPES)}
HEAD_BIT = 1 << TOKEN_MODIFIERS.index("head")


def encode(analysis: Analysis, index: LineIndex, view: str) -> list[int]:
    data: list[int] = []
    prev_line = prev_col = 0
    for w in analysis.words:
        mods = 0
        if view == "roles":
            kind = w.role
            if w.role_head:
                mods |= HEAD_BIT
        elif view == "entities":
            kind = w.entity
        else:
            kind = w.pos
        if kind is None:
            continue
        start = index.position(w.start)
        end = index.position(w.end)
        if start.line != end.line or end.character <= start.character:
            continue  # semantic tokens can't span lines
        delta_line = start.line - prev_line
        delta_col = start.character - prev_col if delta_line == 0 else start.character
        data += [delta_line, delta_col, end.character - start.character, _type_index[kind], mods]
        prev_line, prev_col = start.line, start.character
    return data
