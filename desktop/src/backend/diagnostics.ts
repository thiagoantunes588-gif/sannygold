import { execFileSync } from "node:child_process";
import { platform, release } from "node:os";
import { resolveDatabaseConfig, sanitizedDatabaseConfig } from "./database";
import { validateRuntimeLayout } from "./paths";

export type StartupMode = {
  safeMode: boolean;
  recoveryMode: boolean;
};

function commandAvailable(command: string, args: string[]): boolean {
  try {
    execFileSync(command, args, { stdio: "ignore", timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

export function buildStartupDiagnostics(mode: StartupMode): Record<string, unknown> {
  const setup = validateRuntimeLayout();
  let database: Record<string, unknown>;

  try {
    database = {
      configured: true,
      ...sanitizedDatabaseConfig(),
    };
    resolveDatabaseConfig();
  } catch (error) {
    database = {
      configured: false,
      message: error instanceof Error ? error.message : String(error),
    };
  }

  const pgDumpCommand = process.env.SANNYSYSTEM_PG_DUMP_PATH?.trim() || "pg_dump";

  return {
    generatedAt: new Date().toISOString(),
    app: {
      name: "SannySystem",
      platform: platform(),
      osRelease: release(),
      node: process.versions.node,
      electron: process.versions.electron,
    },
    mode,
    setup,
    database,
    dependencies: {
      pgDump: {
        command: pgDumpCommand,
        available: commandAvailable(pgDumpCommand, ["--version"]),
        requiredFor: "Backup PostgreSQL automatico.",
      },
    },
    updates: {
      configured: Boolean(process.env.SANNYSYSTEM_UPDATE_URL?.trim()),
      feedUrl: process.env.SANNYSYSTEM_UPDATE_URL?.trim() || "electron-builder publish.generic",
      disabledInSafeMode: mode.safeMode,
    },
  };
}
