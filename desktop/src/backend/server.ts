import compression from "compression";
import cors from "cors";
import express, { NextFunction, Request, Response } from "express";
import helmet from "helmet";
import bcrypt from "bcryptjs";
import { AuditAction, OfflineActionType, OfflineAttachmentKind, Prisma, Role, UserStatus } from "@prisma/client";
import { z } from "zod";
import { LogLevel } from "@prisma/client";
import { createServer, Server } from "node:http";
import { randomBytes } from "node:crypto";
import { authenticateRequest, AuthenticatedRequest, login, logout, refreshSession, requirePermission, toSafeUser } from "./auth";
import { prisma } from "./prisma";
import { permissionCatalog, permissionsForRole, roleFromInput, roleLabels } from "./permissions";
import { validateRuntimeLayout } from "./paths";
import { exportSnapshot, importSnapshots, registerWorkstation, resolveConflict, syncStatus } from "./sync";
import { writeAudit } from "./audit";
import { logger } from "./logger";
import { connectWithRetry, databaseHealth, sanitizedDatabaseConfig } from "./database";
import { runAutomaticMigrations } from "./migrations";
import { writeOperationalLog } from "./operational-log";
import { backupStatus, createPostgresBackup, startAutomaticBackupScheduler } from "./database-backup";
import { enqueueOfflineItems, listOfflineQueue, offlineStatus, processOfflineQueue } from "./offline";

type BackendServer = {
  app: express.Express;
  server: Server;
  host: string;
  port: number;
  close: () => Promise<void>;
};

type BackendServerOptions = {
  port?: number;
  safeMode?: boolean;
};

const loginSchema = z.object({
  login: z.string().min(2),
  password: z.string().min(1),
});

const refreshSchema = z.object({
  refreshToken: z.string().min(20),
});

const userSchema = z.object({
  name: z.string().min(2),
  login: z.string().min(2).optional(),
  email: z.string().email(),
  role: z.string().default("operacao"),
  password: z.string().min(10).optional(),
  status: z.string().optional(),
});

const userUpdateSchema = z.object({
  name: z.string().min(2).optional(),
  login: z.string().min(2).optional(),
  email: z.string().email().optional(),
  role: z.string().optional(),
  status: z.string().optional(),
  mustChangePassword: z.boolean().optional(),
});

const passwordResetSchema = z.object({
  password: z.string().min(10).optional(),
});

const clientSchema = z.object({
  customerName: z.string().min(2),
  contactName: z.string().optional().nullable(),
  cpfCnpj: z.string().optional().nullable(),
  email: z.string().optional().nullable(),
  phone: z.string().optional().nullable(),
  address: z.string().optional().nullable(),
  city: z.string().optional().nullable(),
  state: z.string().optional().nullable(),
  lat: z.number().optional().nullable(),
  lng: z.number().optional().nullable(),
  payload: z.record(z.unknown()).optional().nullable(),
});

const serviceOrderSchema = z.object({
  id: z.string().min(3).optional(),
  eventId: z.string().optional().nullable(),
  clientId: z.string().optional().nullable(),
  driverId: z.string().optional().nullable(),
  status: z.string().optional(),
  scheduledAt: z.string().optional().nullable(),
  payload: z.record(z.unknown()).optional().nullable(),
});

const offlineAttachmentSchema = z.object({
  kind: z.nativeEnum(OfflineAttachmentKind),
  fileName: z.string().min(1),
  mimeType: z.string().optional().nullable(),
  sizeBytes: z.number().int().nonnegative().optional().nullable(),
  checksum: z.string().optional().nullable(),
  dataBase64: z.string().optional().nullable(),
});

const offlineQueueItemSchema = z.object({
  clientMutationId: z.string().min(8),
  actionType: z.nativeEnum(OfflineActionType),
  entity: z.string().min(2).default("serviceOrder"),
  entityId: z.string().optional().nullable(),
  operation: z.string().min(2),
  payload: z.record(z.unknown()).default({}),
  baseVersion: z.number().int().nonnegative().optional().nullable(),
  createdAt: z.string().optional().nullable(),
  attachments: z.array(offlineAttachmentSchema).max(12).optional(),
});

const offlineQueueBatchSchema = z.object({
  items: z.array(offlineQueueItemSchema).min(1).max(200),
});

const mobileDeviceSchema = z.object({
  deviceId: z.string().min(4),
  platform: z.string().min(2),
  pushToken: z.string().optional().nullable(),
  appVersion: z.string().optional().nullable(),
  deviceName: z.string().optional().nullable(),
});

function jsonInput(value: unknown): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(value)) as Prisma.InputJsonValue;
}

function asyncRoute(
  handler: (req: AuthenticatedRequest, res: Response, next: NextFunction) => Promise<void>,
) {
  return (req: Request, res: Response, next: NextFunction) => {
    handler(req as AuthenticatedRequest, res, next).catch(next);
  };
}

function lowerText(value: unknown): string {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function startOfToday(): Date {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date;
}

function endOfToday(): Date {
  const date = startOfToday();
  date.setDate(date.getDate() + 1);
  return date;
}

function numericPayloadValue(payload: Prisma.JsonValue | null, keys: string[]): number | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = Number(record[key]);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function stockRiskFromPayload(payload: Prisma.JsonValue | null): boolean {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  const record = payload as Record<string, unknown>;
  const status = lowerText(record.stock_status || record.status || record.situacao);
  if (["baixo", "zerado", "low", "empty", "critico", "critica"].includes(status)) return true;
  const quantity = numericPayloadValue(payload, ["quantity", "qty", "current_stock", "currentStock", "saldo", "estoque_atual"]);
  const minimum = numericPayloadValue(payload, ["minimum", "min_stock", "minStock", "estoque_minimo"]);
  return quantity !== null && minimum !== null && quantity <= minimum;
}

function normalizeStatus(value: string | undefined): UserStatus {
  const normalized = String(value || "").trim().toLowerCase();
  if (["ativo", "active"].includes(normalized)) return UserStatus.ATIVO;
  if (["inativo", "inactive"].includes(normalized)) return UserStatus.INATIVO;
  if (["convite", "convite_pendente"].includes(normalized)) return UserStatus.CONVITE_PENDENTE;
  if (["troca_senha", "troca-senha", "troca senha"].includes(normalized)) return UserStatus.TROCA_SENHA;
  return UserStatus.TROCA_SENHA;
}

function normalizeLogin(value: string): string {
  return value.trim().toLowerCase();
}

function requestUserAgent(req: Request): string | undefined {
  return req.header("user-agent") || undefined;
}

function roleMatrix(): Array<{ role: Role; label: string; permissions: string[] }> {
  return Object.values(Role).map((role) => ({
    role,
    label: roleLabels[role],
    permissions: permissionsForRole(role),
  }));
}

function configuredApiHost(): string {
  return process.env.SANNYSYSTEM_API_HOST?.trim() || "127.0.0.1";
}

function configuredApiPort(options: BackendServerOptions): number {
  const fromOptions = options.port;
  const fromEnv = Number.parseInt(process.env.SANNYSYSTEM_API_PORT || "", 10);
  if (fromOptions !== undefined) return fromOptions;
  return Number.isFinite(fromEnv) ? fromEnv : 0;
}

export async function createBackendServer(options: BackendServerOptions = {}): Promise<BackendServer> {
  const initialSetup = validateRuntimeLayout();
  if (!initialSetup.ready) {
    logger.warn("Setup inicial exige atenção", { issues: initialSetup.issues });
  }
  const migrationResult = options.safeMode
    ? { skipped: true, reason: "safe_mode", message: "Migrations automaticas desativadas em safe mode." }
    : await runAutomaticMigrations();
  await connectWithRetry(prisma, Number.parseInt(process.env.SANNYSYSTEM_DB_CONNECT_ATTEMPTS || "5", 10));
  await registerWorkstation();
  await writeOperationalLog({
    level: LogLevel.INFO,
    module: "database",
    message: "Conexão PostgreSQL pronta.",
    metadata: { migrationResult, database: sanitizedDatabaseConfig(), safeMode: Boolean(options.safeMode) },
  });
  if (!options.safeMode) startAutomaticBackupScheduler();

  const app = express();
  app.disable("x-powered-by");
  app.use(helmet({ contentSecurityPolicy: false }));
  app.use(cors({ origin: true, credentials: true }));
  app.use(compression());
  app.use(express.json({ limit: "20mb" }));
  app.use((req, res, next) => {
    const requestId = randomBytes(8).toString("hex");
    res.on("finish", () => {
      if (!["POST", "PUT", "PATCH", "DELETE"].includes(req.method)) return;
      const authReq = req as AuthenticatedRequest;
      if (!authReq.authUser) return;
      writeAudit({
        user: authReq.authUser,
        action: AuditAction.SYSTEM,
        module: "api",
        targetId: req.path,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        requestId,
        detail: `${req.method} ${req.path} -> ${res.statusCode}`,
      }).catch((error) => logger.error("Falha ao registrar auditoria automática", { error, requestId }));
    });
    next();
  });

  app.get("/api/health", asyncRoute(async (_req, res) => {
    const setup = validateRuntimeLayout();
    const db = await databaseHealth(prisma);
    const userCount = await prisma.user.count();

    res.json({
      ok: true,
      database: "postgresql",
      prisma: true,
      databaseHealth: db,
      safeMode: Boolean(options.safeMode),
      users: userCount,
      dropboxDetected: Boolean(setup.layout.dropboxRoot),
      setupReady: setup.ready,
      setup,
    });
  }));

  app.get("/api/setup", asyncRoute(async (_req, res) => {
    res.json(validateRuntimeLayout());
  }));

  app.get("/api/dashboard/operations", authenticateRequest, asyncRoute(async (_req, res) => {
    const now = new Date();
    const todayStart = startOfToday();
    const tomorrowStart = endOfToday();
    const closedOrderStatuses = ["concluida", "concluída", "finalizada", "done", "cancelada", "cancelled"];
    const availableEquipmentStatuses = ["disponivel", "disponível", "available", "livre"];
    const inUseEquipmentStatuses = ["em_operacao", "em operação", "em_rota", "em rota", "instalado", "carregado", "reservado"];
    const maintenanceEquipmentStatuses = ["manutencao", "manutenção", "maintenance", "indisponivel", "indisponível", "baixado"];
    const paidFinancialStatuses = ["pago", "quitado", "fechado", "paid", "done", "concluido", "concluído"];

    const [
      serviceOrders,
      delayedOrders,
      eventsToday,
      futureEvents,
      equipmentByStatus,
      vehiclesTotal,
      financialPending,
      warehouseRecords,
      sync,
      offline,
    ] = await Promise.all([
      prisma.serviceOrder.findMany({
        where: { deletedAt: null },
        orderBy: [{ scheduledAt: "asc" }, { updatedAt: "desc" }],
        take: 500,
      }),
      prisma.serviceOrder.count({
        where: {
          deletedAt: null,
          scheduledAt: { lt: now },
          status: { notIn: closedOrderStatuses },
        },
      }),
      prisma.event.count({
        where: {
          deletedAt: null,
          eventDate: { gte: todayStart, lt: tomorrowStart },
        },
      }),
      prisma.event.count({
        where: {
          deletedAt: null,
          eventDate: { gte: todayStart },
        },
      }),
      prisma.equipment.groupBy({
        by: ["status"],
        where: { deletedAt: null },
        _count: { _all: true },
      }),
      prisma.vehicle.count({ where: { deletedAt: null } }),
      prisma.financialEntry.aggregate({
        where: { deletedAt: null, status: { notIn: paidFinancialStatuses } },
        _count: { _all: true },
        _sum: { amount: true },
      }),
      prisma.genericRecord.findMany({
        where: {
          deletedAt: null,
          entity: { in: ["warehouse_items", "warehouseItem", "warehouse", "almoxarifado"] },
        },
        take: 1000,
      }),
      syncStatus(),
      offlineStatus(),
    ]);

    const activeOrders = serviceOrders.filter((item) => !closedOrderStatuses.includes(lowerText(item.status)));
    const equipment = equipmentByStatus.reduce(
      (summary, group) => {
        const status = lowerText(group.status);
        const count = group._count._all;
        summary.total += count;
        if (availableEquipmentStatuses.includes(status)) summary.available += count;
        else if (inUseEquipmentStatuses.includes(status)) summary.inUse += count;
        else if (maintenanceEquipmentStatuses.includes(status)) summary.maintenance += count;
        else summary.other += count;
        return summary;
      },
      { total: 0, available: 0, inUse: 0, maintenance: 0, other: 0 },
    );
    const offlineQueue = (offline.queue || {}) as Record<string, unknown>;

    res.json({
      generatedAt: now.toISOString(),
      serviceOrders: {
        total: serviceOrders.length,
        active: activeOrders.length,
        delayed: delayedOrders,
        latest: serviceOrders.slice(0, 12),
      },
      events: {
        today: eventsToday,
        future: futureEvents,
        simultaneous: eventsToday,
      },
      equipment,
      vehicles: {
        active: vehiclesTotal,
        total: vehiclesTotal,
      },
      warehouse: {
        total: warehouseRecords.length,
        lowStock: warehouseRecords.filter((item) => stockRiskFromPayload(item.payload)).length,
      },
      financial: {
        openCount: financialPending._count._all,
        openAmount: financialPending._sum.amount || 0,
      },
      sync: {
        openConflicts: sync.openConflicts || 0,
        lastSnapshot: sync.lastSnapshot || null,
      },
      offline: {
        pending: offlineQueue.pending || 0,
        conflicts: offlineQueue.conflicts || 0,
      },
    });
  }));

  app.get("/api/database/status", authenticateRequest, requirePermission("database.manage"), asyncRoute(async (_req, res) => {
    res.json({
      database: sanitizedDatabaseConfig(),
      health: await databaseHealth(prisma),
      backups: await backupStatus(),
    });
  }));

  app.post("/api/database/backups", authenticateRequest, requirePermission("database.manage"), asyncRoute(async (req, res) => {
    res.status(201).json(await createPostgresBackup(req.authUser?.id));
  }));

  app.get("/api/logs/operational", authenticateRequest, requirePermission("logs.read"), asyncRoute(async (_req, res) => {
    const entries = await prisma.operationalLog.findMany({ orderBy: { createdAt: "desc" }, take: 300 });
    res.json({ entries });
  }));

  app.post("/api/auth/login", asyncRoute(async (req, res) => {
    const payload = loginSchema.parse(req.body);
    const result = await login(payload.login, payload.password, req.ip, requestUserAgent(req));
    res.json(result);
  }));

  app.post("/api/auth/refresh", asyncRoute(async (req, res) => {
    const payload = refreshSchema.parse(req.body);
    const result = await refreshSession(payload.refreshToken, req.ip, requestUserAgent(req));
    res.json(result);
  }));

  app.post("/api/auth/logout", authenticateRequest, asyncRoute(async (req, res) => {
    await logout(req);
    res.json({ ok: true });
  }));

  app.get("/api/auth/me", authenticateRequest, asyncRoute(async (req, res) => {
    res.json({ user: toSafeUser(req.authUser!) });
  }));

  app.post("/api/mobile/devices", authenticateRequest, asyncRoute(async (req, res) => {
    const payload = mobileDeviceSchema.parse(req.body);
    const settingKey = "mobile.devices";
    const current = await prisma.appSetting.findUnique({ where: { key: settingKey } });
    const devices = Array.isArray(current?.value) ? (current.value as Array<Record<string, unknown>>) : [];
    const now = new Date().toISOString();
    const nextDevice = {
      ...payload,
      userId: req.authUser!.id,
      userEmail: req.authUser!.email,
      updatedAt: now,
      lastSeenAt: now,
    };
    const nextDevices = [
      nextDevice,
      ...devices.filter((device) => String(device.deviceId || "") !== payload.deviceId),
    ].slice(0, 500);
    await prisma.appSetting.upsert({
      where: { key: settingKey },
      create: { key: settingKey, value: jsonInput(nextDevices) },
      update: { value: jsonInput(nextDevices) },
    });
    await writeAudit({
      user: req.authUser,
      action: AuditAction.SYSTEM,
      module: "mobile",
      targetId: payload.deviceId,
      ipAddress: req.ip,
      userAgent: requestUserAgent(req),
      after: { platform: payload.platform, appVersion: payload.appVersion, hasPushToken: Boolean(payload.pushToken) },
      detail: "Dispositivo mobile registrado.",
    });
    res.status(202).json({ ok: true });
  }));

  app.get("/api/auth/sessions", authenticateRequest, asyncRoute(async (req, res) => {
    const sessions = await prisma.session.findMany({
      where: { userId: req.authUser!.id },
      orderBy: { createdAt: "desc" },
      take: 20,
      select: {
        id: true,
        ipAddress: true,
        userAgent: true,
        workstation: true,
        createdAt: true,
        lastSeenAt: true,
        expiresAt: true,
        revokedAt: true,
        revokedReason: true,
      },
    });
    res.json({ sessions });
  }));

  app.get("/api/system/paths", authenticateRequest, asyncRoute(async (_req, res) => {
    res.json(validateRuntimeLayout());
  }));

  app.get(
    "/api/users",
    authenticateRequest,
    requirePermission("users.manage"),
    asyncRoute(async (_req, res) => {
      const users = await prisma.user.findMany({
        orderBy: [{ role: "asc" }, { name: "asc" }],
        select: {
          id: true,
          login: true,
          name: true,
          email: true,
          role: true,
          status: true,
          mustChangePassword: true,
          lastLoginAt: true,
          failedLoginCount: true,
          lockedUntil: true,
          deletedAt: true,
          createdAt: true,
          updatedAt: true,
        },
      });
      res.json({ users });
    }),
  );

  app.post(
    "/api/users",
    authenticateRequest,
    requirePermission("users.manage"),
    asyncRoute(async (req, res) => {
      const payload = userSchema.parse(req.body);
      const temporaryPassword = payload.password || randomBytes(12).toString("base64url");
      const role = roleFromInput(payload.role);
      const passwordHash = await bcrypt.hash(temporaryPassword, 12);
      const status = normalizeStatus(payload.status || "ativo");
      const email = normalizeLogin(payload.email);
      const loginValue = normalizeLogin(payload.login || payload.email);
      const user = await prisma.user.upsert({
        where: { email },
        create: {
          name: payload.name.trim(),
          login: loginValue,
          email,
          role,
          status,
          mustChangePassword: true,
          passwordHash,
          passwordChangedAt: new Date(),
        },
        update: {
          name: payload.name.trim(),
          login: loginValue,
          role,
          status,
          deletedAt: null,
          ...(payload.password ? { passwordHash, mustChangePassword: true } : {}),
        },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.CREATE,
        module: "users",
        targetId: user.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        after: { login: user.login, email: user.email, role: user.role, status: user.status },
      });
      res.status(201).json({ user: toSafeUser(user), temporaryPassword: payload.password ? undefined : temporaryPassword });
    }),
  );

  app.put(
    "/api/users/:id",
    authenticateRequest,
    requirePermission("users.manage"),
    asyncRoute(async (req, res) => {
      const id = String(req.params.id);
      const before = await prisma.user.findUnique({ where: { id } });
      if (!before) {
        res.status(404).json({ error: "Usuário não encontrado." });
        return;
      }
      const payload = userUpdateSchema.parse(req.body);
      const role = payload.role ? roleFromInput(payload.role) : undefined;
      const status = payload.status ? normalizeStatus(payload.status) : undefined;
      const user = await prisma.user.update({
        where: { id },
        data: {
          ...(payload.name ? { name: payload.name.trim() } : {}),
          ...(payload.login ? { login: normalizeLogin(payload.login) } : {}),
          ...(payload.email ? { email: normalizeLogin(payload.email) } : {}),
          ...(role ? { role } : {}),
          ...(status ? { status } : {}),
          ...(status && status !== UserStatus.INATIVO ? { deletedAt: null } : {}),
          ...(payload.mustChangePassword !== undefined ? { mustChangePassword: payload.mustChangePassword } : {}),
        },
      });
      await writeAudit({
        user: req.authUser,
        action: before.status !== user.status ? AuditAction.STATUS_CHANGE : AuditAction.UPDATE,
        module: "users",
        targetId: user.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        before: {
          login: before.login,
          email: before.email,
          role: before.role,
          status: before.status,
          mustChangePassword: before.mustChangePassword,
        },
        after: {
          login: user.login,
          email: user.email,
          role: user.role,
          status: user.status,
          mustChangePassword: user.mustChangePassword,
        },
      });
      res.json({ user: toSafeUser(user) });
    }),
  );

  app.post(
    "/api/users/:id/reset-password",
    authenticateRequest,
    requirePermission("users.manage"),
    asyncRoute(async (req, res) => {
      const id = String(req.params.id);
      const payload = passwordResetSchema.parse(req.body);
      const before = await prisma.user.findUnique({ where: { id } });
      if (!before) {
        res.status(404).json({ error: "Usuário não encontrado." });
        return;
      }
      const temporaryPassword = payload.password || randomBytes(12).toString("base64url");
      const passwordHash = await bcrypt.hash(temporaryPassword, 12);
      const user = await prisma.user.update({
        where: { id },
        data: {
          passwordHash,
          mustChangePassword: true,
          failedLoginCount: 0,
          lockedUntil: null,
          passwordChangedAt: new Date(),
        },
      });
      await prisma.session.updateMany({
        where: { userId: id, revokedAt: null },
        data: { revokedAt: new Date(), revokedReason: "password_reset" },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.PASSWORD_RESET,
        module: "users",
        targetId: user.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        before: { email: before.email, mustChangePassword: before.mustChangePassword },
        after: { email: user.email, mustChangePassword: user.mustChangePassword },
        detail: "Senha redefinida e sessões anteriores revogadas.",
      });
      res.json({ user: toSafeUser(user), temporaryPassword: payload.password ? undefined : temporaryPassword });
    }),
  );

  app.delete(
    "/api/users/:id",
    authenticateRequest,
    requirePermission("users.manage"),
    asyncRoute(async (req, res) => {
      const id = String(req.params.id);
      if (req.authUser?.id === id) {
        res.status(400).json({ error: "Não é permitido excluir o próprio usuário logado." });
        return;
      }
      const before = await prisma.user.findUnique({ where: { id } });
      if (!before) {
        res.status(404).json({ error: "Usuário não encontrado." });
        return;
      }
      const user = await prisma.user.update({
        where: { id },
        data: { status: UserStatus.INATIVO, deletedAt: new Date() },
      });
      await prisma.session.updateMany({
        where: { userId: id, revokedAt: null },
        data: { revokedAt: new Date(), revokedReason: "user_deleted" },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.DELETE,
        module: "users",
        targetId: user.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        before: { login: before.login, email: before.email, role: before.role, status: before.status },
        after: { login: user.login, email: user.email, role: user.role, status: user.status, deletedAt: user.deletedAt },
        detail: "Usuário inativado com histórico de exclusão preservado.",
      });
      res.json({ user: toSafeUser(user) });
    }),
  );

  app.get(
    "/api/users/:id/history",
    authenticateRequest,
    requirePermission("users.manage"),
    asyncRoute(async (req, res) => {
      const id = String(req.params.id);
      const user = await prisma.user.findUnique({ where: { id } });
      if (!user) {
        res.status(404).json({ error: "Usuário não encontrado." });
        return;
      }
      const [audit, access, sessions] = await Promise.all([
        prisma.auditLog.findMany({
          where: {
            OR: [{ userId: id }, { targetId: id }],
          },
          orderBy: { createdAt: "desc" },
          take: 120,
        }),
        prisma.accessLog.findMany({ where: { userId: id }, orderBy: { createdAt: "desc" }, take: 120 }),
        prisma.session.findMany({
          where: { userId: id },
          orderBy: { createdAt: "desc" },
          take: 30,
          select: {
            id: true,
            ipAddress: true,
            userAgent: true,
            workstation: true,
            createdAt: true,
            lastSeenAt: true,
            expiresAt: true,
            revokedAt: true,
            revokedReason: true,
          },
        }),
      ]);
      await writeAudit({
        user: req.authUser,
        action: AuditAction.SYSTEM,
        module: "users",
        targetId: id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        detail: "Histórico de usuário consultado.",
      });
      res.json({ user: toSafeUser(user), audit, access, sessions });
    }),
  );

  app.get(
    "/api/permissions",
    authenticateRequest,
    requirePermission("permissions.read"),
    asyncRoute(async (_req, res) => {
      res.json({
        roles: roleMatrix(),
        permissions: permissionCatalog,
      });
    }),
  );

  app.get(
    "/api/access-logs",
    authenticateRequest,
    requirePermission("audit.read"),
    asyncRoute(async (_req, res) => {
      const entries = await prisma.accessLog.findMany({ orderBy: { createdAt: "desc" }, take: 300 });
      res.json({ entries });
    }),
  );

  app.get(
    "/api/clients",
    authenticateRequest,
    requirePermission("clients.read"),
    asyncRoute(async (_req, res) => {
      const clients = await prisma.client.findMany({
        where: { deletedAt: null },
        orderBy: { customerName: "asc" },
        take: 500,
      });
      res.json({ clients });
    }),
  );

  app.post(
    "/api/clients",
    authenticateRequest,
    requirePermission("clients.write"),
    asyncRoute(async (req, res) => {
      const payload = clientSchema.parse(req.body);
      const client = await prisma.client.create({
        data: {
          customerName: payload.customerName.trim(),
          contactName: payload.contactName || undefined,
          cpfCnpj: payload.cpfCnpj || undefined,
          email: payload.email || undefined,
          phone: payload.phone || undefined,
          address: payload.address || undefined,
          city: payload.city || undefined,
          state: payload.state || undefined,
          lat: payload.lat ?? undefined,
          lng: payload.lng ?? undefined,
          payload: payload.payload ? jsonInput(payload.payload) : undefined,
        },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.CREATE,
        module: "clients",
        targetId: client.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        after: client,
      });
      res.status(201).json({ client });
    }),
  );

  app.put(
    "/api/clients/:id",
    authenticateRequest,
    requirePermission("clients.write"),
    asyncRoute(async (req, res) => {
      const id = String(req.params.id);
      const before = await prisma.client.findUnique({ where: { id } });
      if (!before) {
        res.status(404).json({ error: "Cliente não encontrado." });
        return;
      }
      const payload = clientSchema.partial().parse(req.body);
      const client = await prisma.client.update({
        where: { id },
        data: {
          ...(payload.customerName ? { customerName: payload.customerName.trim() } : {}),
          ...(payload.contactName !== undefined ? { contactName: payload.contactName || null } : {}),
          ...(payload.cpfCnpj !== undefined ? { cpfCnpj: payload.cpfCnpj || null } : {}),
          ...(payload.email !== undefined ? { email: payload.email || null } : {}),
          ...(payload.phone !== undefined ? { phone: payload.phone || null } : {}),
          ...(payload.address !== undefined ? { address: payload.address || null } : {}),
          ...(payload.city !== undefined ? { city: payload.city || null } : {}),
          ...(payload.state !== undefined ? { state: payload.state || null } : {}),
          ...(payload.lat !== undefined ? { lat: payload.lat } : {}),
          ...(payload.lng !== undefined ? { lng: payload.lng } : {}),
          ...(payload.payload !== undefined ? { payload: payload.payload === null ? Prisma.JsonNull : jsonInput(payload.payload) } : {}),
          version: { increment: 1 },
        },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.UPDATE,
        module: "clients",
        targetId: client.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        before,
        after: client,
      });
      res.json({ client });
    }),
  );

  app.get(
    "/api/service-orders",
    authenticateRequest,
    requirePermission("serviceOrders.read"),
    asyncRoute(async (_req, res) => {
      const serviceOrders = await prisma.serviceOrder.findMany({
        where: { deletedAt: null },
        orderBy: [{ scheduledAt: "asc" }, { updatedAt: "desc" }],
        take: 500,
      });
      res.json({ serviceOrders });
    }),
  );

  app.post(
    "/api/service-orders",
    authenticateRequest,
    requirePermission("serviceOrders.write"),
    asyncRoute(async (req, res) => {
      const payload = serviceOrderSchema.parse(req.body);
      const serviceOrder = await prisma.serviceOrder.create({
        data: {
          ...(payload.id ? { id: payload.id } : {}),
          eventId: payload.eventId || undefined,
          clientId: payload.clientId || undefined,
          driverId: payload.driverId || req.authUser?.id,
          status: payload.status || "aberta",
          scheduledAt: payload.scheduledAt ? new Date(payload.scheduledAt) : undefined,
          payload: payload.payload ? jsonInput(payload.payload) : undefined,
        },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.CREATE,
        module: "service-orders",
        targetId: serviceOrder.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        after: serviceOrder,
      });
      res.status(201).json({ serviceOrder });
    }),
  );

  app.put(
    "/api/service-orders/:id",
    authenticateRequest,
    requirePermission("serviceOrders.write"),
    asyncRoute(async (req, res) => {
      const id = String(req.params.id);
      const before = await prisma.serviceOrder.findUnique({ where: { id } });
      if (!before) {
        res.status(404).json({ error: "Ordem de serviço não encontrada." });
        return;
      }
      const payload = serviceOrderSchema.partial().parse(req.body);
      const serviceOrder = await prisma.serviceOrder.update({
        where: { id },
        data: {
          ...(payload.eventId !== undefined ? { eventId: payload.eventId || null } : {}),
          ...(payload.clientId !== undefined ? { clientId: payload.clientId || null } : {}),
          ...(payload.driverId !== undefined ? { driverId: payload.driverId || null } : {}),
          ...(payload.status ? { status: payload.status } : {}),
          ...(payload.scheduledAt !== undefined ? { scheduledAt: payload.scheduledAt ? new Date(payload.scheduledAt) : null } : {}),
          ...(payload.payload !== undefined ? { payload: payload.payload === null ? Prisma.JsonNull : jsonInput(payload.payload) } : {}),
          version: { increment: 1 },
        },
      });
      await writeAudit({
        user: req.authUser,
        action: AuditAction.UPDATE,
        module: "service-orders",
        targetId: serviceOrder.id,
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
        before,
        after: serviceOrder,
      });
      res.json({ serviceOrder });
    }),
  );

  app.get(
    "/api/offline/status",
    authenticateRequest,
    requirePermission("offline.sync"),
    asyncRoute(async (_req, res) => {
      res.json(await offlineStatus());
    }),
  );

  app.get(
    "/api/offline/queue",
    authenticateRequest,
    requirePermission("offline.sync"),
    asyncRoute(async (req, res) => {
      const limit = Number.parseInt(String(req.query.limit || "100"), 10);
      res.json({ items: await listOfflineQueue(Number.isFinite(limit) ? limit : 100) });
    }),
  );

  app.post(
    "/api/offline/queue",
    authenticateRequest,
    requirePermission("offline.queue"),
    asyncRoute(async (req, res) => {
      const parsed = offlineQueueBatchSchema.parse(Array.isArray(req.body) ? { items: req.body } : req.body);
      const result = await enqueueOfflineItems(parsed.items, req.authUser, {
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
      });
      res.status(202).json(result);
    }),
  );

  app.post(
    "/api/offline/sync",
    authenticateRequest,
    requirePermission("offline.sync"),
    asyncRoute(async (req, res) => {
      const queue = await processOfflineQueue(req.authUser, {
        ipAddress: req.ip,
        userAgent: requestUserAgent(req),
      });
      const snapshots = {
        import: await importSnapshots(req.authUser?.id),
        export: await exportSnapshot(req.authUser?.id),
      };
      res.json({ queue, snapshots, status: await offlineStatus() });
    }),
  );

  app.get(
    "/api/audit",
    authenticateRequest,
    requirePermission("audit.read"),
    asyncRoute(async (_req, res) => {
      const entries = await prisma.auditLog.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
      res.json({ entries });
    }),
  );

  app.get(
    "/api/sync/status",
    authenticateRequest,
    requirePermission("sync.export"),
    asyncRoute(async (_req, res) => {
      res.json(await syncStatus());
    }),
  );

  app.post(
    "/api/sync/export",
    authenticateRequest,
    requirePermission("sync.export"),
    asyncRoute(async (req, res) => {
      res.json(await exportSnapshot(req.authUser?.id));
    }),
  );

  app.post(
    "/api/sync/import",
    authenticateRequest,
    requirePermission("sync.import"),
    asyncRoute(async (req, res) => {
      res.json(await importSnapshots(req.authUser?.id));
    }),
  );

  app.get(
    "/api/sync/conflicts",
    authenticateRequest,
    requirePermission("sync.import"),
    asyncRoute(async (_req, res) => {
      const conflicts = await prisma.syncConflict.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
      res.json({ conflicts });
    }),
  );

  app.post(
    "/api/sync/conflicts/:id/resolve",
    authenticateRequest,
    requirePermission("sync.import"),
    asyncRoute(async (req, res) => {
      const resolution = z.enum(["accept_local", "accept_remote", "ignore"]).parse(req.body.resolution);
      await resolveConflict(String(req.params.id), resolution, req.authUser?.id);
      res.json({ ok: true });
    }),
  );

  app.use((error: unknown, req: Request, res: Response, _next: NextFunction) => {
    logger.error("Erro na API local", { error, path: req.path });
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: "Dados inválidos.", details: error.flatten() });
      return;
    }
    res.status(500).json({ error: error instanceof Error ? error.message : "Erro interno." });
  });

  const server = createServer(app);
  const host = configuredApiHost();
  const requestedPort = configuredApiPort(options);
  const port = await new Promise<number>((resolve, reject) => {
    server.once("error", reject);
    server.listen(requestedPort, host, () => {
      const address = server.address();
      if (!address || typeof address === "string") reject(new Error("Porta local inválida."));
      else resolve(address.port);
    });
  });

  logger.info("SannySystem backend iniciado", { host, port });

  return {
    app,
    server,
    host,
    port,
    close: () =>
      new Promise<void>((resolveClose, rejectClose) => {
        server.close((error) => (error ? rejectClose(error) : resolveClose()));
      }),
  };
}
