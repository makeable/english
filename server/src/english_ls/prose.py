"""Find the prose in a document and turn it into clean text for the NLP model.

Each paragraph becomes a `Segment`: the clean text the model reads, plus a map
from every character of that text back to its offset in the original
document. Markdown markup, code, links' URLs and front matter are removed, so
the parser sees ordinary sentences while highlights still land on the right
characters in the editor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt

# Offset used for characters that don't exist in the source (placeholders,
# joined line breaks). Words containing them are never highlighted.
NO_SOURCE = -1

# Stand-in words so a sentence like "Run `npm install` first" still parses.
CODE_PLACEHOLDER = "code"
LINK_PLACEHOLDER = "link"


@dataclass(frozen=True)
class Segment:
    text: str
    offsets: tuple[int, ...]  # offsets[i] = document offset of text[i], or NO_SOURCE

    def doc_range(self, start: int, end: int) -> tuple[int, int] | None:
        """Map a clean-text range to a document range, if every character has a source."""
        if start >= end:
            return None
        chunk = self.offsets[start:end]
        if NO_SOURCE in chunk:
            return None
        return chunk[0], chunk[-1] + 1

    def doc_range_loose(self, start: int, end: int) -> tuple[int, int] | None:
        """Like doc_range, but skips placeholder characters at the edges (for multi-word spans)."""
        chunk = [o for o in self.offsets[start:end] if o != NO_SOURCE]
        if not chunk:
            return None
        return chunk[0], chunk[-1] + 1


class _Builder:
    def __init__(self) -> None:
        self.chars: list[str] = []
        self.offsets: list[int] = []

    def add(self, text: str, offsets: list[int]) -> None:
        self.chars.append(text)
        self.offsets.extend(offsets)

    def add_virtual(self, text: str) -> None:
        self.add(text, [NO_SOURCE] * len(text))

    def build(self) -> Segment | None:
        text = "".join(self.chars)
        if not text.strip():
            return None
        return Segment(text, tuple(self.offsets))


def extract(text: str, language_id: str) -> list[Segment]:
    if language_id == "markdown":
        return extract_markdown(text)
    return extract_plaintext(text)


_BLANK_LINES = re.compile(r"\n[ \t]*\n")


def extract_plaintext(text: str) -> list[Segment]:
    segments = []
    start = 0
    for m in [*_BLANK_LINES.finditer(text), None]:
        end = m.start() if m else len(text)
        para = text[start:end]
        if para.strip():
            clean = para.replace("\r", " ").replace("\n", " ").replace("\t", " ")
            segments.append(Segment(clean, tuple(range(start, end))))
        if m:
            start = m.end()
    return segments


_md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
_FRONT_MATTER = re.compile(r"\A(---|\+\+\+)[ \t]*\r?\n.*?^\1[ \t]*$", re.S | re.M)


def _blank_out(text: str, start: int, end: int) -> str:
    """Replace a range with spaces (keeping newlines) so offsets don't move."""
    chunk = re.sub(r"[^\n]", " ", text[start:end])
    return text[:start] + chunk + text[end:]


def extract_markdown(text: str) -> list[Segment]:
    fm = _FRONT_MATTER.match(text)
    src = _blank_out(text, 0, fm.end()) if fm else text

    line_starts = [0] + [m.end() for m in re.finditer(r"\n", src)]

    def line_offset(line: int) -> int:
        return line_starts[line] if line < len(line_starts) else len(src)

    segments: list[Segment] = []
    cursor = 0
    region = (0, len(src))
    for tok in _md.parse(src):
        if tok.map is not None:
            region = (line_offset(tok.map[0]), line_offset(tok.map[1]))
        if tok.type != "inline" or not tok.children:
            continue
        cursor = max(cursor, region[0])
        builder = _Builder()
        cursor = _walk_inline(tok.children, src, cursor, region[1], builder)
        seg = builder.build()
        if seg:
            segments.append(seg)
    return segments


def _align(content: str, src: str, cur: int, limit: int) -> tuple[list[int], int]:
    """Find where each character of `content` sits in `src`, moving forward from `cur`."""
    exact = src.find(content, cur, limit)
    if exact != -1:
        return list(range(exact, exact + len(content))), exact + len(content)
    offsets = []
    for ch in content:
        pos = src.find(ch, cur, limit)
        if pos == -1:
            offsets.append(NO_SOURCE)
        else:
            offsets.append(pos)
            cur = pos + 1
    return offsets, cur


def _skip_link_target(src: str, cur: int, limit: int) -> int:
    """Move past `](url)`, `][ref]` or `]` after a link's text."""
    close = src.find("]", cur, limit)
    if close == -1:
        return cur
    cur = close + 1
    if src.startswith("(", cur):
        depth = 0
        for i in range(cur, limit):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
        return cur
    if src.startswith("[", cur):
        end = src.find("]", cur + 1, limit)
        return end + 1 if end != -1 else cur
    return cur


def _walk_inline(children, src: str, cur: int, limit: int, out: _Builder) -> int:
    in_autolink = False
    for child in children:
        t = child.type
        if in_autolink:
            if t == "link_close":
                in_autolink = False
            continue
        if t == "text":
            offsets, cur = _align(child.content, src, cur, limit)
            out.add(child.content, offsets)
        elif t in ("softbreak", "hardbreak"):
            out.add_virtual(" ")
        elif t == "code_inline":
            start = src.find("`", cur, limit)
            if start != -1:
                n = 1
                while src.startswith("`", start + n):
                    n += 1
                end = src.find("`" * n, start + n, limit)
                cur = end + n if end != -1 else start + n
            out.add_virtual(CODE_PLACEHOLDER)
        elif t == "link_open" and child.markup == "autolink":
            end = src.find(">", cur, limit)
            cur = end + 1 if end != -1 else cur
            out.add_virtual(LINK_PLACEHOLDER)
            in_autolink = True
        elif t == "link_close":
            cur = _skip_link_target(src, cur, limit)
        elif t == "image":
            start = src.find("![", cur, limit)
            if start != -1:
                cur = _skip_link_target(src, start + 2, limit)
            out.add_virtual(" ")
        elif t == "html_inline":
            pos = src.find(child.content, cur, limit)
            if pos != -1:
                cur = pos + len(child.content)
            out.add_virtual(" ")
        # emphasis/strong/strikethrough open/close: nothing to add; their
        # markers are skipped when the next text is aligned.
    return cur
