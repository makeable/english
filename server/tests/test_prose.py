from lsprotocol import types

from english_ls.positions import LineIndex
from english_ls.prose import CODE_PLACEHOLDER, extract_markdown, extract_plaintext


def words_back_to_source(doc: str, seg) -> list[str]:
    """Map each clean word back to the document text it came from."""
    out = []
    i = 0
    text = seg.text
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        j = i
        while j < len(text) and not text[j].isspace():
            j += 1
        r = seg.doc_range(i, j)
        out.append(doc[r[0] : r[1]] if r else None)
        i = j
    return out


def test_plaintext_paragraphs():
    doc = "First line\ncontinues here.\n\nSecond para."
    segs = extract_plaintext(doc)
    assert [s.text for s in segs] == ["First line continues here.", "Second para."]
    assert words_back_to_source(doc, segs[1]) == ["Second", "para."]


def test_markdown_skips_code_blocks_and_front_matter():
    doc = "---\ntitle: Hello\n---\n\n# Heading\n\nSome text.\n\n```python\nx = 1\n```\n\n    indented code\n"
    texts = [s.text for s in extract_markdown(doc)]
    assert texts == ["Heading", "Some text."]


def test_markdown_inline_markup_maps_to_source():
    doc = "- The **quick** brown [fox](http://example.com) jumps.\n"
    (seg,) = extract_markdown(doc)
    assert seg.text == "The quick brown fox jumps."
    assert words_back_to_source(doc, seg) == ["The", "quick", "brown", "fox", "jumps."]


def test_markdown_inline_code_becomes_placeholder():
    doc = "Run `npm install` before you start."
    (seg,) = extract_markdown(doc)
    assert seg.text == f"Run {CODE_PLACEHOLDER} before you start."
    words = words_back_to_source(doc, seg)
    assert words[1] is None  # placeholder is never highlighted
    assert words[2:] == ["before", "you", "start."]


def test_markdown_soft_break_and_blockquote():
    doc = "> The cat\n> sat down."
    (seg,) = extract_markdown(doc)
    assert seg.text == "The cat sat down."
    assert words_back_to_source(doc, seg) == ["The", "cat", "sat", "down."]


def test_numbered_list_marker_not_confused_with_text():
    doc = "1. 1st place goes to Ana."
    (seg,) = extract_markdown(doc)
    assert words_back_to_source(doc, seg)[0] == "1st"


def test_positions_utf16():
    text = "ab\n😀 cat"
    idx = LineIndex(text)
    cat = text.index("cat")
    pos = idx.position(cat)
    assert (pos.line, pos.character) == (1, 3)  # emoji is two UTF-16 units
    assert idx.offset(types.Position(line=1, character=3)) == cat
