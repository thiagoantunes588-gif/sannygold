import {
  AuditAction,
  ConflictStatus,
  LogLevel,
  OfflineActionType,
  OfflineAttachmentKind,
  OfflineQueueItem,
  OfflineQueueStatus,
  Prisma,
  User,
} from "@prisma/client";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { hostname } from "node:os";
import { writeAudit } from "./audit";
import { writeOperationalLog } from "./operational-log";
import { ensureRuntimeFolders } from "./paths";
import { prisma } from "./prisma";

type OfflineActor = Pick<User, "id" | "email" | "role"> | null | undefined;

export type OfflineAttachmentInput = {
  kind: OfflineAttachmentKind;
  fileName: string;
  mimeType?: string | null;
  sizeBytes?: number | null;
  checksum?: string | null;
  dataBase64?: string | null;
};

export type OfflineQueueInput = {
  clientMutationId: string;
  actionType: OfflineActionType;
  entity: string;
  entityId?: string | null;
  operation: string;
  payload: Record<string, unknown>;
  baseVersion?: number | null;
  createdAt?: string | null;
  attachments?: OfflineAttachmentInput[];
};

type RequestContext = {
  ipAddress?: string | null;
  userAgent?: string | null;
};

type QueueItemWithAttachments = Prisma.OfflineQueueItemGetPayload<{
  include: { attachments: true; createdBy: true };
}>;

function jsonInput(value: unknown): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(value)) as Prisma.InputJsonValue;
}

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function checksum(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function safeFileName(value: string): string {
  const cleaned = value.replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "");
  return cleaned || "anexo";
}

function decodeBase64(value: string): Buffer {
  const [, body] = value.includes(",") ? value.split(",", 2) : ["", value];
  return Buffer.from(body, "base64");
}

function nextRetry(attempts: number): Date {
  const delayMinutes = Math.min(60, Math.max(1, 2 ** Math.min(attempts, 5)));
  return new Date(Date.now() + delayMinutes * 60_000);
}

function serviceOrderIdFor(item: Pick<OfflineQueueItem, "entityId" | "payload">): string | null {
  const payload = asObject(item.payload);
  return String(item.entityId || payload.serviceOrderId || payload.id || "").trim() || null;
}

function actionLabel(actionType: OfflineActionType): string {
  const labels: Record<OfflineActionType, string> = {
    CHECKLIST: "checklist",
    CHECK_IN: "check-in",
    CHECK_OUT: "check-out",
    PHOTO: "foto",
    SIGNATURE: "assinatura",
    SERVICE_ORDER: "ordem de serviço",
    OCCURRENCE: "ocorrência",
  };
  return labels[actionType];
}

async function storeAttachmentFiles(item: QueueItemWithAttachments): Promise<Array<Record<string, unknown>>> {
  const layout = ensureRuntimeFolders();
  const serviceOrderId = serviceOrderIdFor(item) || "sem-os";
  const stored: Array<Record<string, unknown>> = [];

  for (const attachment of item.attachments) {
    let storagePath = attachment.storagePath || null;
    let sizeBytes = attachment.sizeBytes;
    let attachmentChecksum = attachment.checksum || null;

    if (attachment.dataBase64 && !storagePath) {
      const buffer = decodeBase64(attachment.dataBase64);
      const relativePath = ["uploads", "offline", serviceOrderId, `${attachment.id}-${safeFileName(attachment.fileName)}`].join("/");
      const fullPath = join(layout.dataDir, ...relativePath.split("/"));
      mkdirSync(dirname(fullPath), { recursive: true });
      writeFileSync(fullPath, buffer);
      storagePath = relativePath;
      sizeBytes = buffer.byteLength;
      attachmentChecksum = createHash("sha256").update(buffer).digest("hex");
      await prisma.offlineAttachment.update({
        where: { id: attachment.id },
        data: {
          storagePath,
          sizeBytes,
          checksum: attachmentChecksum,
          dataBase64: null,
        },
      });
    }

    stored.push({
      id: attachment.id,
      kind: attachment.kind,
      fileName: attachment.fileName,
      mimeType: attachment.mimeType,
      sizeBytes,
      checksum: attachmentChecksum,
      storagePath,
    });
  }

  return stored;
}

function buildServicePayload(
  existingPayload: unknown,
  item: QueueItemWithAttachments,
  attachmentRefs: Array<Record<string, unknown>>,
): Record<string, unknown> {
  const current = asObject(existingPayload);
  const payload = asObject(item.payload);
  const offline = asObject(current.offline);
  const operational = asObject(current.operational);
  const actionRecord = {
    id: item.clientMutationId,
    type: item.actionType,
    operation: item.operation,
    recordedAt: item.createdAt.toISOString(),
    syncedAt: new Date().toISOString(),
    userId: item.createdById,
    workstation: hostname(),
    payload,
    attachments: attachmentRefs,
  };

  const nextOperational: Record<string, unknown> = { ...operational };
  if (item.actionType === OfflineActionType.CHECKLIST) {
    nextOperational.checklist = payload.checklist || payload.items || [];
  }
  if (item.actionType === OfflineActionType.CHECK_IN) {
    nextOperational.checkIn = {
      at: payload.at || new Date().toISOString(),
      gps: payload.gps || null,
      notes: payload.notes || null,
    };
  }
  if (item.actionType === OfflineActionType.CHECK_OUT) {
    nextOperational.checkOut = {
      at: payload.at || new Date().toISOString(),
      gps: payload.gps || null,
      notes: payload.notes || null,
    };
  }
  if (item.actionType === OfflineActionType.PHOTO) {
    nextOperational.photos = [...asArray(nextOperational.photos), ...attachmentRefs];
  }
  if (item.actionType === OfflineActionType.SIGNATURE) {
    nextOperational.signatures = [...asArray(nextOperational.signatures), ...attachmentRefs.map((attachment) => ({
      ...attachment,
      signerName: payload.signerName || null,
    }))];
  }
  if (item.actionType === OfflineActionType.OCCURRENCE) {
    nextOperational.occurrences = [
      ...asArray(nextOperational.occurrences),
      {
        at: payload.at || new Date().toISOString(),
        notes: payload.notes || payload.description || "",
        severity: payload.severity || "normal",
      },
    ];
  }

  return {
    ...current,
    ...asObject(payload.serviceOrderPayload),
    operational: nextOperational,
    offline: {
      ...offline,
      lastSyncedAt: new Date().toISOString(),
      pendingSource: "local-cache",
      actions: [...asArray(offline.actions), actionRecord].slice(-250),
    },
  };
}

function statusForAction(actionType: OfflineActionType, currentStatus?: string | null): string {
  if (actionType === OfflineActionType.CHECK_IN) return "em_andamento";
  if (actionType === OfflineActionType.CHECK_OUT) return "concluida";
  return currentStatus || "aberta";
}

async function createOfflineConflict(
  item: QueueItemWithAttachments,
  localPayload: Record<string, unknown>,
  remotePayload: Record<string, unknown>,
): Promise<string> {
  const conflict = await prisma.syncConflict.create({
    data: {
      entity: item.entity,
      recordId: serviceOrderIdFor(item) || item.clientMutationId,
      sourceWorkstationId: `offline:${hostname()}`,
      localChecksum: checksum(localPayload),
      remoteChecksum: checksum(remotePayload),
      localPayload: jsonInput(localPayload),
      remotePayload: jsonInput(remotePayload),
      status: ConflictStatus.OPEN,
    },
  });

  await prisma.offlineQueueItem.update({
    where: { id: item.id },
    data: {
      status: OfflineQueueStatus.CONFLICT,
      conflictId: conflict.id,
      lastError: "A ordem foi alterada antes da sincronização. Resolva o conflito para continuar.",
    },
  });

  await writeOperationalLog({
    level: LogLevel.WARN,
    module: "offline",
    message: "Conflito offline criado.",
    metadata: {
      queueItemId: item.id,
      clientMutationId: item.clientMutationId,
      conflictId: conflict.id,
      entity: item.entity,
      entityId: item.entityId,
    },
  });

  return conflict.id;
}

async function applyServiceOrderItem(item: QueueItemWithAttachments): Promise<{ targetId: string; status: string }> {
  const attachmentRefs = await storeAttachmentFiles(item);
  const payload = asObject(item.payload);
  const serviceOrderId = serviceOrderIdFor(item) || item.clientMutationId;
  const existing = await prisma.serviceOrder.findUnique({ where: { id: serviceOrderId } });
  const nextPayload = buildServicePayload(existing?.payload, item, attachmentRefs);
  const requestedStatus = typeof payload.status === "string" ? payload.status : undefined;
  const nextStatus = statusForAction(item.actionType, requestedStatus || existing?.status);

  if (existing && item.baseVersion !== null && item.baseVersion !== undefined && existing.version > item.baseVersion) {
    const remotePayload = {
      ...JSON.parse(JSON.stringify(existing)),
      status: nextStatus,
      payload: nextPayload,
      version: existing.version + 1,
      updatedAt: new Date().toISOString(),
    };
    const conflictId = await createOfflineConflict(item, JSON.parse(JSON.stringify(existing)), remotePayload);
    return { targetId: conflictId, status: OfflineQueueStatus.CONFLICT };
  }

  if (existing) {
    const updated = await prisma.serviceOrder.update({
      where: { id: existing.id },
      data: {
        status: nextStatus,
        eventId: typeof payload.eventId === "string" ? payload.eventId : existing.eventId,
        clientId: typeof payload.clientId === "string" ? payload.clientId : existing.clientId,
        driverId: typeof payload.driverId === "string" ? payload.driverId : existing.driverId,
        scheduledAt: typeof payload.scheduledAt === "string" ? new Date(payload.scheduledAt) : existing.scheduledAt,
        payload: jsonInput(nextPayload),
        version: { increment: 1 },
      },
    });
    return { targetId: updated.id, status: updated.status };
  }

  const created = await prisma.serviceOrder.create({
    data: {
      id: serviceOrderId,
      status: nextStatus,
      eventId: typeof payload.eventId === "string" ? payload.eventId : undefined,
      clientId: typeof payload.clientId === "string" ? payload.clientId : undefined,
      driverId: item.createdById || (typeof payload.driverId === "string" ? payload.driverId : undefined),
      scheduledAt: typeof payload.scheduledAt === "string" ? new Date(payload.scheduledAt) : undefined,
      payload: jsonInput({
        title: payload.title || payload.description || "Ordem criada offline",
        ...nextPayload,
      }),
    },
  });
  return { targetId: created.id, status: created.status };
}

async function applyQueueItem(item: QueueItemWithAttachments): Promise<{ targetId: string; status: string }> {
  if (item.entity !== "serviceOrder") {
    throw new Error(`Entidade offline não suportada: ${item.entity}`);
  }
  return applyServiceOrderItem(item);
}

export async function enqueueOfflineItems(
  inputs: OfflineQueueInput[],
  actor: OfflineActor,
  context: RequestContext = {},
): Promise<{ accepted: number; duplicates: number; items: Array<{ id: string; clientMutationId: string; status: OfflineQueueStatus }> }> {
  let accepted = 0;
  let duplicates = 0;
  const items: Array<{ id: string; clientMutationId: string; status: OfflineQueueStatus }> = [];

  for (const input of inputs) {
    const existing = await prisma.offlineQueueItem.findUnique({ where: { clientMutationId: input.clientMutationId } });
    if (existing) {
      duplicates += 1;
      items.push({ id: existing.id, clientMutationId: existing.clientMutationId, status: existing.status });
      continue;
    }

    const created = await prisma.offlineQueueItem.create({
      data: {
        clientMutationId: input.clientMutationId,
        actionType: input.actionType,
        entity: input.entity,
        entityId: input.entityId || undefined,
        operation: input.operation,
        payload: jsonInput(input.payload),
        baseVersion: input.baseVersion ?? undefined,
        createdById: actor?.id,
        createdAt: input.createdAt ? new Date(input.createdAt) : undefined,
        attachments: {
          create: (input.attachments || []).map((attachment) => ({
            kind: attachment.kind,
            fileName: attachment.fileName,
            mimeType: attachment.mimeType || undefined,
            sizeBytes: attachment.sizeBytes || 0,
            checksum: attachment.checksum || undefined,
            dataBase64: attachment.dataBase64 || undefined,
          })),
        },
      },
    });

    accepted += 1;
    items.push({ id: created.id, clientMutationId: created.clientMutationId, status: created.status });
  }

  await writeAudit({
    user: actor,
    action: AuditAction.OFFLINE_QUEUE,
    module: "offline",
    ipAddress: context.ipAddress,
    userAgent: context.userAgent,
    after: { accepted, duplicates, total: inputs.length },
    detail: "Ações offline recebidas na fila de sincronização.",
  });

  return { accepted, duplicates, items };
}

export async function processOfflineQueue(
  actor: OfflineActor,
  context: RequestContext = {},
): Promise<{ processed: number; done: number; failed: number; conflicts: number }> {
  const now = new Date();
  const pending = await prisma.offlineQueueItem.findMany({
    where: {
      status: { in: [OfflineQueueStatus.PENDING, OfflineQueueStatus.FAILED] },
      OR: [{ nextRetryAt: null }, { nextRetryAt: { lte: now } }],
    },
    include: { attachments: true, createdBy: true },
    orderBy: { createdAt: "asc" },
    take: 100,
  });

  let done = 0;
  let failed = 0;
  let conflicts = 0;

  for (const item of pending) {
    if (item.attempts >= item.maxAttempts) continue;
    await prisma.offlineQueueItem.update({
      where: { id: item.id },
      data: { status: OfflineQueueStatus.SYNCING, lastError: null },
    });

    try {
      const result = await applyQueueItem(item);
      if (result.status === OfflineQueueStatus.CONFLICT) {
        conflicts += 1;
        continue;
      }
      await prisma.offlineQueueItem.update({
        where: { id: item.id },
        data: {
          status: OfflineQueueStatus.DONE,
          attempts: { increment: 1 },
          syncedAt: new Date(),
          lastError: null,
          nextRetryAt: null,
        },
      });
      await writeAudit({
        user: item.createdBy || actor,
        action: AuditAction.OFFLINE_SYNC,
        module: "offline",
        targetId: result.targetId,
        ipAddress: context.ipAddress,
        userAgent: context.userAgent,
        after: {
          queueItemId: item.id,
          clientMutationId: item.clientMutationId,
          actionType: item.actionType,
          operation: item.operation,
          targetStatus: result.status,
        },
        detail: `Ação offline sincronizada: ${actionLabel(item.actionType)}.`,
      });
      done += 1;
    } catch (error) {
      const attempts = item.attempts + 1;
      const finalFailure = attempts >= item.maxAttempts;
      await prisma.offlineQueueItem.update({
        where: { id: item.id },
        data: {
          status: finalFailure ? OfflineQueueStatus.FAILED : OfflineQueueStatus.PENDING,
          attempts,
          lastError: error instanceof Error ? error.message : String(error),
          nextRetryAt: finalFailure ? null : nextRetry(attempts),
        },
      });
      await writeOperationalLog({
        level: finalFailure ? LogLevel.ERROR : LogLevel.WARN,
        module: "offline",
        message: finalFailure ? "Ação offline falhou definitivamente." : "Ação offline reagendada para retry.",
        metadata: {
          queueItemId: item.id,
          clientMutationId: item.clientMutationId,
          attempts,
          error: error instanceof Error ? error.message : String(error),
        },
      });
      failed += 1;
    }
  }

  await writeOperationalLog({
    level: conflicts || failed ? LogLevel.WARN : LogLevel.INFO,
    module: "offline",
    message: "Processamento da fila offline concluído.",
    metadata: { processed: pending.length, done, failed, conflicts },
  });

  return { processed: pending.length, done, failed, conflicts };
}

export async function offlineStatus(): Promise<Record<string, unknown>> {
  const [pending, syncing, done, failed, conflicts, lastSynced, recentConflicts] = await Promise.all([
    prisma.offlineQueueItem.count({ where: { status: OfflineQueueStatus.PENDING } }),
    prisma.offlineQueueItem.count({ where: { status: OfflineQueueStatus.SYNCING } }),
    prisma.offlineQueueItem.count({ where: { status: OfflineQueueStatus.DONE } }),
    prisma.offlineQueueItem.count({ where: { status: OfflineQueueStatus.FAILED } }),
    prisma.offlineQueueItem.count({ where: { status: OfflineQueueStatus.CONFLICT } }),
    prisma.offlineQueueItem.findFirst({ where: { status: OfflineQueueStatus.DONE }, orderBy: { syncedAt: "desc" } }),
    prisma.offlineQueueItem.findMany({
      where: { status: OfflineQueueStatus.CONFLICT },
      orderBy: { updatedAt: "desc" },
      take: 20,
      select: {
        id: true,
        clientMutationId: true,
        actionType: true,
        entity: true,
        entityId: true,
        conflictId: true,
        lastError: true,
        updatedAt: true,
      },
    }),
  ]);

  return {
    workstation: hostname(),
    queue: { pending, syncing, done, failed, conflicts },
    lastSyncedAt: lastSynced?.syncedAt || null,
    recentConflicts,
  };
}

export async function listOfflineQueue(limit = 100): Promise<Array<Record<string, unknown>>> {
  const items = await prisma.offlineQueueItem.findMany({
    orderBy: { createdAt: "desc" },
    take: Math.min(Math.max(limit, 1), 300),
    include: {
      attachments: {
        select: {
          id: true,
          kind: true,
          fileName: true,
          mimeType: true,
          sizeBytes: true,
          checksum: true,
          storagePath: true,
          createdAt: true,
        },
      },
      createdBy: {
        select: {
          id: true,
          name: true,
          email: true,
          role: true,
        },
      },
    },
  });
  return items.map((item) => ({
    ...item,
    payload: item.payload,
    attachmentCount: item.attachments.length,
  }));
}
