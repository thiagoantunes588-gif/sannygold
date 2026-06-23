import { cp, mkdir, readdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, "..");
const sourceDir = resolve(root, "src", "renderer");
const targetDir = resolve(root, "dist", "renderer");

await mkdir(targetDir, { recursive: true });

for (const entry of await readdir(targetDir, { withFileTypes: true }).catch(() => [])) {
  if (!entry.isFile()) continue;
  if (!/\.(html|css|png|jpg|jpeg|webp|svg)$/i.test(entry.name)) continue;
  await rm(resolve(targetDir, entry.name), { force: true });
}

for (const entry of await readdir(sourceDir, { withFileTypes: true })) {
  if (!entry.isFile()) continue;
  if (!/\.(html|css|png|jpg|jpeg|webp|svg)$/i.test(entry.name)) continue;
  await cp(resolve(sourceDir, entry.name), resolve(targetDir, entry.name));
}
