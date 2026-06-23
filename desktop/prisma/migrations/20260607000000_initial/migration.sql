-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "Role" AS ENUM ('ADMINISTRADOR', 'OPERACAO', 'MOTORISTA', 'FINANCEIRO');

-- CreateEnum
CREATE TYPE "UserStatus" AS ENUM ('ATIVO', 'INATIVO', 'CONVITE_PENDENTE', 'TROCA_SENHA');

-- CreateEnum
CREATE TYPE "AuditAction" AS ENUM ('LOGIN', 'LOGOUT', 'CREATE', 'UPDATE', 'DELETE', 'ACCESS_DENIED', 'SYNC_EXPORT', 'SYNC_IMPORT', 'SYNC_CONFLICT', 'SYNC_RESOLVE', 'UPDATE_CHECK', 'SYSTEM');

-- CreateEnum
CREATE TYPE "SyncDirection" AS ENUM ('EXPORT', 'IMPORT');

-- CreateEnum
CREATE TYPE "SyncStatus" AS ENUM ('PENDING', 'DONE', 'WARNING', 'ERROR');

-- CreateEnum
CREATE TYPE "ConflictStatus" AS ENUM ('OPEN', 'LOCAL_ACCEPTED', 'REMOTE_ACCEPTED', 'MANUAL_MERGE', 'IGNORED');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "legacyPasswordHash" TEXT,
    "role" "Role" NOT NULL DEFAULT 'OPERACAO',
    "status" "UserStatus" NOT NULL DEFAULT 'TROCA_SENHA',
    "mustChangePassword" BOOLEAN NOT NULL DEFAULT true,
    "lastLoginAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "revokedAt" TIMESTAMP(3),

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Client" (
    "id" TEXT NOT NULL,
    "legacyId" TEXT,
    "customerName" TEXT NOT NULL,
    "contactName" TEXT,
    "cpfCnpj" TEXT,
    "email" TEXT,
    "phone" TEXT,
    "address" TEXT,
    "city" TEXT,
    "state" TEXT,
    "lat" DOUBLE PRECISION,
    "lng" DOUBLE PRECISION,
    "payload" JSONB,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Client_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Event" (
    "id" TEXT NOT NULL,
    "legacyId" TEXT,
    "title" TEXT NOT NULL,
    "eventDate" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'planejado',
    "notes" TEXT,
    "payload" JSONB,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Equipment" (
    "id" TEXT NOT NULL,
    "legacyId" TEXT,
    "equipmentType" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'disponivel',
    "condition" TEXT,
    "notes" TEXT,
    "payload" JSONB,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Equipment_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Vehicle" (
    "id" TEXT NOT NULL,
    "legacyId" TEXT,
    "plate" TEXT,
    "vehicleType" TEXT,
    "model" TEXT,
    "driverName" TEXT,
    "payload" JSONB,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Vehicle_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FinancialEntry" (
    "id" TEXT NOT NULL,
    "legacyId" TEXT,
    "entryType" TEXT NOT NULL,
    "category" TEXT,
    "description" TEXT,
    "amount" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "entryDate" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'aberto',
    "payload" JSONB,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "FinancialEntry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ServiceOrder" (
    "id" TEXT NOT NULL,
    "legacyId" TEXT,
    "eventId" TEXT,
    "clientId" TEXT,
    "driverId" TEXT,
    "status" TEXT NOT NULL DEFAULT 'aberta',
    "scheduledAt" TIMESTAMP(3),
    "payload" JSONB,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ServiceOrder_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "GenericRecord" (
    "id" TEXT NOT NULL,
    "entity" TEXT NOT NULL,
    "legacyId" TEXT NOT NULL,
    "label" TEXT,
    "payload" JSONB NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "GenericRecord_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AuditLog" (
    "id" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "userId" TEXT,
    "userEmail" TEXT,
    "userRole" "Role",
    "action" "AuditAction" NOT NULL,
    "module" TEXT NOT NULL,
    "targetId" TEXT,
    "ipAddress" TEXT,
    "workstation" TEXT,
    "before" JSONB,
    "after" JSONB,
    "detail" TEXT,

    CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Workstation" (
    "id" TEXT NOT NULL,
    "hostname" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "dataDir" TEXT NOT NULL,
    "lastSeenAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Workstation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SyncSnapshot" (
    "id" TEXT NOT NULL,
    "workstationId" TEXT NOT NULL,
    "direction" "SyncDirection" NOT NULL,
    "status" "SyncStatus" NOT NULL DEFAULT 'PENDING',
    "fileName" TEXT NOT NULL,
    "filePath" TEXT NOT NULL,
    "checksum" TEXT NOT NULL,
    "recordCount" INTEGER NOT NULL DEFAULT 0,
    "message" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "SyncSnapshot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SyncCursor" (
    "id" TEXT NOT NULL,
    "sourceWorkstationId" TEXT NOT NULL,
    "entity" TEXT NOT NULL,
    "recordId" TEXT NOT NULL,
    "remoteChecksum" TEXT NOT NULL,
    "remoteUpdatedAt" TIMESTAMP(3) NOT NULL,
    "appliedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SyncCursor_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SyncConflict" (
    "id" TEXT NOT NULL,
    "entity" TEXT NOT NULL,
    "recordId" TEXT NOT NULL,
    "sourceWorkstationId" TEXT NOT NULL,
    "localChecksum" TEXT NOT NULL,
    "remoteChecksum" TEXT NOT NULL,
    "localPayload" JSONB NOT NULL,
    "remotePayload" JSONB NOT NULL,
    "status" "ConflictStatus" NOT NULL DEFAULT 'OPEN',
    "resolution" TEXT,
    "resolvedById" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolvedAt" TIMESTAMP(3),

    CONSTRAINT "SyncConflict_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AppSetting" (
    "key" TEXT NOT NULL,
    "value" JSONB NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AppSetting_pkey" PRIMARY KEY ("key")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE INDEX "User_role_idx" ON "User"("role");

-- CreateIndex
CREATE INDEX "User_status_idx" ON "User"("status");

-- CreateIndex
CREATE UNIQUE INDEX "Session_tokenHash_key" ON "Session"("tokenHash");

-- CreateIndex
CREATE INDEX "Session_userId_idx" ON "Session"("userId");

-- CreateIndex
CREATE INDEX "Session_expiresAt_idx" ON "Session"("expiresAt");

-- CreateIndex
CREATE UNIQUE INDEX "Client_legacyId_key" ON "Client"("legacyId");

-- CreateIndex
CREATE INDEX "Client_customerName_idx" ON "Client"("customerName");

-- CreateIndex
CREATE INDEX "Client_updatedAt_idx" ON "Client"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "Event_legacyId_key" ON "Event"("legacyId");

-- CreateIndex
CREATE INDEX "Event_eventDate_idx" ON "Event"("eventDate");

-- CreateIndex
CREATE INDEX "Event_status_idx" ON "Event"("status");

-- CreateIndex
CREATE INDEX "Event_updatedAt_idx" ON "Event"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "Equipment_legacyId_key" ON "Equipment"("legacyId");

-- CreateIndex
CREATE INDEX "Equipment_equipmentType_idx" ON "Equipment"("equipmentType");

-- CreateIndex
CREATE INDEX "Equipment_status_idx" ON "Equipment"("status");

-- CreateIndex
CREATE INDEX "Equipment_updatedAt_idx" ON "Equipment"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "Vehicle_legacyId_key" ON "Vehicle"("legacyId");

-- CreateIndex
CREATE INDEX "Vehicle_plate_idx" ON "Vehicle"("plate");

-- CreateIndex
CREATE INDEX "Vehicle_updatedAt_idx" ON "Vehicle"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "FinancialEntry_legacyId_key" ON "FinancialEntry"("legacyId");

-- CreateIndex
CREATE INDEX "FinancialEntry_entryDate_idx" ON "FinancialEntry"("entryDate");

-- CreateIndex
CREATE INDEX "FinancialEntry_entryType_idx" ON "FinancialEntry"("entryType");

-- CreateIndex
CREATE INDEX "FinancialEntry_status_idx" ON "FinancialEntry"("status");

-- CreateIndex
CREATE INDEX "FinancialEntry_updatedAt_idx" ON "FinancialEntry"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "ServiceOrder_legacyId_key" ON "ServiceOrder"("legacyId");

-- CreateIndex
CREATE INDEX "ServiceOrder_status_idx" ON "ServiceOrder"("status");

-- CreateIndex
CREATE INDEX "ServiceOrder_scheduledAt_idx" ON "ServiceOrder"("scheduledAt");

-- CreateIndex
CREATE INDEX "ServiceOrder_updatedAt_idx" ON "ServiceOrder"("updatedAt");

-- CreateIndex
CREATE INDEX "GenericRecord_entity_idx" ON "GenericRecord"("entity");

-- CreateIndex
CREATE INDEX "GenericRecord_updatedAt_idx" ON "GenericRecord"("updatedAt");

-- CreateIndex
CREATE UNIQUE INDEX "GenericRecord_entity_legacyId_key" ON "GenericRecord"("entity", "legacyId");

-- CreateIndex
CREATE INDEX "AuditLog_createdAt_idx" ON "AuditLog"("createdAt");

-- CreateIndex
CREATE INDEX "AuditLog_module_idx" ON "AuditLog"("module");

-- CreateIndex
CREATE INDEX "AuditLog_action_idx" ON "AuditLog"("action");

-- CreateIndex
CREATE INDEX "AuditLog_userEmail_idx" ON "AuditLog"("userEmail");

-- CreateIndex
CREATE INDEX "SyncSnapshot_workstationId_idx" ON "SyncSnapshot"("workstationId");

-- CreateIndex
CREATE INDEX "SyncSnapshot_createdAt_idx" ON "SyncSnapshot"("createdAt");

-- CreateIndex
CREATE INDEX "SyncSnapshot_status_idx" ON "SyncSnapshot"("status");

-- CreateIndex
CREATE INDEX "SyncCursor_entity_recordId_idx" ON "SyncCursor"("entity", "recordId");

-- CreateIndex
CREATE UNIQUE INDEX "SyncCursor_sourceWorkstationId_entity_recordId_key" ON "SyncCursor"("sourceWorkstationId", "entity", "recordId");

-- CreateIndex
CREATE INDEX "SyncConflict_status_idx" ON "SyncConflict"("status");

-- CreateIndex
CREATE INDEX "SyncConflict_entity_recordId_idx" ON "SyncConflict"("entity", "recordId");

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AuditLog" ADD CONSTRAINT "AuditLog_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SyncConflict" ADD CONSTRAINT "SyncConflict_resolvedById_fkey" FOREIGN KEY ("resolvedById") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;
