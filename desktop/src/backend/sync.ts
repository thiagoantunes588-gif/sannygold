import { AuditAction, ConflictStatus, Prisma, PrismaClient, SyncDirection, SyncStatus } from "@prisma/client";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { hostname, platform } from "node:os";
import { basename, join } from "node:path";
import { ensureRuntimeFolders, getWorkstationId } from "./paths";
import { prisma } from "./prisma";
import { writeAudit } from "./audit";
import { logger } from "./logger";

type SyncEntity = "client" | "event" | "equipment" | "vehicle" | "financialEntry" | "serviceOrder" | "genericRecord";

type SnapshotRecord = {
  entity: SyncEntity;
  id: string;
  updatedAt: string;
  checksum: string;
  payload: Record<string, unknown>;
};

type SnapshotFile = {
  schemaVersion: 1;
  snapshotId: string;
  workstationId: string;
  hostname: string;
  platform: string;
  exportedAt: string;
  records: SnapshotRecord[];
};

const entityConfigs: Record<
  SyncEntity,
  {
    delegate: keyof PrismaClient;
    dateFields: string[];
  }
> = {
  client: { delegate: "client", dateFields: ["createdAt", "updatedAt", "deletedAt"] },
  event: { delegate: "event", dateFields: ["eventDate", "createdAt", "updatedAt", "deletedAt"] },
  equipment: { delegate: "equipment", dateFields: ["createdAt", "updatedAt", "deletedAt"] },
  vehicle: { delegate: "vehicle", dateFields: ["createdAt", "updatedAt", "deletedAt"] },
  financialEntry: { delegate: "financialEntry", dateFields: ["entryDate", "createdAt", "updatedAt", "deletedAt"] },
  serviceOrder: { delegate: "serviceOrder", dateFields: ["scheduledAt", "createdAt", "updatedAt", "deletedAt"] },
  genericRecord: { delegate: "genericRecord", dateFields: ["createdAt", "updatedAt", "deletedAt"] },
};

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    const input = value as Record<string, unknown>;
    return Object.keys(input)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = stableValue(input[key]);
        return acc;
      }, {});
  }
  return value;
}

function checksum(payload: unknown): string {
  return createHash("sha256").update(JSON.stringify(stableValue(payload))).digest("hex");
}

function jsonInput(value: unknown): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(value)) as Prisma.InputJsonValue;
}

function normalizeRecord(record: unknown): Record<string, unknown> {
  return JSON.parse(JSON.stringify(record)) as Record<string, unknown>;
}

function delegateFor(entity: SyncEntity): any {
  return (prisma as any)[entityConfigs[entity].delegate];
}

function rehydrateDates(entity: SyncEntity, payload: Record<string, unknown>): Record<string, unknown> {
  const data = { ...payload };
  for (const field of entityConfigs[entity].dateFields) {
    if (typeof data[field] === "string" && data[field]) data[field] = new Date(data[field] as string);
    if (data[field] === null) data[field] = null;
  }
  return data;
}

async function collectRecords(entity: SyncEntity): Promise<SnapshotRecord[]> {
  const delegate = delegateFor(entity);
  const records = (await delegate.findMany({ orderBy: { updatedAt: "asc" } })) as Record<string, unknown>[];
  return records.map((record) => {
    const payload = normalizeRecord(record);
    return {
      entity,
      id: String(payload.id),
      updatedAt: String(payload.updatedAt),
      checksum: checksum(payload),
      payload,
    };
  });
}

export async function registerWorkstation(): Promise<void> {
  const { dataDir } = ensureRuntimeFolders();
  await prisma.workstation.upsert({
    where: { id: getWorkstationId() },
    create: {
      id: getWorkstationId(),
      hostname: hostname(),
      platform: platform(),
      dataDir,
      lastSeenAt: new Date(),
    },
    update: {
      hostname: hostname(),
      platform: platform(),
      dataDir,
      lastSeenAt: new Date(),
    },
  });
}

export async function exportSnapshot(userId?: string): Promise<{ filePath: string; recordCount: number; checksum: string }> {
  const { directories } = ensureRuntimeFolders();
  const { snapshotsDir, tempDir } = directories;
  const workstationId = getWorkstationId();
  await registerWorkstation();

  const records = (
    await Promise.all((Object.keys(entityConfigs) as SyncEntity[]).map((entity) => collectRecords(entity)))
  ).flat();

  const snapshot: SnapshotFile = {
    schemaVersion: 1,
    snapshotId: randomUUID(),
    workstationId,
    hostname: hostname(),
    platform: platform(),
    exportedAt: new Date().toISOString(),
    records,
  };
  const serialized = JSON.stringify(snapshot, null, 2);
  const fileChecksum = checksum(snapshot);
  const fileName = `${workstationId}-${snapshot.exportedAt.replace(/[:.]/g, "-")}.json`;
  const tempPath = join(tempDir, `${fileName}.tmp`);
  const finalPath = join(snapshotsDir, fileName);

  writeFileSync(tempPath, serialized);
  renameSync(tempPath, finalPath);

  await prisma.syncSnapshot.create({
    data: {
      workstationId,
      direction: SyncDirection.EXPORT,
      status: SyncStatus.DONE,
      fileName,
      filePath: finalPath,
      checksum: fileChecksum,
      recordCount: records.length,
      completedAt: new Date(),
    },
  });

  const user = userId ? await prisma.user.findUnique({ where: { id: userId } }) : null;
  await writeAudit({
    user,
    action: AuditAction.SYNC_EXPORT,
    module: "sync",
    targetId: fileName,
    after: { filePath: finalPath, recordCount: records.length, checksum: fileChecksum },
  });

  return { filePath: finalPath, recordCount: records.length, checksum: fileChecksum };
}

async function createConflict(record: SnapshotRecord, snapshot: SnapshotFile, localPayload: Record<string, unknown>): Promise<void> {
  await prisma.syncConflict.create({
    data: {
      entity: record.entity,
      recordId: record.id,
      sourceWorkstationId: snapshot.workstationId,
      localChecksum: checksum(localPayload),
      remoteChecksum: record.checksum,
      localPayload: jsonInput(localPayload),
      remotePayload: jsonInput(record.payload),
    },
  });
}

async function applyRemoteRecord(record: SnapshotRecord, snapshot: SnapshotFile): Promise<void> {
  const delegate = delegateFor(record.entity);
  const data = rehydrateDates(record.entity, record.payload);

  await delegate.upsert({
    where: { id: record.id },
    create: data,
    update: data,
  });

  await prisma.syncCursor.upsert({
    where: {
      sourceWorkstationId_entity_recordId: {
        sourceWorkstationId: snapshot.workstationId,
        entity: record.entity,
        recordId: record.id,
      },
    },
    create: {
      sourceWorkstationId: snapshot.workstationId,
      entity: record.entity,
      recordId: record.id,
      remoteChecksum: record.checksum,
      remoteUpdatedAt: new Date(record.updatedAt),
    },
    update: {
      remoteChecksum: record.checksum,
      remoteUpdatedAt: new Date(record.updatedAt),
      appliedAt: new Date(),
    },
  });
}

export async function importSnapshots(userId?: string): Promise<{ imported: number; conflicts: number; files: number }> {
  const { directories } = ensureRuntimeFolders();
  const { snapshotsDir } = directories;
  const workstationId = getWorkstationId();
  if (!existsSync(snapshotsDir)) return { imported: 0, conflicts: 0, files: 0 };

  let imported = 0;
  let conflicts = 0;
  let files = 0;

  for (const fileName of readdirSync(snapshotsDir).filter((file) => file.endsWith(".json")).sort()) {
    const filePath = join(snapshotsDir, fileName);
    let snapshot: SnapshotFile;
    try {
      snapshot = JSON.parse(readFileSync(filePath, "utf-8")) as SnapshotFile;
    } catch (error) {
      logger.warn("Snapshot ignorado por JSON inválido", { filePath, error });
      continue;
    }
    if (snapshot.workstationId === workstationId || snapshot.schemaVersion !== 1) continue;

    files += 1;
    for (const record of snapshot.records) {
      const delegate = delegateFor(record.entity);
      const local = (await delegate.findUnique({ where: { id: record.id } })) as Record<string, unknown> | null;
      const cursor = await prisma.syncCursor.findUnique({
        where: {
          sourceWorkstationId_entity_recordId: {
            sourceWorkstationId: snapshot.workstationId,
            entity: record.entity,
            recordId: record.id,
          },
        },
      });

      if (local) {
        const localPayload = normalizeRecord(local);
        const localChecksum = checksum(localPayload);
        const localUpdatedAt = new Date(String(localPayload.updatedAt));
        const changedAfterLastApply = cursor ? localUpdatedAt > cursor.appliedAt : localChecksum !== record.checksum;
        if (localChecksum !== record.checksum && changedAfterLastApply) {
          const existingConflict = await prisma.syncConflict.findFirst({
            where: {
              entity: record.entity,
              recordId: record.id,
              sourceWorkstationId: snapshot.workstationId,
              remoteChecksum: record.checksum,
              status: ConflictStatus.OPEN,
            },
          });
          if (!existingConflict) {
            await createConflict(record, snapshot, localPayload);
            conflicts += 1;
          }
          continue;
        }
      }

      await applyRemoteRecord(record, snapshot);
      imported += 1;
    }

    await prisma.syncSnapshot.create({
      data: {
        workstationId: snapshot.workstationId,
        direction: SyncDirection.IMPORT,
        status: conflicts ? SyncStatus.WARNING : SyncStatus.DONE,
        fileName: basename(filePath),
        filePath,
        checksum: checksum(snapshot),
        recordCount: snapshot.records.length,
        completedAt: new Date(),
        message: conflicts ? "Importação concluída com conflitos pendentes." : undefined,
      },
    });
  }

  const user = userId ? await prisma.user.findUnique({ where: { id: userId } }) : null;
  await writeAudit({
    user,
    action: conflicts ? AuditAction.SYNC_CONFLICT : AuditAction.SYNC_IMPORT,
    module: "sync",
    after: { imported, conflicts, files },
  });

  return { imported, conflicts, files };
}

export async function syncStatus(): Promise<Record<string, unknown>> {
  const layout = ensureRuntimeFolders();
  const [lastSnapshot, openConflicts, workstations] = await Promise.all([
    prisma.syncSnapshot.findFirst({ orderBy: { createdAt: "desc" } }),
    prisma.syncConflict.count({ where: { status: ConflictStatus.OPEN } }),
    prisma.workstation.findMany({ orderBy: { lastSeenAt: "desc" }, take: 10 }),
  ]);

  return {
    workstationId: getWorkstationId(),
    dataDir: layout.dataDir,
    directories: layout.directories,
    snapshotsDir: layout.directories.snapshotsDir,
    logsDir: layout.directories.logsDir,
    lastSnapshot,
    openConflicts,
    workstations,
  };
}

export async function resolveConflict(
  conflictId: string,
  resolution: "accept_local" | "accept_remote" | "ignore",
  userId?: string,
): Promise<void> {
  const conflict = await prisma.syncConflict.findUnique({ where: { id: conflictId } });
  if (!conflict) throw new Error("Conflito não encontrado.");
  if (conflict.status !== ConflictStatus.OPEN) return;

  if (resolution === "accept_remote") {
    await applyRemoteRecord(
      {
        entity: conflict.entity as SyncEntity,
        id: conflict.recordId,
        updatedAt: String((conflict.remotePayload as Record<string, unknown>).updatedAt || new Date().toISOString()),
        checksum: conflict.remoteChecksum,
        payload: conflict.remotePayload as Record<string, unknown>,
      },
      {
        schemaVersion: 1,
        snapshotId: conflict.id,
        workstationId: conflict.sourceWorkstationId,
        hostname: "",
        platform: "",
        exportedAt: new Date().toISOString(),
        records: [],
      },
    );
  }

  const status =
    resolution === "accept_remote"
      ? ConflictStatus.REMOTE_ACCEPTED
      : resolution === "accept_local"
        ? ConflictStatus.LOCAL_ACCEPTED
        : ConflictStatus.IGNORED;

  await prisma.syncConflict.update({
    where: { id: conflictId },
    data: {
      status,
      resolution,
      resolvedById: userId,
      resolvedAt: new Date(),
    },
  });

  const user = userId ? await prisma.user.findUnique({ where: { id: userId } }) : null;
  await writeAudit({
    user,
    action: AuditAction.SYNC_RESOLVE,
    module: "sync",
    targetId: conflictId,
    after: { resolution },
  });
}
