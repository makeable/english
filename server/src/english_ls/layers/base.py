"""A layer reads a parsed spaCy Doc and adds words, regions or flags to an Analysis.

New kinds of analysis (phrase trees, coreference, semantic roles, LLM passes)
plug in by implementing this protocol and being added to `default_layers()`.
"""

from __future__ import annotations

from typing import Protocol

from spacy.tokens import Doc

from ..model import Analysis


class Layer(Protocol):
    name: str

    def analyze(self, doc: Doc, out: Analysis) -> None: ...
