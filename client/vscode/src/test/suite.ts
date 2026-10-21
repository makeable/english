import * as assert from "assert";
import * as path from "path";
import * as vscode from "vscode";

async function waitFor<T>(fn: () => Thenable<T | undefined>, timeoutMs: number): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await fn();
    if (value !== undefined) {
      return value;
    }
    if (Date.now() > deadline) {
      throw new Error("timed out");
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

async function smokeTest(): Promise<void> {
  const folder = vscode.workspace.workspaceFolders![0].uri.fsPath;
  const uri = vscode.Uri.file(path.join(folder, "sample.md"));
  const doc = await vscode.workspace.openTextDocument(uri);
  await vscode.window.showTextDocument(doc);

  const legend = await waitFor(
    () => vscode.commands.executeCommand<vscode.SemanticTokensLegend>("vscode.provideDocumentSemanticTokensLegend", uri),
    30000,
  );
  assert.ok(legend.tokenTypes.includes("noun"), "legend has noun");

  const tokens = await waitFor(async () => {
    const t = await vscode.commands.executeCommand<vscode.SemanticTokens>("vscode.provideDocumentSemanticTokens", uri);
    return t && t.data.length > 0 ? t : undefined;
  }, 60000);

  // Decode and look for "Lovelace" as a proper noun.
  const lines = doc.getText().split("\n");
  let line = 0;
  let col = 0;
  const found: string[] = [];
  for (let i = 0; i < tokens.data.length; i += 5) {
    const [dl, dc, len, type] = tokens.data.slice(i, i + 5);
    line += dl;
    col = dl ? dc : col + dc;
    found.push(`${lines[line].slice(col, col + len)}:${legend.tokenTypes[type]}`);
  }
  assert.ok(found.includes("Lovelace:properNoun"), "Lovelace is a proper noun");
  assert.ok(found.includes("wrote:verb"), "wrote is a verb");
  assert.ok(!found.some((f) => f.startsWith("print")), "code block skipped");

  const diags = await waitFor(async () => {
    const d = vscode.languages.getDiagnostics(uri).filter((x) => x.source === "english");
    return d.length ? d : undefined;
  }, 30000);
  const codes = new Set(diags.map((d) => String(typeof d.code === "object" ? d.code.value : d.code)));
  for (const code of ["passive", "filler", "repeated-word", "long-sentence"]) {
    assert.ok(codes.has(code), `diagnostic ${code}`);
  }
  console.log(`smoke test OK: ${found.length} tokens, ${diags.length} style hints`);
}

export function run(): Promise<void> {
  return smokeTest();
}
