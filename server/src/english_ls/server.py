"""The language server: wires the analyzer to LSP requests."""

from __future__ import annotations

import asyncio
import bisect
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from lsprotocol import types
from pygls.server import LanguageServer

from . import __version__
from .analyzer import Analyzer, default_layers, load_model
from .model import Analysis
from .positions import LineIndex
from .tokens import TOKEN_MODIFIERS, TOKEN_TYPES, VIEWS, encode

log = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 0.3
WAIT_FOR_ANALYSIS_SECONDS = 15


@dataclass
class DocState:
    language_id: str
    version: int
    analysis: Analysis | None = None
    index: LineIndex | None = None
    analyzed_version: int = -1
    task: asyncio.Task | None = None


class EnglishServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("english-ls", __version__)
        self.analyzer: Analyzer | None = None
        self.model_ready = asyncio.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nlp")
        self.docs: dict[str, DocState] = {}
        self.view = "all"
        self.style_checks = True
        self.options: dict = {}

    # --- model -------------------------------------------------------------

    async def load(self) -> None:
        model = self.options.get("model") or "en_core_web_trf"
        long_words = int(self.options.get("longSentenceWords") or 35)
        loop = asyncio.get_running_loop()
        try:
            nlp, name = await loop.run_in_executor(self.executor, load_model, model)
        except RuntimeError as e:
            self.show_message(
                "English highlighter: no spaCy model found. Install one with "
                "`python -m spacy download en_core_web_sm`.",
                types.MessageType.Error,
            )
            log.error("%s", e)
            return
        if name != model:
            self.show_message(
                f"English highlighter: '{model}' isn't installed, using '{name}' instead.",
                types.MessageType.Warning,
            )
        self.analyzer = Analyzer(nlp, name, default_layers(long_words))
        log.info("loaded model %s", name)
        self.model_ready.set()
        self.send_notification("english/modelLoaded", {"model": name})

    # --- analysis ----------------------------------------------------------

    def schedule(self, uri: str, delay: float = DEBOUNCE_SECONDS) -> None:
        state = self.docs.get(uri)
        if state is None:
            return
        if state.task and not state.task.done():
            state.task.cancel()
        state.task = asyncio.ensure_future(self._analyze(uri, delay))

    async def _analyze(self, uri: str, delay: float) -> None:
        await asyncio.sleep(delay)
        await self.model_ready.wait()
        state = self.docs.get(uri)
        if state is None or self.analyzer is None:
            return
        text = self.workspace.get_text_document(uri).source
        version = state.version
        loop = asyncio.get_running_loop()
        analysis = await loop.run_in_executor(
            self.executor, self.analyzer.analyze_document, text, state.language_id
        )
        if self.docs.get(uri) is not state or state.version != version:
            return  # a newer edit has its own analysis coming
        state.analysis = analysis
        state.index = LineIndex(text)
        state.analyzed_version = version
        self.publish(uri, state)
        self.refresh_tokens()
        self.send_notification("english/analysisReady", {"uri": uri, "version": version})

    async def current(self, uri: str) -> DocState | None:
        """The document's analysis, waiting briefly for a pending one to finish."""
        state = self.docs.get(uri)
        while state is not None and state.analyzed_version != state.version and state.task:
            task = state.task
            try:
                await asyncio.wait_for(asyncio.shield(task), WAIT_FOR_ANALYSIS_SECONDS)
            except asyncio.CancelledError:
                if task.cancelled():
                    continue  # superseded by a newer edit; wait for that one
                raise
            except asyncio.TimeoutError:
                break
            state = self.docs.get(uri)
        if state is None or state.analysis is None or state.analyzed_version != state.version:
            return None
        return state

    def publish(self, uri: str, state: DocState) -> None:
        diags = []
        if self.style_checks and state.analysis and state.index:
            for f in state.analysis.flags:
                diags.append(
                    types.Diagnostic(
                        range=state.index.range(f.start, f.end),
                        message=f.message,
                        severity=types.DiagnosticSeverity.Information,
                        source="english",
                        code=f.code,
                    )
                )
        self.publish_diagnostics(uri, diags, version=state.analyzed_version)

    def refresh_tokens(self) -> None:
        caps = self.client_capabilities.workspace
        if caps and caps.semantic_tokens and caps.semantic_tokens.refresh_support:
            self.lsp.send_request(types.WORKSPACE_SEMANTIC_TOKENS_REFRESH)


server = EnglishServer()


@server.feature(types.INITIALIZE)
def on_initialize(ls: EnglishServer, params: types.InitializeParams) -> None:
    opts = params.initialization_options or {}
    ls.options = dict(opts)
    if opts.get("view") in VIEWS:
        ls.view = opts["view"]
    ls.style_checks = bool(opts.get("styleChecks", True))


@server.feature(types.INITIALIZED)
async def on_initialized(ls: EnglishServer, params: types.InitializedParams) -> None:
    asyncio.ensure_future(ls.load())


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: EnglishServer, params: types.DidOpenTextDocumentParams) -> None:
    doc = params.text_document
    ls.docs[doc.uri] = DocState(language_id=doc.language_id, version=doc.version)
    ls.schedule(doc.uri, delay=0)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: EnglishServer, params: types.DidChangeTextDocumentParams) -> None:
    state = ls.docs.get(params.text_document.uri)
    if state:
        state.version = params.text_document.version
        ls.schedule(params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: EnglishServer, params: types.DidCloseTextDocumentParams) -> None:
    state = ls.docs.pop(params.text_document.uri, None)
    if state and state.task:
        state.task.cancel()
    ls.publish_diagnostics(params.text_document.uri, [])


@server.feature(
    types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    types.SemanticTokensLegend(token_types=TOKEN_TYPES, token_modifiers=TOKEN_MODIFIERS),
)
async def semantic_tokens(ls: EnglishServer, params: types.SemanticTokensParams) -> types.SemanticTokens:
    state = await ls.current(params.text_document.uri)
    if state is None:
        return types.SemanticTokens(data=[])
    return types.SemanticTokens(data=encode(state.analysis, state.index, ls.view))


@server.feature(types.TEXT_DOCUMENT_HOVER)
async def hover(ls: EnglishServer, params: types.HoverParams) -> types.Hover | None:
    state = await ls.current(params.text_document.uri)
    if state is None:
        return None
    offset = state.index.offset(params.position)
    words = state.analysis.words
    i = bisect.bisect_right([w.start for w in words], offset) - 1
    if i < 0 or not (words[i].start <= offset < words[i].end):
        return None
    w = words[i]
    return types.Hover(
        contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=w.hover),
        range=state.index.range(w.start, w.end),
    )


@server.feature("english/setView")
def set_view(ls: EnglishServer, params) -> None:
    view = getattr(params, "view", None)
    if view in VIEWS:
        ls.view = view
        ls.refresh_tokens()


@server.feature("english/setStyleChecks")
def set_style_checks(ls: EnglishServer, params) -> None:
    ls.style_checks = bool(getattr(params, "enabled", True))
    for uri, state in ls.docs.items():
        if state.analysis is not None:
            ls.publish(uri, state)


@server.feature("english/spans")
async def spans(ls: EnglishServer, params) -> dict:
    """Multi-word regions (clauses, phrases, entities, roles) for client-side decorations."""
    state = await ls.current(params.uri)
    if state is None:
        return {"version": None, "regions": []}

    def rng(start: int, end: int) -> dict:
        r = state.index.range(start, end)
        return {
            "start": {"line": r.start.line, "character": r.start.character},
            "end": {"line": r.end.line, "character": r.end.character},
        }

    return {
        "version": state.analyzed_version,
        "regions": [
            {"kind": g.kind, "label": g.label, "depth": g.depth, "range": rng(g.start, g.end)}
            for g in state.analysis.regions
        ],
    }
