import * as SQLite from "expo-sqlite";
import type { OfflineQueueItem, ServiceOrder } from "@/types/operation";

let dbPromise: Promise<SQLite.SQLiteDatabase> | null = null;

function db(): Promise<SQLite.SQLiteDatabase> {
  dbPromise ||= SQLite.openDatabaseAsync("sannysystem-mobile.db");
  return dbPromise;
}

function mutationId(): string {
  return `mobile-${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
}

export async function initOfflineStore(): Promise<void> {
  const database = await db();
  await database.execAsync(`
    CREATE TABLE IF NOT EXISTS offline_queue (
      clientMutationId TEXT PRIMARY KEY NOT NULL,
      actionType TEXT NOT NULL,
      entity TEXT NOT NULL,
      entityId TEXT,
      operation TEXT NOT NULL,
      payload TEXT NOT NULL,
      baseVersion INTEGER,
      createdAt TEXT NOT NULL,
      attachments TEXT,
      localStatus TEXT NOT NULL,
      lastError TEXT
    );

    CREATE INDEX IF NOT EXISTS offline_queue_status_idx ON offline_queue(localStatus, createdAt);

    CREATE TABLE IF NOT EXISTS service_orders (
      id TEXT PRIMARY KEY NOT NULL,
      status TEXT NOT NULL,
      version INTEGER NOT NULL DEFAULT 1,
      scheduledAt TEXT,
      updatedAt TEXT,
      payload TEXT,
      cachedAt TEXT NOT NULL
    );
  `);
}

export async function enqueueOfflineAction(
  input: Omit<OfflineQueueItem, "clientMutationId" | "createdAt" | "localStatus"> & {
    clientMutationId?: string;
    createdAt?: string;
  },
): Promise<OfflineQueueItem> {
  await initOfflineStore();
  const item: OfflineQueueItem = {
    ...input,
    clientMutationId: input.clientMutationId || mutationId(),
    createdAt: input.createdAt || new Date().toISOString(),
    localStatus: "pending",
  };
  const database = await db();
  await database.runAsync(
    `INSERT OR REPLACE INTO offline_queue
     (clientMutationId, actionType, entity, entityId, operation, payload, baseVersion, createdAt, attachments, localStatus, lastError)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      item.clientMutationId,
      item.actionType,
      item.entity,
      item.entityId || null,
      item.operation,
      JSON.stringify(item.payload),
      item.baseVersion ?? null,
      item.createdAt,
      item.attachments ? JSON.stringify(item.attachments) : null,
      item.localStatus,
      item.lastError || null,
    ],
  );
  return item;
}

function rowToQueueItem(row: Record<string, unknown>): OfflineQueueItem {
  return {
    clientMutationId: String(row.clientMutationId),
    actionType: row.actionType as OfflineQueueItem["actionType"],
    entity: "serviceOrder",
    entityId: row.entityId ? String(row.entityId) : null,
    operation: String(row.operation),
    payload: JSON.parse(String(row.payload || "{}")) as Record<string, unknown>,
    baseVersion: row.baseVersion === null || row.baseVersion === undefined ? null : Number(row.baseVersion),
    createdAt: String(row.createdAt),
    attachments: row.attachments ? JSON.parse(String(row.attachments)) : undefined,
    localStatus: row.localStatus as OfflineQueueItem["localStatus"],
    lastError: row.lastError ? String(row.lastError) : null,
  };
}

export async function listQueue(): Promise<OfflineQueueItem[]> {
  await initOfflineStore();
  const database = await db();
  const rows = await database.getAllAsync<Record<string, unknown>>(
    "SELECT * FROM offline_queue ORDER BY createdAt DESC LIMIT 200",
  );
  return rows.map(rowToQueueItem);
}

export async function pendingQueue(): Promise<OfflineQueueItem[]> {
  await initOfflineStore();
  const database = await db();
  const rows = await database.getAllAsync<Record<string, unknown>>(
    "SELECT * FROM offline_queue WHERE localStatus IN ('pending', 'failed') ORDER BY createdAt ASC LIMIT 100",
  );
  return rows.map(rowToQueueItem);
}

export async function markQueueStatus(
  ids: string[],
  status: OfflineQueueItem["localStatus"],
  message?: string | null,
): Promise<void> {
  if (!ids.length) return;
  await initOfflineStore();
  const database = await db();
  for (const id of ids) {
    await database.runAsync(
      "UPDATE offline_queue SET localStatus = ?, lastError = ? WHERE clientMutationId = ?",
      [status, message || null, id],
    );
  }
}

export async function cacheServiceOrders(serviceOrders: ServiceOrder[]): Promise<void> {
  await initOfflineStore();
  const database = await db();
  const cachedAt = new Date().toISOString();
  for (const item of serviceOrders) {
    await database.runAsync(
      `INSERT OR REPLACE INTO service_orders
       (id, status, version, scheduledAt, updatedAt, payload, cachedAt)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        item.id,
        item.status || "aberta",
        item.version || 1,
        item.scheduledAt || null,
        item.updatedAt || null,
        item.payload ? JSON.stringify(item.payload) : null,
        cachedAt,
      ],
    );
  }
}

export async function cachedServiceOrders(): Promise<ServiceOrder[]> {
  await initOfflineStore();
  const database = await db();
  const rows = await database.getAllAsync<Record<string, unknown>>(
    "SELECT * FROM service_orders ORDER BY scheduledAt ASC, updatedAt DESC LIMIT 300",
  );
  return rows.map((row) => ({
    id: String(row.id),
    status: String(row.status || "aberta"),
    version: Number(row.version || 1),
    scheduledAt: row.scheduledAt ? String(row.scheduledAt) : null,
    updatedAt: row.updatedAt ? String(row.updatedAt) : null,
    payload: row.payload ? (JSON.parse(String(row.payload)) as ServiceOrder["payload"]) : null,
  }));
}

export async function queueCounts(): Promise<{ pending: number; failed: number; synced: number }> {
  await initOfflineStore();
  const database = await db();
  const rows = await database.getAllAsync<{ localStatus: string; total: number }>(
    "SELECT localStatus, COUNT(*) as total FROM offline_queue GROUP BY localStatus",
  );
  return rows.reduce(
    (acc, row) => {
      if (row.localStatus === "pending") acc.pending = row.total;
      if (row.localStatus === "failed") acc.failed = row.total;
      if (row.localStatus === "synced") acc.synced = row.total;
      return acc;
    },
    { pending: 0, failed: 0, synced: 0 },
  );
}
