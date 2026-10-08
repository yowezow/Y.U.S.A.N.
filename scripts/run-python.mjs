import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const script = process.argv[2];
if (!script) throw new Error("Provide a Python script path.");

const candidates = [
  process.env.YUSAN_PYTHON,
  resolve(root, ".venv", "bin", "python"),
  resolve(root, ".venv", "Scripts", "python.exe"),
  process.platform === "win32" ? "python" : "python3"
].filter(Boolean);
const python = candidates.find(candidate => candidate === "python" || candidate === "python3" || existsSync(candidate));
const result = spawnSync(python, [resolve(root, script), ...process.argv.slice(3)], { cwd: root, stdio: "inherit" });
process.exit(result.status ?? 1);
