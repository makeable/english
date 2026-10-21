"""Runs the NLP layers over a document's prose, with a per-paragraph cache."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

import spacy
from spacy.language import Language

from .layers.base import Layer
from .layers.spacy_core import SpacyCoreLayer
from .layers.style import StyleLayer
from .model import Analysis
from .prose import Segment, extract

log = logging.getLogger(__name__)

# Tried in order when the configured model isn't installed.
FALLBACK_MODELS = ["en_core_web_trf", "en_core_web_lg", "en_core_web_md", "en_core_web_sm"]


def load_model(preferred: str | None) -> tuple[Language, str]:
    names = [preferred] if preferred else []
    names += [n for n in FALLBACK_MODELS if n != preferred]
    errors = []
    for name in names:
        try:
            return spacy.load(name), name
        except OSError as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError("No spaCy English model is installed.\n" + "\n".join(errors))


class ParagraphCache:
    def __init__(self, max_items: int = 5000) -> None:
        self.max_items = max_items
        self._items: OrderedDict[str, Analysis] = OrderedDict()

    def get(self, key: str) -> Analysis | None:
        item = self._items.get(key)
        if item is not None:
            self._items.move_to_end(key)
        return item

    def put(self, key: str, value: Analysis) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)


def default_layers(long_sentence_words: int = 35) -> list[Layer]:
    return [SpacyCoreLayer(), StyleLayer(long_sentence_words)]


class Analyzer:
    def __init__(self, nlp: Language, model_name: str, layers: list[Layer] | None = None) -> None:
        self.nlp = nlp
        self.model_name = model_name
        self.layers = layers if layers is not None else default_layers()
        self.cache = ParagraphCache()
        self._lock = threading.Lock()  # spaCy pipelines aren't safe to run concurrently

    def analyze_segment_texts(self, texts: list[str]) -> list[Analysis]:
        """Analyse clean paragraph texts. Offsets in results are relative to each text."""
        results: list[Analysis | None] = [self.cache.get(t) for t in texts]
        todo = [i for i, r in enumerate(results) if r is None]
        if todo:
            with self._lock:
                docs = self.nlp.pipe([texts[i] for i in todo], batch_size=32)
                for i, doc in zip(todo, docs):
                    a = Analysis()
                    for layer in self.layers:
                        layer.analyze(doc, a)
                    self.cache.put(texts[i], a)
                    results[i] = a
        return results  # type: ignore[return-value]

    def analyze_document(self, text: str, language_id: str) -> Analysis:
        segments = extract(text, language_id)
        per_segment = self.analyze_segment_texts([s.text for s in segments])
        doc = Analysis()
        for seg, a in zip(segments, per_segment):
            doc.extend(a.shifted(_mapper(seg)))
        doc.words.sort(key=lambda w: w.start)
        return doc


def _mapper(seg: Segment):
    def m(start: int, end: int, loose: bool):
        return seg.doc_range_loose(start, end) if loose else seg.doc_range(start, end)

    return m
