"""Convert between Python string offsets and LSP positions (line, UTF-16 column)."""

from __future__ import annotations

import bisect

from lsprotocol import types


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


class LineIndex:
    def __init__(self, text: str) -> None:
        self.text = text
        self.line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self.line_starts.append(i + 1)

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.line_starts, offset) - 1

    def position(self, offset: int) -> types.Position:
        offset = max(0, min(offset, len(self.text)))
        line = self.line_of(offset)
        col = _utf16_len(self.text[self.line_starts[line] : offset])
        return types.Position(line=line, character=col)

    def range(self, start: int, end: int) -> types.Range:
        return types.Range(start=self.position(start), end=self.position(end))

    def offset(self, pos: types.Position) -> int:
        if pos.line >= len(self.line_starts):
            return len(self.text)
        start = self.line_starts[pos.line]
        end = self.line_starts[pos.line + 1] if pos.line + 1 < len(self.line_starts) else len(self.text)
        units = 0
        for i in range(start, end):
            if units >= pos.character:
                return i
            units += 2 if ord(self.text[i]) > 0xFFFF else 1
        return end
