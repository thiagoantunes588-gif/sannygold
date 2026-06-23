import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, parse, resolve, sep } from "node:path";
import { randomUUID } from "node:crypto";
import { hostname, homedir, platform } from "node:os";
import { loadEnvironment } from "./env";

loadEnvironment();

type DropboxInfo = {
  personal?: { path?: string };
  business?: { path?: string };
};

export type RuntimeDirectories = {
  logsDir: string;
  backupsDir: string;
  tempDir: string;
  exportsDir: string;
  uploadsDir: string;
  databaseDir: string;
  configDir: string;
  syncDir: string;
  snapshotsDir: string;
  conflictsDir: string;
  updatesDir: string;
  localCacheDir: string;
};

export type RuntimeLayout = {
  appInstallDir: string;
  stateDir: string;
  dataDir: string;
  dropboxRoot: string | null;
  usingDropbox: boolean;
  workstationIdPath: string;
  directories: RuntimeDirectories;
};

export type RuntimeIssue = {
  level: "error" | "warning";
  code: string;
  message: string;
  path?: string;
};

export type RuntimeValidation = {
  ready: boolean;
  layout: RuntimeLayout;
  issues: RuntimeIssue[];
};

const DATA_FOLDER_NAME = "SannySystemData";
const RUNTIME_MANIFEST_NAME = "runtime.json";
const REQUIRED_DATA_DIRS = [
  "logs",
  "backups",
  "temp",
  "exports",
  "uploads",
  "database",
  "config",
  "sync",
  join("sync", "snapshots"),
  "conflicts",
  "updates",
];
const PROHIBITED_DIR_NAMES = new Set([
  "node_modules",
  ".git",
  ".cache",
  "cache",
  "dist",
  "release",
  "build",
  ".next",
  "out",
  ".venv",
  "venv",
  "__pycache__",
]);
const PROHIBITED_FILE_EXTENSIONS = new Set([
  ".app",
  ".bat",
  ".cmd",
  ".com",
  ".db",
  ".dmg",
  ".dll",
  ".exe",
  ".msi",
  ".pkg",
  ".ps1",
  ".command",
  ".sh",
  ".sqlite",
  ".sqlite3",
]);

function readDropboxInfo(filePath: string): string[] {
  if (!existsSync(filePath)) return [];
  try {
    const parsed = JSON.parse(readFileSync(filePath, "utf-8")) as DropboxInfo;
    return [parsed.personal?.path, parsed.business?.path].filter((item): item is string => Boolean(item));
  } catch {
    return [];
  }
}

function isInsidePath(childPath: string, parentPath: string): boolean {
  const child = resolve(childPath);
  const parent = resolve(parentPath);
  return child === parent || child.startsWith(`${parent}${sep}`);
}

function safeWriteJson(filePath: string, payload: unknown): void {
  mkdirSync(dirname(filePath), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`);
}

export function resolveAppInstallDir(): string {
  if (process.env.SANNYSYSTEM_APP_DIR) return resolve(process.env.SANNYSYSTEM_APP_DIR);

  const execPath = resolve(process.execPath);
  if (platform() === "darwin") {
    const appIndex = execPath.indexOf(".app/Contents/MacOS");
    if (appIndex >= 0) return execPath.slice(0, appIndex + ".app".length);
  }

  return dirname(execPath);
}

export function resolveLocalStateDir(): string {
  if (process.env.SANNYSYSTEM_HOME) return resolve(process.env.SANNYSYSTEM_HOME);

  const home = homedir();
  if (platform() === "win32") {
    return join(process.env.APPDATA || join(home, "AppData", "Roaming"), "SannySystem");
  }
  if (platform() === "darwin") {
    return join(home, "Library", "Application Support", "SannySystem");
  }
  return join(process.env.XDG_DATA_HOME || join(home, ".local", "share"), "SannySystem");
}

export function detectDropboxRoot(): string | null {
  if (process.env.SANNYSYSTEM_DROPBOX_ROOT && existsSync(process.env.SANNYSYSTEM_DROPBOX_ROOT)) {
    return resolve(process.env.SANNYSYSTEM_DROPBOX_ROOT);
  }

  const home = homedir();
  const infoFiles =
    platform() === "win32"
      ? [
          join(process.env.LOCALAPPDATA || "", "Dropbox", "info.json"),
          join(process.env.APPDATA || "", "Dropbox", "info.json"),
        ]
      : [join(home, ".dropbox", "info.json")];

  for (const infoFile of infoFiles) {
    for (const candidate of readDropboxInfo(infoFile)) {
      if (existsSync(candidate)) return resolve(candidate);
    }
  }

  const commonCandidates =
    platform() === "win32"
      ? [join(home, "Dropbox"), join(home, "Dropbox (SannyGold)")]
      : [join(home, "Dropbox"), join(home, "Library", "CloudStorage", "Dropbox")];

  return commonCandidates.find((candidate) => existsSync(candidate)) || null;
}

export function resolveDataSyncDir(): string {
  if (process.env.SANNYSYSTEM_DATA_DIR) return resolve(process.env.SANNYSYSTEM_DATA_DIR);

  const dropboxRoot = detectDropboxRoot();
  if (dropboxRoot) return join(dropboxRoot, DATA_FOLDER_NAME);

  return join(resolveLocalStateDir(), DATA_FOLDER_NAME);
}

export function buildRuntimeLayout(): RuntimeLayout {
  const stateDir = resolveLocalStateDir();
  const dataDir = resolveDataSyncDir();
  const dropboxRoot = detectDropboxRoot();
  const directories: RuntimeDirectories = {
    logsDir: join(dataDir, "logs"),
    backupsDir: join(dataDir, "backups"),
    tempDir: join(dataDir, "temp"),
    exportsDir: join(dataDir, "exports"),
    uploadsDir: join(dataDir, "uploads"),
    databaseDir: join(dataDir, "database"),
    configDir: join(dataDir, "config"),
    syncDir: join(dataDir, "sync"),
    snapshotsDir: join(dataDir, "sync", "snapshots"),
    conflictsDir: join(dataDir, "conflicts"),
    updatesDir: join(dataDir, "updates"),
    localCacheDir: join(stateDir, "cache"),
  };

  return {
    appInstallDir: resolveAppInstallDir(),
    stateDir,
    dataDir,
    dropboxRoot,
    usingDropbox: Boolean(dropboxRoot && isInsidePath(dataDir, dropboxRoot)),
    workstationIdPath: join(stateDir, "workstation.json"),
    directories,
  };
}

function ensureDataPolicyFiles(layout: RuntimeLayout): void {
  safeWriteJson(join(layout.directories.configDir, RUNTIME_MANIFEST_NAME), {
    schemaVersion: 1,
    app: "SannySystem",
    platform: platform(),
    hostname: hostname(),
    appInstallDir: layout.appInstallDir,
    dataDir: layout.dataDir,
    stateDir: layout.stateDir,
    dropboxRoot: layout.dropboxRoot,
    usingDropbox: layout.usingDropbox,
    updatedAt: new Date().toISOString(),
    policy: {
      application: "Instalada localmente. Nunca sincronizar node_modules, release, dist ou executaveis pelo Dropbox.",
      database: "PostgreSQL e o unico banco ativo. SQLite fisico nao deve existir em SannySystemData.",
      cache: "Cache tecnico fica fora do Dropbox em stateDir/cache.",
    },
  });
  writeFileSync(
    join(layout.directories.databaseDir, "README-NO-SQLITE.txt"),
    [
      "Esta pasta existe apenas para metadados, manifests e relatórios de banco.",
      "Nao salve arquivos .db, .sqlite ou .sqlite3 aqui.",
      "O banco ativo do SannySystem e PostgreSQL, configurado por DATABASE_URL.",
      "",
    ].join("\n"),
  );
}

function testWritable(dir: string): RuntimeIssue | null {
  const probePath = join(dir, `.sannysystem-write-test-${randomUUID()}.tmp`);
  try {
    writeFileSync(probePath, "ok");
    rmSync(probePath, { force: true });
    return null;
  } catch (error) {
    return {
      level: "error",
      code: "directory_not_writable",
      path: dir,
      message: `A pasta nao permite escrita: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

function scanProhibitedContent(rootDir: string): RuntimeIssue[] {
  if (!existsSync(rootDir)) return [];
  const issues: RuntimeIssue[] = [];
  const queue: Array<{ path: string; depth: number }> = [{ path: rootDir, depth: 0 }];
  let visited = 0;

  while (queue.length && visited < 2500) {
    const current = queue.shift()!;
    visited += 1;
    let entries: string[] = [];
    try {
      entries = readdirSync(current.path);
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = join(current.path, entry);
      let stats;
      try {
        stats = statSync(fullPath);
      } catch {
        continue;
      }

      const parsed = parse(entry);
      const lowerName = entry.toLowerCase();
      const lowerExt = parsed.ext.toLowerCase();

      if (stats.isDirectory()) {
        if (PROHIBITED_DIR_NAMES.has(lowerName) || PROHIBITED_FILE_EXTENSIONS.has(lowerExt)) {
          issues.push({
            level: "error",
            code: "prohibited_directory_in_dropbox_data",
            path: fullPath,
            message: "Pasta proibida dentro de SannySystemData.",
          });
        } else if (current.depth < 5) {
          queue.push({ path: fullPath, depth: current.depth + 1 });
        }
        continue;
      }

      if (PROHIBITED_FILE_EXTENSIONS.has(lowerExt)) {
        issues.push({
          level: "error",
          code: "prohibited_file_in_dropbox_data",
          path: fullPath,
          message: "Arquivo proibido dentro de SannySystemData.",
        });
      }
    }
  }

  if (visited >= 2500) {
    issues.push({
      level: "warning",
      code: "prohibited_scan_limited",
      path: rootDir,
      message: "A verificacao de conteudo proibido parou no limite de 2500 itens.",
    });
  }

  return issues;
}

export function ensureRuntimeFolders(): RuntimeLayout {
  const layout = buildRuntimeLayout();
  mkdirSync(layout.stateDir, { recursive: true });
  mkdirSync(layout.directories.localCacheDir, { recursive: true });
  for (const relativeDir of REQUIRED_DATA_DIRS) {
    mkdirSync(join(layout.dataDir, relativeDir), { recursive: true });
  }
  ensureDataPolicyFiles(layout);
  return layout;
}

export function validateRuntimeLayout(): RuntimeValidation {
  const layout = ensureRuntimeFolders();
  const issues: RuntimeIssue[] = [];

  if (!layout.dropboxRoot) {
    issues.push({
      level: "warning",
      code: "dropbox_not_detected",
      message: "Dropbox nao foi detectado. A aplicacao usara pasta local de contingencia ate o Dropbox estar disponivel.",
      path: layout.dataDir,
    });
  }

  if (isInsidePath(layout.dataDir, layout.appInstallDir)) {
    issues.push({
      level: "error",
      code: "data_inside_application",
      message: "A pasta de dados nao pode ficar dentro da pasta de instalacao da aplicacao.",
      path: layout.dataDir,
    });
  }

  if (layout.dropboxRoot && !isInsidePath(layout.dataDir, layout.dropboxRoot)) {
    issues.push({
      level: "warning",
      code: "data_outside_dropbox",
      message: "Dropbox foi detectado, mas SANNYSYSTEM_DATA_DIR aponta para fora dele.",
      path: layout.dataDir,
    });
  }

  for (const dir of [
    layout.dataDir,
    layout.directories.logsDir,
    layout.directories.backupsDir,
    layout.directories.tempDir,
    layout.directories.exportsDir,
    layout.directories.uploadsDir,
    layout.directories.databaseDir,
    layout.directories.configDir,
  ]) {
    const issue = testWritable(dir);
    if (issue) issues.push(issue);
  }

  issues.push(...scanProhibitedContent(layout.dataDir));

  return {
    ready: !issues.some((issue) => issue.level === "error"),
    layout,
    issues,
  };
}

export function getWorkstationId(): string {
  const layout = ensureRuntimeFolders();
  const identityPath = layout.workstationIdPath;
  if (existsSync(identityPath)) {
    try {
      const parsed = JSON.parse(readFileSync(identityPath, "utf-8")) as { id?: string };
      if (parsed.id) return parsed.id;
    } catch {
      // Recria identidade corrompida.
    }
  }
  const id = randomUUID();
  safeWriteJson(identityPath, { id, hostname: hostname(), platform: platform(), createdAt: new Date().toISOString() });
  return id;
}
