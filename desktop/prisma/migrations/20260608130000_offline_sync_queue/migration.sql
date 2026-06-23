ALTER TYPE "AuditAction" ADD VALUE IF NOT EXISTS 'OFFLINE_QUEUE';
ALTER TYPE "AuditAction" ADD VALUE IF NOT EXISTS 'OFFLINE_SYNC';
ALTER TYPE "AuditAction" ADD VALUE IF NOT EXISTS 'OFFLINE_CONFLICT';

DO $$ BEGIN
  CREATE TYPE "OfflineActionType" AS ENUM (
    'CHECKLIST',
    'CHECK_IN',
    'CHECK_OUT',
    'PHOTO',
    'SIGNATURE',
    'SERVICE_ORDER',
    'OCCURRENCE'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  CREATE TYPE "OfflineQueueStatus" AS ENUM (
    'PENDING',
    'SYNCING',
    'DONE',
    'FAILED',
    'CONFLICT'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  CREATE TYPE "OfflineAttachmentKind" AS ENUM (
    'PHOTO',
    'SIGNATURE',
    'DOCUMENT'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS "OfflineQueueItem" (
  "id" TEXT NOT NULL,
  "clientMutationId" TEXT NOT NULL,
  "actionType" "OfflineActionType" NOT NULL,
  "entity" TEXT NOT NULL,
  "entityId" TEXT,
  "operation" TEXT NOT NULL,
  "payload" JSONB NOT NULL,
  "baseVersion" INTEGER,
  "status" "OfflineQueueStatus" NOT NULL DEFAULT 'PENDING',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "maxAttempts" INTEGER NOT NULL DEFAULT 5,
  "nextRetryAt" TIMESTAMP(3),
  "lastError" TEXT,
  "conflictId" TEXT,
  "createdById" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "syncedAt" TIMESTAMP(3),

  CONSTRAINT "OfflineQueueItem_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "OfflineAttachment" (
  "id" TEXT NOT NULL,
  "queueItemId" TEXT NOT NULL,
  "kind" "OfflineAttachmentKind" NOT NULL,
  "fileName" TEXT NOT NULL,
  "mimeType" TEXT,
  "sizeBytes" INTEGER NOT NULL DEFAULT 0,
  "checksum" TEXT,
  "storagePath" TEXT,
  "dataBase64" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "OfflineAttachment_pkey" PRIMARY KEY ("id")
);

DO $$ BEGIN
  ALTER TABLE "OfflineQueueItem" ADD CONSTRAINT "OfflineQueueItem_clientMutationId_key" UNIQUE ("clientMutationId");
EXCEPTION
  WHEN duplicate_table THEN null;
  WHEN duplicate_object THEN null;
END $$;

CREATE INDEX IF NOT EXISTS "OfflineQueueItem_status_nextRetryAt_idx" ON "OfflineQueueItem"("status", "nextRetryAt");
CREATE INDEX IF NOT EXISTS "OfflineQueueItem_entity_entityId_idx" ON "OfflineQueueItem"("entity", "entityId");
CREATE INDEX IF NOT EXISTS "OfflineQueueItem_createdAt_idx" ON "OfflineQueueItem"("createdAt");
CREATE INDEX IF NOT EXISTS "OfflineQueueItem_createdById_idx" ON "OfflineQueueItem"("createdById");
CREATE INDEX IF NOT EXISTS "OfflineAttachment_queueItemId_idx" ON "OfflineAttachment"("queueItemId");
CREATE INDEX IF NOT EXISTS "OfflineAttachment_kind_idx" ON "OfflineAttachment"("kind");

DO $$ BEGIN
  ALTER TABLE "OfflineQueueItem" ADD CONSTRAINT "OfflineQueueItem_createdById_fkey"
  FOREIGN KEY ("createdById") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  ALTER TABLE "OfflineAttachment" ADD CONSTRAINT "OfflineAttachment_queueItemId_fkey"
  FOREIGN KEY ("queueItemId") REFERENCES "OfflineQueueItem"("id") ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;
