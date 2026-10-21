"""Start the real server over stdio and talk LSP to it."""

import asyncio
import sys

from lsprotocol import types
from pygls.lsp.client import BaseLanguageClient

from english_ls.tokens import TOKEN_TYPES

TEXT = "The cake was eaten by the children.\n\n```\nnot prose\n```\n\nAda Lovelace lives in London."
URI = "file:///tmp/sample.md"


def decode(data, text):
    lines = text.split("\n")
    out = []
    line = col = 0
    for i in range(0, len(data), 5):
        dl, dc, length, typ, mods = data[i : i + 5]
        line += dl
        col = dc if dl else col + dc
        out.append((lines[line][col : col + length], TOKEN_TYPES[typ], mods))
    return out


async def run_session():
    client = BaseLanguageClient("test-client", "0")
    diagnostics = asyncio.get_running_loop().create_future()

    @client.feature(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    def on_diags(params):
        if params.diagnostics and not diagnostics.done():
            diagnostics.set_result(params.diagnostics)

    @client.feature(types.WINDOW_SHOW_MESSAGE)
    def on_message(params):
        pass

    @client.feature("english/modelLoaded")
    def on_loaded(params):
        pass

    @client.feature("english/analysisReady")
    def on_ready(params):
        pass

    await client.start_io(sys.executable, "-m", "english_ls", "--log-level", "WARNING")
    try:
        await client.initialize_async(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                initialization_options={"model": "en_core_web_sm"},
            )
        )
        client.initialized(types.InitializedParams())
        client.text_document_did_open(
            types.DidOpenTextDocumentParams(
                text_document=types.TextDocumentItem(uri=URI, language_id="markdown", version=1, text=TEXT)
            )
        )
        doc = types.TextDocumentIdentifier(uri=URI)
        tokens = await asyncio.wait_for(
            client.text_document_semantic_tokens_full_async(types.SemanticTokensParams(text_document=doc)), 60
        )
        diags = await asyncio.wait_for(diagnostics, 10)
        hover = await client.text_document_hover_async(
            types.HoverParams(text_document=doc, position=types.Position(line=0, character=4))
        )
        client.protocol.notify("english/setView", {"view": "roles"})
        roles = await client.text_document_semantic_tokens_full_async(types.SemanticTokensParams(text_document=doc))
        spans = await client.protocol.send_request_async("english/spans", {"uri": URI})
        return tokens, diags, hover, roles, spans
    finally:
        await client.shutdown_async(None)
        client.exit(None)
        await client.stop()


def test_server_end_to_end():
    tokens, diags, hover, roles, spans = asyncio.run(run_session())

    words = decode(tokens.data, TEXT)
    assert ("cake", "noun", 0) in words
    assert ("eaten", "verb", 0) in words
    assert ("London", "properNoun", 0) in words
    assert not any(w[0] in ("not", "prose") for w in words)  # code block untouched

    assert any(d.code == "passive" for d in diags)

    assert hover is not None and "noun" in hover.contents.value

    role_words = decode(roles.data, TEXT)
    assert ("cake", "subject", 1) in role_words  # head modifier set

    kinds = {r.kind for r in spans.regions}
    assert {"role", "entity", "phrase"} <= kinds
