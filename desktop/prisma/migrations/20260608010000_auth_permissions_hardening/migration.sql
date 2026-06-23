ALTER TYPE "Role" ADD VALUE IF NOT EXISTS 'ALMOXARIFADO';
ALTER TYPE "AuditAction" ADD VALUE IF NOT EXISTS 'TOKEN_REFRESH';
ALTER TYPE "AuditAction" ADD VALUE IF NOT EXISTS 'PASSWORD_RESET';
ALTER TYPE "AuditAction" ADD VALUE IF NOT EXISTS 'STATUS_CHANGE';

DO $$ BEGIN
  CREATE TYPE "AccessAction" AS ENUM (
    'LOGIN_SUCCESS',
    'LOGIN_FAILURE',
    'TOKEN_REFRESH',
    'LOGOUT',
    'SESSION_EXPIRED',
    'ACCESS_DENIED'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "login" TEXT;
UPDATE "User" SET "login" = lower("email") WHERE "login" IS NULL OR trim("login") = '';
ALTER TABLE "User" ALTER COLUMN "login" SET NOT NULL;
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "failedLoginCount" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "lockedUntil" TIMESTAMP(3);
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "passwordChangedAt" TIMESTAMP(3);
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "deletedAt" TIMESTAMP(3);

DO $$ BEGIN
  ALTER TABLE "User" ADD CONSTRAINT "User_login_key" UNIQUE ("login");
EXCEPTION
  WHEN duplicate_table THEN null;
  WHEN duplicate_object THEN null;
END $$;

CREATE INDEX IF NOT EXISTS "User_login_idx" ON "User"("login");
CREATE INDEX IF NOT EXISTS "User_deletedAt_idx" ON "User"("deletedAt");

ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "accessTokenId" TEXT;
ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "ipAddress" TEXT;
ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "userAgent" TEXT;
ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "workstation" TEXT;
ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "lastSeenAt" TIMESTAMP(3);
ALTER TABLE "Session" ADD COLUMN IF NOT EXISTS "revokedReason" TEXT;

DO $$ BEGIN
  ALTER TABLE "Session" ADD CONSTRAINT "Session_accessTokenId_key" UNIQUE ("accessTokenId");
EXCEPTION
  WHEN duplicate_table THEN null;
  WHEN duplicate_object THEN null;
END $$;

CREATE INDEX IF NOT EXISTS "Session_revokedAt_idx" ON "Session"("revokedAt");

ALTER TABLE "AuditLog" ADD COLUMN IF NOT EXISTS "userAgent" TEXT;
ALTER TABLE "AuditLog" ADD COLUMN IF NOT EXISTS "requestId" TEXT;

CREATE TABLE IF NOT EXISTS "AccessLog" (
  "id" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "userId" TEXT,
  "userEmail" TEXT,
  "userRole" "Role",
  "action" "AccessAction" NOT NULL,
  "success" BOOLEAN NOT NULL DEFAULT false,
  "sessionId" TEXT,
  "ipAddress" TEXT,
  "userAgent" TEXT,
  "workstation" TEXT,
  "message" TEXT,

  CONSTRAINT "AccessLog_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "AccessLog_createdAt_idx" ON "AccessLog"("createdAt");
CREATE INDEX IF NOT EXISTS "AccessLog_userEmail_idx" ON "AccessLog"("userEmail");
CREATE INDEX IF NOT EXISTS "AccessLog_action_idx" ON "AccessLog"("action");
CREATE INDEX IF NOT EXISTS "AccessLog_success_idx" ON "AccessLog"("success");
CREATE INDEX IF NOT EXISTS "AccessLog_sessionId_idx" ON "AccessLog"("sessionId");

DO $$ BEGIN
  ALTER TABLE "AccessLog" ADD CONSTRAINT "AccessLog_userId_fkey"
  FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;
