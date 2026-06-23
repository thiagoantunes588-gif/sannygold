import dotenv from "dotenv";
import { existsSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join, resolve } from "node:path";

let loaded = false;

function localStateDir(): string {
  const home = homedir();
  if (platform() === "win32") {
    return join(process.env.APPDATA || join(home, "AppData", "Roaming"), "SannySystem");
  }
  if (platform() === "darwin") {
    return join(home, "Library", "Application Support", "SannySystem");
  }
  return join(process.env.XDG_DATA_HOME || join(home, ".local", "share"), "SannySystem");
}

export function loadEnvironment(): void {
  if (loaded) return;
  loaded = true;

  const explicit = process.env.SANNYSYSTEM_ENV_FILE ? [resolve(process.env.SANNYSYSTEM_ENV_FILE)] : [];
  const candidates = [
    ...explicit,
    resolve(process.cwd(), ".env.local"),
    resolve(process.cwd(), ".env"),
    join(localStateDir(), "config", ".env"),
    join(localStateDir(), ".env"),
  ];

  for (const path of candidates) {
    if (existsSync(path)) {
      dotenv.config({ path, override: false });
    }
  }
}
