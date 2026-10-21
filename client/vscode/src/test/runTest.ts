import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { runTests } from "@vscode/test-electron";

// Uses an installed VS Code if one is found (VSCODE_EXECUTABLE overrides);
// otherwise @vscode/test-electron downloads one.
function findVSCode(): string | undefined {
  const candidates = [
    process.env.VSCODE_EXECUTABLE,
    "/Applications/Visual Studio Code.app/Contents/MacOS/Code",
  ];
  return candidates.find((p) => p && fs.existsSync(p));
}

async function main(): Promise<void> {
  const extensionDevelopmentPath = path.resolve(__dirname, "../..");
  const extensionTestsPath = path.resolve(__dirname, "./suite");
  const samples = path.resolve(extensionDevelopmentPath, "../../samples");
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "english-ls-test-"));
  await runTests({
    vscodeExecutablePath: findVSCode(),
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: [
      samples,
      "--disable-extensions",
      "--user-data-dir",
      path.join(scratch, "user-data"),
      "--extensions-dir",
      path.join(scratch, "extensions"),
    ],
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
