import { BackupProvider, BackupStatus, LogLevel, Prisma } from "@prisma/client";
import { createHash } from "node:crypto";
import { createReadStream, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { execFile, execFileSync } from "node:child_process";
import { promisify } from "node:util";
import { ensureRuntimeFolders } from "./paths";
import { prisma } from "./prisma";
import { resolveDatabaseConfig } from "./database";
import { writeOperationalLog } from "./operational-log";
import { logger } from "./logger";

const execFileAsync = promisify(execFile);

function backupProvider(): BackupProvider {
  const provider = resolveDatabaseConfig().provider;
  if (provider === "supabase") return BackupProvider.SUPABASE;
  if (provider === "neon") return BackupProvider.NEON;
  if (provider === "railway") return BackupProvider.RAILWAY;
  if (provider === "local-postgres") return BackupProvider.LOCAL;
  return BackupProvider.CUSTOM_POSTGRES;
}

function timestampSlug(date = new Date()): string {
  return date.toISOString().replace(/[:.]/g, "-");
}

function sha256File(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

export async function createPostgresBackup(createdById?: string): Promise<Record<string, unknown>> {
  const config = resolveDatabaseConfig();
  const { directories } = ensureRuntimeFolders();
  const retentionDays = Number.parseInt(process.env.SANNYSYSTEM_BACKUP_RETENTION_DAYS || "30", 10);
  const fileName = `postgres-${config.provider}-${timestampSlug()}.dump`;
  const tempPath = join(directories.tempDir, `${fileName}.tmp`);
  const finalPath = join(directories.backupsDir, fileName);

  const run = await prisma.databaseBackup.create({
    data: {
      provider: backupProvider(),
      status: BackupStatus.RUNNING,
      fileName,
      filePath: finalPath,
      databaseHost: config.host,
      databaseName: config.database,
      retentionDays,
      createdById,
    },
  });

  const startedAt = Date.now();
  try {
    await execFileAsync(
      resolvePgDumpCommand(),
      [
        "--dbname",
        config.url,
        "--format",
        "custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        tempPath,
      ],
      {
        timeout: Number.parseInt(process.env.SANNYSYSTEM_BACKUP_TIMEOUT_SECONDS || "300", 10) * 1000,
        maxBuffer: 1024 * 1024 * 20,
      },
    );

    renameSync(tempPath, finalPath);
    const sizeBytes = statSync(finalPath).size;
    const checksum = await sha256File(finalPath);

    await prisma.databaseBackup.update({
      where: { id: run.id },
      data: {
        status: BackupStatus.SUCCESS,
        sizeBytes,
        checksum,
        finishedAt: new Date(),
        message: "Backup PostgreSQL concluído.",
      },
    });
    await writeOperationalLog({
      level: LogLevel.INFO,
      module: "database-backup",
      message: "Backup PostgreSQL concluído.",
      metadata: {
        fileName,
        filePath: finalPath,
        sizeBytes,
        checksum,
        durationMs: Date.now() - startedAt,
      },
    });
    await pruneOldBackups(retentionDays);
    return { id: run.id, status: BackupStatus.SUCCESS, fileName, filePath: finalPath, sizeBytes, checksum };
  } catch (error) {
    rmSync(tempPath, { force: true });
    const message = error instanceof Error ? error.message : String(error);
    await prisma.databaseBackup.update({
      where: { id: run.id },
      data: {
        status: BackupStatus.FAILED,
        finishedAt: new Date(),
        message,
      },
    });
    await writeOperationalLog({
      level: LogLevel.ERROR,
      module: "database-backup",
      message: "Falha no backup PostgreSQL.",
      metadata: {
        fileName,
        durationMs: Date.now() - startedAt,
        error: message,
      } as Prisma.InputJsonValue,
    });
    throw new Error(`Backup PostgreSQL falhou: ${message}`);
  }
}

function resolvePgDumpCommand(): string {
  return process.env.SANNYSYSTEM_PG_DUMP_PATH?.trim() || "pg_dump";
}

function pgDumpAvailable(): boolean {
  try {
    execFileSync(resolvePgDumpCommand(), ["--version"], { stdio: "ignore", timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

export async function pruneOldBackups(retentionDays: number): Promise<void> {
  const { directories } = ensureRuntimeFolders();
  const cutoff = Date.now() - retentionDays * 24 * 60 * 60 * 1000;
  for (const file of readdirSync(directories.backupsDir).filter((item) => item.endsWith(".dump"))) {
    const path = join(directories.backupsDir, file);
    try {
      const stats = statSync(path);
      if (stats.mtimeMs < cutoff) rmSync(path, { force: true });
    } catch {
      // Ignora arquivos removidos por outro processo.
    }
  }
}

function backupTimeParts(): { hour: number; minute: number } {
  const [hourRaw, minuteRaw] = (process.env.SANNYSYSTEM_BACKUP_TIME || "20:00").split(":");
  return {
    hour: Number.parseInt(hourRaw || "20", 10),
    minute: Number.parseInt(minuteRaw || "0", 10),
  };
}

let backupTimer: NodeJS.Timeout | null = null;
let lastAutomaticBackupDate = "";

export function startAutomaticBackupScheduler(): void {
  const enabled = String(process.env.SANNYSYSTEM_BACKUP_ENABLED ?? "true").toLowerCase();
  if (!["1", "true", "yes", "on"].includes(enabled)) {
    logger.info("Backup PostgreSQL automático desativado.");
    return;
  }
  if (backupTimer) return;

  backupTimer = setInterval(() => {
    const now = new Date();
    const { hour, minute } = backupTimeParts();
    const today = now.toISOString().slice(0, 10);
    if (lastAutomaticBackupDate === today) return;
    if (now.getHours() !== hour || now.getMinutes() !== minute) return;
    lastAutomaticBackupDate = today;
    createPostgresBackup().catch((error) => {
      logger.error("Backup PostgreSQL automático falhou", { error });
    });
  }, 60_000);
}

export async function backupStatus(): Promise<Record<string, unknown>> {
  const { directories } = ensureRuntimeFolders();
  const lastBackups = await prisma.databaseBackup.findMany({
    orderBy: { startedAt: "desc" },
    take: 20,
  });
  return {
    enabled: String(process.env.SANNYSYSTEM_BACKUP_ENABLED ?? "true").toLowerCase(),
    time: process.env.SANNYSYSTEM_BACKUP_TIME || "20:00",
    retentionDays: Number.parseInt(process.env.SANNYSYSTEM_BACKUP_RETENTION_DAYS || "30", 10),
    backupDir: directories.backupsDir,
    pgDumpCommand: resolvePgDumpCommand(),
    pgDumpAvailable: pgDumpAvailable(),
    lastBackups,
  };
}
