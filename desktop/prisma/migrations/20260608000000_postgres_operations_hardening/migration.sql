-- CreateEnum
CREATE TYPE "LogLevel" AS ENUM ('DEBUG', 'INFO', 'WARN', 'ERROR');

-- CreateEnum
CREATE TYPE "BackupStatus" AS ENUM ('RUNNING', 'SUCCESS', 'WARNING', 'FAILED');

-- CreateEnum
CREATE TYPE "BackupProvider" AS ENUM ('LOCAL', 'DROPBOX', 'SUPABASE', 'NEON', 'RAILWAY', 'CUSTOM_POSTGRES');

-- CreateTable
CREATE TABLE "Permission" (
    "key" TEXT NOT NULL,
    "module" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Permission_pkey" PRIMARY KEY ("key")
);

-- CreateTable
CREATE TABLE "RolePermission" (
    "role" "Role" NOT NULL,
    "permissionKey" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RolePermission_pkey" PRIMARY KEY ("role","permissionKey")
);

-- CreateTable
CREATE TABLE "OperationalLog" (
    "id" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "level" "LogLevel" NOT NULL,
    "module" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "metadata" JSONB,
    "workstation" TEXT,

    CONSTRAINT "OperationalLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DatabaseBackup" (
    "id" TEXT NOT NULL,
    "provider" "BackupProvider" NOT NULL DEFAULT 'LOCAL',
    "status" "BackupStatus" NOT NULL DEFAULT 'RUNNING',
    "fileName" TEXT NOT NULL,
    "filePath" TEXT NOT NULL,
    "sizeBytes" INTEGER NOT NULL DEFAULT 0,
    "checksum" TEXT,
    "databaseHost" TEXT,
    "databaseName" TEXT,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),
    "retentionDays" INTEGER NOT NULL DEFAULT 30,
    "message" TEXT,
    "createdById" TEXT,

    CONSTRAINT "DatabaseBackup_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Permission_module_idx" ON "Permission"("module");

-- CreateIndex
CREATE INDEX "RolePermission_permissionKey_idx" ON "RolePermission"("permissionKey");

-- CreateIndex
CREATE INDEX "OperationalLog_createdAt_idx" ON "OperationalLog"("createdAt");

-- CreateIndex
CREATE INDEX "OperationalLog_level_idx" ON "OperationalLog"("level");

-- CreateIndex
CREATE INDEX "OperationalLog_module_idx" ON "OperationalLog"("module");

-- CreateIndex
CREATE INDEX "DatabaseBackup_startedAt_idx" ON "DatabaseBackup"("startedAt");

-- CreateIndex
CREATE INDEX "DatabaseBackup_status_idx" ON "DatabaseBackup"("status");

-- CreateIndex
CREATE INDEX "DatabaseBackup_provider_idx" ON "DatabaseBackup"("provider");

-- AddForeignKey
ALTER TABLE "RolePermission" ADD CONSTRAINT "RolePermission_permissionKey_fkey" FOREIGN KEY ("permissionKey") REFERENCES "Permission"("key") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DatabaseBackup" ADD CONSTRAINT "DatabaseBackup_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;
