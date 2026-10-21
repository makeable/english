import pytest

from english_ls.analyzer import Analyzer, load_model


@pytest.fixture(scope="module")
def analyzer():
    # Tests use the small model so they're fast and deterministic.
    nlp, name = load_model("en_core_web_sm")
    assert name == "en_core_web_sm"
    return Analyzer(nlp, name)


def words(doc_text, analysis):
    return {doc_text[w.start : w.end]: w for w in analysis.words}


def test_parts_of_speech_and_roles(analyzer):
    text = "The old dog chased a red ball."
    a = analyzer.analyze_document(text, "plaintext")
    w = words(text, a)
    assert w["dog"].pos == "noun"
    assert w["chased"].pos == "verb"
    assert w["old"].pos == "adjective"
    assert w["dog"].role == "subject" and w["dog"].role_head
    assert w["old"].role == "subject" and not w["old"].role_head
    assert w["chased"].role == "predicate"
    assert w["ball"].role == "object"
    roles = [(text[r.start : r.end], r.label) for r in a.regions if r.kind == "role"]
    assert ("The old dog", "subject") in roles
    assert ("a red ball", "object") in roles


def test_relative_clause_region(analyzer):
    text = "The man who called yesterday left early."
    a = analyzer.analyze_document(text, "plaintext")
    clauses = [(text[r.start : r.end], r.label) for r in a.regions if r.kind == "clause"]
    assert ("who called yesterday", "relative clause") in clauses


def test_entities(analyzer):
    text = "Ada Lovelace moved to London in 1835."
    a = analyzer.analyze_document(text, "plaintext")
    w = words(text, a)
    assert w["Ada"].entity == "entityPerson"
    assert w["London"].entity == "entityPlace"
    ents = {text[r.start : r.end]: r.label for r in a.regions if r.kind == "entity"}
    assert ents.get("Ada Lovelace") == "PERSON"


def test_style_flags(analyzer):
    text = "The cake was eaten by the children. It is really very good. I went to the the shop."
    a = analyzer.analyze_document(text, "plaintext")
    codes = {(f.code, text[f.start : f.end]) for f in a.flags}
    assert ("passive", "was eaten") in codes
    assert ("filler", "really") in codes
    assert ("repeated-word", "the the") in codes


def test_markdown_offsets_point_at_source(analyzer):
    text = "Intro.\n\n```\ncode here\n```\n\nThe **cat** sat on `mat`."
    a = analyzer.analyze_document(text, "markdown")
    found = [text[w.start : w.end] for w in a.words]
    assert "cat" in found and "sat" in found
    assert "here" not in found  # code block is skipped
    assert "code" not in found  # inline-code placeholder is never highlighted


def test_cache_reuses_unchanged_paragraphs(analyzer):
    analyzer.analyze_document("First paragraph here.\n\nSecond one.", "plaintext")
    before = len(analyzer.cache._items)
    analyzer.analyze_document("First paragraph here.\n\nSecond one changed.", "plaintext")
    assert len(analyzer.cache._items) == before + 1
