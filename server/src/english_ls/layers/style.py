"""Style flags built on the parse: passive voice, long sentences, filler words, repeats."""

from __future__ import annotations

from spacy.tokens import Doc

from ..model import Analysis, Flag

FILLER_WORDS = {
    "very", "really", "just", "actually", "basically", "quite", "rather",
    "somewhat", "literally", "simply", "totally", "truly", "extremely",
}
FILLER_PHRASES = {
    ("in", "order", "to"): "Usually 'to' is enough.",
    ("kind", "of"): "Hedge word; consider removing.",
    ("sort", "of"): "Hedge word; consider removing.",
    ("due", "to", "the", "fact", "that"): "Consider 'because'.",
    ("at", "this", "point", "in", "time"): "Consider 'now'.",
}


class StyleLayer:
    name = "style"

    def __init__(self, long_sentence_words: int = 35) -> None:
        self.long_sentence_words = long_sentence_words

    def analyze(self, doc: Doc, out: Analysis) -> None:
        for sent in doc.sents:
            words = [t for t in sent if not t.is_punct and not t.is_space]
            if len(words) > self.long_sentence_words:
                last = words[-1]
                out.flags.append(
                    Flag(
                        sent.start_char,
                        last.idx + len(last.text),
                        "long-sentence",
                        f"Long sentence ({len(words)} words). Consider splitting it.",
                    )
                )

        for tok in doc:
            if tok.dep_ == "auxpass":
                verb = tok.head
                start = min(tok.idx, verb.idx)
                end = max(tok.idx + len(tok.text), verb.idx + len(verb.text))
                agent = next((c for c in verb.children if c.dep_ == "agent"), None)
                hint = ""
                if agent is not None and agent.right_edge.i > agent.i:
                    doer = doc[agent.i + 1 : agent.right_edge.i + 1].text
                    hint = f" Try making '{doer}' the subject."
                out.flags.append(
                    Flag(start, end, "passive", f"Passive voice: '{doc.text[start:end]}'.{hint}")
                )

            low = tok.lower_
            if low in FILLER_WORDS and tok.pos_ in ("ADV", "ADJ"):
                out.flags.append(
                    Flag(tok.idx, tok.idx + len(tok.text), "filler", f"Filler word '{tok.text}'; often removable.")
                )

            nxt = tok.nbor(1) if tok.i + 1 < len(doc) else None
            if nxt is not None and tok.is_alpha and nxt.lower_ == low and tok.whitespace_:
                out.flags.append(
                    Flag(tok.idx, nxt.idx + len(nxt.text), "repeated-word", f"Repeated word '{tok.text}'.")
                )

        lowers = [t.lower_ for t in doc]
        for phrase, advice in FILLER_PHRASES.items():
            n = len(phrase)
            for i in range(len(lowers) - n + 1):
                if tuple(lowers[i : i + n]) == phrase:
                    first, last = doc[i], doc[i + n - 1]
                    out.flags.append(
                        Flag(first.idx, last.idx + len(last.text), "filler", f"'{doc[i : i + n].text}': {advice}")
                    )
