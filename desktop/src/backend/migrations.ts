import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { LogLevel } from "@prisma/client";
import { resolveDatabaseConfig, resolveMigrationDatabaseUrl } from "./database";
import { logger } from "./logger";
import { writeOperationalLog } from "./operational-log";

const execFileAsync = promisify(execFile);

function prismaCliPath(): string | null {
  const candidates = [
    resolve(process.cwd(), "node_modules", "prisma", "build", "index.js"),
    resolve(dirname(process.execPath), "resources", "app.asar.unpacked", "node_modules", "prisma", "build", "index.js"),
    resolve(dirname(process.execPath), "resources", "app", "node_modules", "prisma", "build", "index.js"),
  ];
  return candidates.find((candidate) => existsSync(candidate)) || null;
}

export async function runAutomaticMigrations(force = false): Promise<{ skipped: boolean; message: string }> {
  const enabled = String(process.env.SANNYSYSTEM_AUTO_MIGRATE ?? "true").toLowerCase();
  if (!force && !["1", "true", "yes", "on"].includes(enabled)) {
    return { skipped: true, message: "Migração automática desativada por SANNYSYSTEM_AUTO_MIGRATE." };
  }

  const cliPath = prismaCliPath();
  if (!cliPath) {
    const message = "Prisma CLI não encontrado; execute npm run db:deploy no ambiente de deploy.";
    logger.warn(message);
    return { skipped: true, message };
  }

  const startedAt = Date.now();
  const config = resolveDatabaseConfig();
  try {
    const runAsNodeEnv = process.versions.electron ? { ELECTRON_RUN_AS_NODE: "1" } : {};
    const result = await execFileAsync(process.execPath, [cliPath, "migrate", "deploy"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        ...runAsNodeEnv,
        DATABASE_URL: resolveMigrationDatabaseUrl(),
      },
      timeout: 120000,
      maxBuffer: 1024 * 1024 * 10,
    });
    await writeOperationalLog({
      level: LogLevel.INFO,
      module: "database",
      message: "Migrations Prisma aplicadas automaticamente.",
      metadata: {
        durationMs: Date.now() - startedAt,
        stdout: result.stdout.slice(-4000),
      },
    });
    return { skipped: false, message: "Migrations aplicadas." };
  } catch (error) {
    await writeOperationalLog({
      level: LogLevel.ERROR,
      module: "database",
      message: "Falha ao aplicar migrations Prisma automaticamente.",
      metadata: {
        durationMs: Date.now() - startedAt,
        error: error instanceof Error ? error.message : String(error),
      },
    });
    throw error;
  }
}
