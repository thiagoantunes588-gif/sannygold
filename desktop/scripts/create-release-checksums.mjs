import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const releaseDir = resolve(root, "release");

function sha256(filePath) {
  return new Promise((resolveHash, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolveHash(hash.digest("hex")));
  });
}

const entries = await readdir(releaseDir, { withFileTypes: true }).catch(() => []);
const artifacts = entries
  .filter((entry) => entry.isFile())
  .map((entry) => entry.name)
  .filter((name) => /\.(exe|dmg|blockmap|yml|yaml|zip)$/i.test(name))
  .sort();

const lines = [];
for (const artifact of artifacts) {
  const filePath = resolve(releaseDir, artifact);
  lines.push(`${await sha256(filePath)}  release/${artifact}`);
}

await writeFile(resolve(releaseDir, "CHECKSUMS-SHA256.txt"), `${lines.join("\n")}\n`);
console.log(`Checksums gerados para ${artifacts.length} artefatos.`);
