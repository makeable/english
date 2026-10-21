import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient, LanguageClientOptions, ServerOptions, TransportKind } from "vscode-languageclient/node";
import { CLAUSE_TINT, ENTITY_BORDER, ROLE_UNDERLINE, TOKEN_COLORS } from "./colors";

type View = "all" | "pos" | "roles" | "entities";

interface Region {
  kind: "clause" | "phrase" | "entity" | "role";
  label: string;
  depth: number;
  range: { start: { line: number; character: number }; end: { line: number; character: number } };
}

const VIEWS: { id: View; label: string; detail: string }[] = [
  { id: "all", label: "All", detail: "Parts of speech + role underlines, clause tints, entity boxes" },
  { id: "pos", label: "Parts of speech", detail: "Nouns, verbs, adjectives..." },
  { id: "roles", label: "Sentence roles", detail: "Subject, predicate, object, complement, adjunct" },
  { id: "entities", label: "Entities", detail: "People, places, organisations, dates, quantities" },
];

const SELECTOR = [
  { scheme: "file", language: "plaintext" },
  { scheme: "file", language: "markdown" },
  { scheme: "untitled", language: "plaintext" },
  { scheme: "untitled", language: "markdown" },
];

let client: LanguageClient | undefined;
let statusItem: vscode.StatusBarItem;
let decorations: Decorations;
let modelName = "loading…";

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusItem.command = "english.switchView";
  context.subscriptions.push(statusItem);

  decorations = new Decorations();
  context.subscriptions.push(decorations);

  context.subscriptions.push(
    vscode.commands.registerCommand("english.switchView", switchView),
    vscode.commands.registerCommand("english.applyRecommendedColors", applyRecommendedColors),
    vscode.commands.registerCommand("english.restartServer", restart),
    vscode.window.onDidChangeActiveTextEditor(() => {
      updateStatus();
      void refreshVisible();
    }),
    vscode.window.onDidChangeVisibleTextEditors(() => void refreshVisible()),
    vscode.workspace.onDidChangeConfiguration(onConfigChange),
  );

  await start(context);
  updateStatus();
}

export async function deactivate(): Promise<void> {
  await client?.stop();
}

function config() {
  return vscode.workspace.getConfiguration("english");
}

function currentView(): View {
  return config().get<View>("view", "all");
}

let extensionContext: vscode.ExtensionContext;

function pythonCommand(context: vscode.ExtensionContext): string {
  const configured = config().get<string>("pythonPath", "").trim();
  if (configured) {
    return configured;
  }
  // Running from the repo: use the server's own virtualenv.
  const repoVenv = path.join(context.extensionPath, "..", "..", "server", ".venv", "bin", "python");
  if (fs.existsSync(repoVenv)) {
    return repoVenv;
  }
  return process.platform === "win32" ? "python" : "python3";
}

async function start(context: vscode.ExtensionContext): Promise<void> {
  extensionContext = context;
  const command = pythonCommand(context);
  const serverOptions: ServerOptions = {
    command,
    args: ["-m", "english_ls"],
    transport: TransportKind.stdio,
  };
  const clientOptions: LanguageClientOptions = {
    documentSelector: SELECTOR,
    initializationOptions: {
      model: config().get("model"),
      view: currentView(),
      styleChecks: config().get("styleChecks"),
      longSentenceWords: config().get("longSentenceWords"),
    },
    outputChannelName: "English Structure Highlighter",
  };
  client = new LanguageClient("english", "English Structure Highlighter", serverOptions, clientOptions);
  client.onNotification("english/analysisReady", (params: { uri: string; version: number }) => {
    for (const editor of vscode.window.visibleTextEditors) {
      if (editor.document.uri.toString() === params.uri) {
        void refreshEditor(editor);
      }
    }
  });
  client.onNotification("english/modelLoaded", (params: { model: string }) => {
    modelName = params.model;
    updateStatus();
  });
  try {
    await client.start();
  } catch (err) {
    void vscode.window.showErrorMessage(
      `English highlighter: couldn't start the language server with '${command}'. ` +
        `Set "english.pythonPath" to a Python that has english-ls installed. (${err})`,
    );
  }
}

async function restart(): Promise<void> {
  modelName = "loading…";
  decorations.clearAll();
  await client?.stop();
  await start(extensionContext);
  updateStatus();
}

function onConfigChange(e: vscode.ConfigurationChangeEvent): void {
  if (!e.affectsConfiguration("english")) {
    return;
  }
  if (
    e.affectsConfiguration("english.pythonPath") ||
    e.affectsConfiguration("english.model") ||
    e.affectsConfiguration("english.longSentenceWords")
  ) {
    void restart();
    return;
  }
  if (e.affectsConfiguration("english.view")) {
    void client?.sendNotification("english/setView", { view: currentView() });
    updateStatus();
  }
  if (e.affectsConfiguration("english.styleChecks")) {
    void client?.sendNotification("english/setStyleChecks", { enabled: config().get("styleChecks") });
  }
  void refreshVisible();
}

async function switchView(): Promise<void> {
  const now = currentView();
  const pick = await vscode.window.showQuickPick(
    VIEWS.map((v) => ({ ...v, description: v.id === now ? "current" : undefined })),
    { placeHolder: "What should the colours show?" },
  );
  if (pick) {
    await config().update("view", pick.id, vscode.ConfigurationTarget.Global);
  }
}

async function applyRecommendedColors(): Promise<void> {
  const editorConfig = vscode.workspace.getConfiguration("editor");
  const existing = editorConfig.get<{ rules?: Record<string, unknown> }>("semanticTokenColorCustomizations") ?? {};
  const updated = { ...existing, rules: { ...(existing.rules ?? {}), ...TOKEN_COLORS } };
  await editorConfig.update("semanticTokenColorCustomizations", updated, vscode.ConfigurationTarget.Global);
  void vscode.window.showInformationMessage("English highlighter: recommended colours added to your user settings.");
}

function updateStatus(): void {
  const editor = vscode.window.activeTextEditor;
  if (!editor || !vscode.languages.match(SELECTOR, editor.document)) {
    statusItem.hide();
    return;
  }
  const view = VIEWS.find((v) => v.id === currentView());
  statusItem.text = `$(symbol-text) ${view?.label ?? "English"}`;
  statusItem.tooltip = `English highlighting (${modelName}). Click to change view.`;
  statusItem.show();
}

async function refreshVisible(): Promise<void> {
  await Promise.all(vscode.window.visibleTextEditors.map(refreshEditor));
}

async function refreshEditor(editor: vscode.TextEditor): Promise<void> {
  if (!client || !client.isRunning() || !vscode.languages.match(SELECTOR, editor.document)) {
    return;
  }
  const version = editor.document.version;
  let result: { version: number | null; regions: Region[] };
  try {
    result = await client.sendRequest("english/spans", { uri: editor.document.uri.toString() });
  } catch {
    return;
  }
  if (result.version !== version || editor.document.version !== version) {
    return; // stale; a newer analysisReady will follow
  }
  decorations.apply(editor, result.regions, currentView());
}

/** Span-level highlights that semantic tokens can't express (nested or multi-word). */
class Decorations implements vscode.Disposable {
  private clauseByDepth: vscode.TextEditorDecorationType[] = [];
  private entity: vscode.TextEditorDecorationType;
  private roles = new Map<string, vscode.TextEditorDecorationType>();

  constructor() {
    for (let depth = 0; depth < 4; depth++) {
      this.clauseByDepth.push(
        vscode.window.createTextEditorDecorationType({ backgroundColor: CLAUSE_TINT, borderRadius: "2px" }),
      );
    }
    this.entity = vscode.window.createTextEditorDecorationType({
      border: `1px solid ${ENTITY_BORDER}`,
      borderRadius: "3px",
    });
    for (const [role, color] of Object.entries(ROLE_UNDERLINE)) {
      this.roles.set(
        role,
        vscode.window.createTextEditorDecorationType({
          borderStyle: "solid",
          borderColor: color,
          borderWidth: "0 0 2px 0",
        }),
      );
    }
  }

  private all(): vscode.TextEditorDecorationType[] {
    return [...this.clauseByDepth, this.entity, ...this.roles.values()];
  }

  apply(editor: vscode.TextEditor, regions: Region[], view: View): void {
    const cfg = config();
    const showClauses = cfg.get("decorations.clauses", true) && (view === "all" || view === "roles");
    const showEntities = cfg.get("decorations.entities", true) && (view === "all" || view === "entities");
    const showRoles = cfg.get("decorations.roleUnderlines", true) && view === "all";

    const toRange = (r: Region) =>
      new vscode.Range(r.range.start.line, r.range.start.character, r.range.end.line, r.range.end.character);

    const clauses: vscode.DecorationOptions[][] = this.clauseByDepth.map(() => []);
    const entities: vscode.DecorationOptions[] = [];
    const roles = new Map<string, vscode.DecorationOptions[]>();

    for (const r of regions) {
      if (r.kind === "clause" && showClauses) {
        const d = Math.min(Math.max(r.depth - 1, 0), clauses.length - 1);
        clauses[d].push({ range: toRange(r), hoverMessage: `*${r.label}*` });
      } else if (r.kind === "entity" && showEntities) {
        entities.push({ range: toRange(r), hoverMessage: `entity: **${r.label}**` });
      } else if (r.kind === "role" && showRoles && this.roles.has(r.label)) {
        const list = roles.get(r.label) ?? [];
        list.push({ range: toRange(r) });
        roles.set(r.label, list);
      }
    }

    this.clauseByDepth.forEach((type, i) => editor.setDecorations(type, clauses[i]));
    editor.setDecorations(this.entity, entities);
    for (const [role, type] of this.roles) {
      editor.setDecorations(type, roles.get(role) ?? []);
    }
  }

  clearAll(): void {
    for (const editor of vscode.window.visibleTextEditors) {
      for (const type of this.all()) {
        editor.setDecorations(type, []);
      }
    }
  }

  dispose(): void {
    this.all().forEach((t) => t.dispose());
  }
}
