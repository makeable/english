"""Shared result types. Offsets are into the text the layer analysed."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    start: int
    end: int
    pos: str  # semantic token type, e.g. "noun"
    role: str | None = None  # "subject", "object", "predicate", "complement", "adjunct"
    role_head: bool = False  # the word that carries the role (e.g. the subject's head noun)
    entity: str | None = None  # entity category, e.g. "entityPerson"
    hover: str = ""  # markdown shown on hover


@dataclass(frozen=True)
class Region:
    """A multi-word span: clause, noun phrase, entity or role run."""

    start: int
    end: int
    kind: str  # "clause" | "phrase" | "entity" | "role"
    label: str
    depth: int = 0


@dataclass(frozen=True)
class Flag:
    """A style issue, shown as a diagnostic."""

    start: int
    end: int
    code: str
    message: str


@dataclass
class Analysis:
    words: list[Word] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    def shifted(self, mapper) -> "Analysis":
        """Map every offset through `mapper(start, end, loose) -> (start, end) | None`."""
        out = Analysis()
        for w in self.words:
            r = mapper(w.start, w.end, False)
            if r:
                out.words.append(_replace(w, r))
        for g in self.regions:
            r = mapper(g.start, g.end, True)
            if r:
                out.regions.append(_replace(g, r))
        for f in self.flags:
            r = mapper(f.start, f.end, True)
            if r:
                out.flags.append(_replace(f, r))
        return out

    def extend(self, other: "Analysis") -> None:
        self.words.extend(other.words)
        self.regions.extend(other.regions)
        self.flags.extend(other.flags)


def _replace(obj, r):
    from dataclasses import replace

    return replace(obj, start=r[0], end=r[1])
