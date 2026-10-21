"""Core grammar layer: parts of speech, sentence roles, clauses, noun phrases, entities."""

from __future__ import annotations

import spacy
from spacy.tokens import Doc, Token

from ..model import Analysis, Region, Word
from ..prose import CODE_PLACEHOLDER, LINK_PLACEHOLDER

POS_TYPES = {
    "NOUN": "noun",
    "PROPN": "properNoun",
    "VERB": "verb",
    "AUX": "auxiliary",
    "ADJ": "adjective",
    "ADV": "adverb",
    "PRON": "pronoun",
    "DET": "determiner",
    "ADP": "adposition",
    "CCONJ": "conjunction",
    "SCONJ": "conjunction",
    "NUM": "numeral",
    "PART": "particle",
    "INTJ": "interjection",
}

# Dependency label -> sentence role. The role covers the word's whole subtree.
ROLE_DEPS = {
    "nsubj": "subject",
    "nsubjpass": "subject",
    "csubj": "subject",
    "csubjpass": "subject",
    "expl": "subject",
    "dobj": "object",
    "obj": "object",
    "iobj": "object",
    "dative": "object",
    "attr": "complement",
    "acomp": "complement",
    "oprd": "complement",
    "xcomp": "complement",
    "ccomp": "complement",
    "advmod": "adjunct",
    "npadvmod": "adjunct",
    "prep": "adjunct",
    "advcl": "adjunct",
    "agent": "adjunct",
}
# Words that join the main verb to make the predicate ("has been eating", "gave up").
VERB_CHAIN_DEPS = {"aux", "auxpass", "neg", "prt"}

CLAUSE_DEPS = {
    "relcl": "relative clause",
    "advcl": "adverbial clause",
    "ccomp": "complement clause",
    "xcomp": "open complement clause",
    "csubj": "subject clause",
    "csubjpass": "subject clause",
    "acl": "adnominal clause",
    "pcomp": "prepositional complement clause",
}

ENTITY_TYPES = {
    "PERSON": "entityPerson",
    "GPE": "entityPlace",
    "LOC": "entityPlace",
    "FAC": "entityPlace",
    "ORG": "entityOrg",
    "NORP": "entityOrg",
    "DATE": "entityTime",
    "TIME": "entityTime",
    "MONEY": "entityQuantity",
    "PERCENT": "entityQuantity",
    "QUANTITY": "entityQuantity",
    "CARDINAL": "entityQuantity",
    "ORDINAL": "entityQuantity",
}
ENTITY_OTHER = "entityOther"

PLACEHOLDERS = {CODE_PLACEHOLDER, LINK_PLACEHOLDER}


def _is_predicate(tok: Token) -> bool:
    if tok.dep_ == "ROOT":
        return True
    if tok.dep_ in VERB_CHAIN_DEPS and tok.head.dep_ == "ROOT":
        return True
    if tok.dep_ == "conj" and tok.head.dep_ == "ROOT" and tok.pos_ in ("VERB", "AUX"):
        return True  # "She sang and danced."
    return False


def role_of(tok: Token) -> tuple[str | None, bool]:
    """The innermost sentence role this word belongs to, and whether it heads it."""
    if _is_predicate(tok):
        return "predicate", tok.dep_ in ("ROOT", "conj")
    node = tok
    while True:
        role = ROLE_DEPS.get(node.dep_)
        if role is None and node.dep_ == "conj" and node.head is not node:
            # coordinated phrases share their head's role: "cats and dogs"
            role = ROLE_DEPS.get(node.head.dep_)
        if role:
            return role, node is tok
        if node.head is node or node.dep_ == "ROOT":
            return None, False
        node = node.head


def _describe(tok: Token, role: str | None) -> str:
    lines = [f"**{POS_TYPES.get(tok.pos_, tok.pos_.lower())}** `{tok.tag_}` — {spacy.explain(tok.tag_) or ''}"]
    morph = tok.morph.to_dict()
    if morph:
        lines.append(", ".join(f"{k}: {v}" for k, v in morph.items()))
    if tok.lemma_ and tok.lemma_.lower() != tok.text.lower():
        lines.append(f"lemma: *{tok.lemma_}*")
    dep = spacy.explain(tok.dep_) or tok.dep_
    if tok.dep_ == "ROOT":
        lines.append("dependency: **root** of the sentence")
    else:
        lines.append(f"dependency: **{dep}** (`{tok.dep_}`) of *{tok.head.text}*")
    if role:
        lines.append(f"sentence role: **{role}**")
    if tok.ent_type_:
        lines.append(f"entity: **{tok.ent_type_}** — {spacy.explain(tok.ent_type_) or ''}")
    return "\n\n".join(lines)


def _span_bounds(tokens: list[Token]) -> tuple[int, int]:
    first, last = tokens[0], tokens[-1]
    return first.idx, last.idx + len(last.text)


class SpacyCoreLayer:
    name = "core"

    def analyze(self, doc: Doc, out: Analysis) -> None:
        roles: list[tuple[int, int, str]] = []  # (start, end, role) per word, for role runs

        for tok in doc:
            pos = POS_TYPES.get(tok.pos_)
            if pos is None or tok.like_url or tok.like_email or tok.text in PLACEHOLDERS:
                continue
            role, head = role_of(tok)
            entity = None
            if tok.ent_type_:
                entity = ENTITY_TYPES.get(tok.ent_type_, ENTITY_OTHER)
            out.words.append(
                Word(
                    start=tok.idx,
                    end=tok.idx + len(tok.text),
                    pos=pos,
                    role=role,
                    role_head=head,
                    entity=entity,
                    hover=_describe(tok, role),
                )
            )
            if role:
                roles.append((tok.idx, tok.idx + len(tok.text), role))

        out.regions.extend(_role_runs(doc, roles))

        for sent in doc.sents:
            for tok in sent:
                label = CLAUSE_DEPS.get(tok.dep_)
                if tok.dep_ == "conj" and tok.pos_ in ("VERB", "AUX") and tok.head.pos_ in ("VERB", "AUX"):
                    label = "coordinated clause"
                if not label:
                    continue
                start, end = _span_bounds([tok.left_edge, tok.right_edge])
                depth = sum(1 for a in tok.ancestors if a.dep_ in CLAUSE_DEPS or a.dep_ == "conj")
                out.regions.append(Region(start, end, "clause", label, depth + 1))

        for chunk in doc.noun_chunks:
            start, end = _span_bounds(list(chunk))
            out.regions.append(Region(start, end, "phrase", "noun phrase"))

        for ent in doc.ents:
            start, end = _span_bounds(list(ent))
            out.regions.append(Region(start, end, "entity", ent.label_))


def _role_runs(doc: Doc, roles: list[tuple[int, int, str]]):
    """Merge neighbouring words with the same role into one region (e.g. a whole subject)."""
    runs: list[Region] = []
    for start, end, role in roles:
        if runs and runs[-1].label == role and _only_gap(doc.text, runs[-1].end, start):
            last = runs.pop()
            runs.append(Region(last.start, end, "role", role))
        else:
            runs.append(Region(start, end, "role", role))
    return runs


def _only_gap(text: str, a: int, b: int) -> bool:
    gap = text[a:b]
    return all(c.isspace() or c in ",'’-\"“”" for c in gap)
