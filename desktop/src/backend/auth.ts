import { AccessAction, AuditAction, Role, Session, User, UserStatus } from "@prisma/client";
import { NextFunction, Request, Response } from "express";
import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { hostname } from "node:os";
import bcrypt from "bcryptjs";
import { prisma } from "./prisma";
import { hasPermission, permissionsForRole, roleLabels } from "./permissions";
import { writeAudit } from "./audit";
import { logger } from "./logger";

export type SafeUser = Pick<User, "id" | "login" | "name" | "email" | "role" | "status" | "mustChangePassword"> & {
  permissions: string[];
  roleLabel: string;
};

export type AuthenticatedRequest = Request & {
  authUser?: User;
  authSession?: Session;
  sessionId?: string;
  sessionTokenHash?: string;
};

type JwtPayload = {
  typ: "access";
  sid: string;
  sub: string;
  jti: string;
  login: string;
  email: string;
  role: Role;
  iat: number;
  exp: number;
};

type AuthTokens = {
  token: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: string;
  refreshExpiresAt: string;
  user: SafeUser;
};

const ACCESS_TOKEN_MINUTES = intEnv("SANNYSYSTEM_ACCESS_TOKEN_MINUTES", 15, 5, 240);
const REFRESH_TOKEN_DAYS = intEnv("SANNYSYSTEM_REFRESH_TOKEN_DAYS", 7, 1, 60);
const MAX_FAILED_LOGINS = intEnv("SANNYSYSTEM_MAX_FAILED_LOGINS", 5, 3, 20);
const LOCK_MINUTES = intEnv("SANNYSYSTEM_LOGIN_LOCK_MINUTES", 15, 1, 1440);

function intEnv(name: string, fallback: number, min: number, max: number): number {
  const parsed = Number.parseInt(process.env[name] || "", 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}

function jwtSecret(): string {
  return (
    process.env.SANNYSYSTEM_JWT_SECRET?.trim() ||
    process.env.SANNYSYSTEM_SESSION_SECRET?.trim() ||
    "dev-only-change-sannysystem-jwt-secret"
  );
}

function base64UrlJson(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function parseBase64UrlJson<T>(value: string): T {
  return JSON.parse(Buffer.from(value, "base64url").toString("utf-8")) as T;
}

function sign(input: string): string {
  return createHmac("sha256", jwtSecret()).update(input).digest("base64url");
}

function safeEquals(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function signJwt(payload: JwtPayload): string {
  const header = base64UrlJson({ alg: "HS256", typ: "JWT" });
  const body = base64UrlJson(payload);
  const signature = sign(`${header}.${body}`);
  return `${header}.${body}.${signature}`;
}

function verifyJwt(token: string, options: { allowExpired?: boolean } = {}): JwtPayload {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("JWT inválido.");
  const [header, body, signature] = parts;
  const expected = sign(`${header}.${body}`);
  if (!safeEquals(signature, expected)) throw new Error("JWT com assinatura inválida.");
  const parsedHeader = parseBase64UrlJson<{ alg?: string; typ?: string }>(header);
  if (parsedHeader.alg !== "HS256" || parsedHeader.typ !== "JWT") throw new Error("JWT com cabeçalho inválido.");
  const payload = parseBase64UrlJson<JwtPayload>(body);
  if (payload.typ !== "access") throw new Error("Token incompatível.");
  if (!options.allowExpired && payload.exp <= Math.floor(Date.now() / 1000)) throw new Error("JWT expirado.");
  return payload;
}

function createRefreshToken(): string {
  return randomBytes(48).toString("base64url");
}

function createAccessToken(user: User, sessionId: string, accessTokenId: string): { token: string; expiresAt: Date } {
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = new Date((now + ACCESS_TOKEN_MINUTES * 60) * 1000);
  const payload: JwtPayload = {
    typ: "access",
    sid: sessionId,
    sub: user.id,
    jti: accessTokenId,
    login: user.login,
    email: user.email,
    role: user.role,
    iat: now,
    exp: Math.floor(expiresAt.getTime() / 1000),
  };
  return { token: signJwt(payload), expiresAt };
}

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export function toSafeUser(user: User): SafeUser {
  return {
    id: user.id,
    login: user.login,
    name: user.name,
    email: user.email,
    role: user.role,
    status: user.status,
    mustChangePassword: user.mustChangePassword,
    permissions: permissionsForRole(user.role),
    roleLabel: roleLabels[user.role],
  };
}

async function writeAccessLog(input: {
  user?: Pick<User, "id" | "email" | "role"> | null;
  userEmail?: string;
  action: AccessAction;
  success: boolean;
  sessionId?: string;
  ipAddress?: string | null;
  userAgent?: string | null;
  message?: string;
}): Promise<void> {
  try {
    await prisma.accessLog.create({
      data: {
        userId: input.user?.id,
        userEmail: input.user?.email || input.userEmail,
        userRole: input.user?.role,
        action: input.action,
        success: input.success,
        sessionId: input.sessionId,
        ipAddress: input.ipAddress || undefined,
        userAgent: input.userAgent || undefined,
        workstation: hostname(),
        message: input.message,
      },
    });
  } catch (error) {
    logger.error("Falha ao registrar log de acesso", { error, input });
  }
}

function loginLocked(user: User): boolean {
  return Boolean(user.lockedUntil && user.lockedUntil > new Date());
}

async function registerFailedLogin(user: User | null, loginValue: string, ipAddress?: string, userAgent?: string): Promise<void> {
  if (user) {
    const failedLoginCount = user.failedLoginCount + 1;
    await prisma.user.update({
      where: { id: user.id },
      data: {
        failedLoginCount,
        lockedUntil: failedLoginCount >= MAX_FAILED_LOGINS ? new Date(Date.now() + LOCK_MINUTES * 60 * 1000) : null,
      },
    });
  }
  await writeAccessLog({
    user,
    userEmail: user?.email || loginValue,
    action: AccessAction.LOGIN_FAILURE,
    success: false,
    ipAddress,
    userAgent,
    message: "Login recusado.",
  });
}

export async function login(loginValue: string, password: string, ipAddress?: string, userAgent?: string): Promise<AuthTokens> {
  const normalizedLogin = loginValue.trim().toLowerCase();
  const user = await prisma.user.findFirst({
    where: {
      OR: [{ login: normalizedLogin }, { email: normalizedLogin }],
      deletedAt: null,
    },
  });

  if (!user || user.status === UserStatus.INATIVO || loginLocked(user)) {
    await registerFailedLogin(user, normalizedLogin, ipAddress, userAgent);
    await writeAudit({
      user,
      action: AuditAction.ACCESS_DENIED,
      module: "auth",
      ipAddress,
      userAgent,
      detail: user && loginLocked(user) ? "Usuário temporariamente bloqueado por tentativas inválidas." : `Login recusado para ${normalizedLogin}.`,
    });
    throw new Error("Usuário ou senha inválidos.");
  }

  const ok = await bcrypt.compare(password, user.passwordHash);
  if (!ok) {
    await registerFailedLogin(user, normalizedLogin, ipAddress, userAgent);
    await writeAudit({
      user,
      action: AuditAction.ACCESS_DENIED,
      module: "auth",
      ipAddress,
      userAgent,
      targetId: user.id,
      detail: "Senha inválida.",
    });
    throw new Error("Usuário ou senha inválidos.");
  }

  const refreshToken = createRefreshToken();
  const accessTokenId = randomBytes(24).toString("base64url");
  const refreshExpiresAt = new Date(Date.now() + REFRESH_TOKEN_DAYS * 24 * 60 * 60 * 1000);

  const session = await prisma.session.create({
    data: {
      tokenHash: hashToken(refreshToken),
      accessTokenId,
      userId: user.id,
      expiresAt: refreshExpiresAt,
      lastSeenAt: new Date(),
      ipAddress,
      userAgent,
      workstation: hostname(),
    },
  });
  const access = createAccessToken(user, session.id, accessTokenId);

  await prisma.user.update({
    where: { id: user.id },
    data: { lastLoginAt: new Date(), failedLoginCount: 0, lockedUntil: null },
  });
  await writeAudit({ user, action: AuditAction.LOGIN, module: "auth", targetId: user.id, ipAddress, userAgent });
  await writeAccessLog({
    user,
    action: AccessAction.LOGIN_SUCCESS,
    success: true,
    sessionId: session.id,
    ipAddress,
    userAgent,
    message: "Login realizado.",
  });

  return {
    token: access.token,
    accessToken: access.token,
    refreshToken,
    expiresAt: access.expiresAt.toISOString(),
    refreshExpiresAt: refreshExpiresAt.toISOString(),
    user: toSafeUser(user),
  };
}

export async function refreshSession(refreshToken: string, ipAddress?: string, userAgent?: string): Promise<AuthTokens> {
  const tokenHash = hashToken(refreshToken);
  const session = await prisma.session.findUnique({ where: { tokenHash }, include: { user: true } });
  if (!session || session.revokedAt || session.expiresAt < new Date() || session.user.status === UserStatus.INATIVO || session.user.deletedAt) {
    await writeAccessLog({
      user: session?.user,
      action: AccessAction.SESSION_EXPIRED,
      success: false,
      sessionId: session?.id,
      ipAddress,
      userAgent,
      message: "Refresh token expirado, revogado ou inválido.",
    });
    throw new Error("Sessão expirada. Faça login novamente.");
  }

  const nextRefreshToken = createRefreshToken();
  const accessTokenId = randomBytes(24).toString("base64url");
  const refreshExpiresAt = new Date(Date.now() + REFRESH_TOKEN_DAYS * 24 * 60 * 60 * 1000);
  const access = createAccessToken(session.user, session.id, accessTokenId);

  await prisma.session.update({
    where: { id: session.id },
    data: {
      tokenHash: hashToken(nextRefreshToken),
      accessTokenId,
      expiresAt: refreshExpiresAt,
      lastSeenAt: new Date(),
      ipAddress,
      userAgent,
      workstation: hostname(),
    },
  });
  await writeAudit({
    user: session.user,
    action: AuditAction.TOKEN_REFRESH,
    module: "auth",
    targetId: session.id,
    ipAddress,
    userAgent,
    detail: "Sessão renovada por refresh token.",
  });
  await writeAccessLog({
    user: session.user,
    action: AccessAction.TOKEN_REFRESH,
    success: true,
    sessionId: session.id,
    ipAddress,
    userAgent,
    message: "Sessão renovada.",
  });

  return {
    token: access.token,
    accessToken: access.token,
    refreshToken: nextRefreshToken,
    expiresAt: access.expiresAt.toISOString(),
    refreshExpiresAt: refreshExpiresAt.toISOString(),
    user: toSafeUser(session.user),
  };
}

export async function authenticateRequest(req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> {
  const header = req.header("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length).trim() : "";
  if (!token) {
    res.status(401).json({ error: "Login obrigatório." });
    return;
  }

  let payload: JwtPayload;
  try {
    payload = verifyJwt(token);
  } catch (error) {
    let expiredPayload: JwtPayload | null = null;
    try {
      expiredPayload = verifyJwt(token, { allowExpired: true });
    } catch {
      // Token malformado: não há sessão confiável para registrar.
    }
    await writeAccessLog({
      action: AccessAction.SESSION_EXPIRED,
      success: false,
      sessionId: expiredPayload?.sid,
      ipAddress: req.ip,
      userAgent: req.header("user-agent"),
      message: error instanceof Error ? error.message : "JWT inválido.",
    });
    res.status(401).json({ error: "Sessão expirada. Faça login novamente." });
    return;
  }

  const session = await prisma.session.findUnique({ where: { id: payload.sid }, include: { user: true } });
  if (
    !session ||
    session.accessTokenId !== payload.jti ||
    session.revokedAt ||
    session.expiresAt < new Date() ||
    session.user.status === UserStatus.INATIVO ||
    session.user.deletedAt
  ) {
    await writeAccessLog({
      user: session?.user,
      action: AccessAction.ACCESS_DENIED,
      success: false,
      sessionId: payload.sid,
      ipAddress: req.ip,
      userAgent: req.header("user-agent"),
      message: "Sessão revogada, expirada ou incompatível.",
    });
    res.status(401).json({ error: "Sessão expirada. Faça login novamente." });
    return;
  }

  await prisma.session.update({
    where: { id: session.id },
    data: {
      lastSeenAt: new Date(),
      ipAddress: req.ip,
      userAgent: req.header("user-agent"),
      workstation: hostname(),
    },
  });
  req.authUser = session.user;
  req.authSession = session;
  req.sessionId = session.id;
  req.sessionTokenHash = session.tokenHash;
  next();
}

export function requirePermission(permission: string) {
  return async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    const user = req.authUser;
    if (!user) {
      res.status(401).json({ error: "Login obrigatório." });
      return;
    }
    if (!hasPermission(user.role as Role, permission)) {
      await writeAudit({
        user,
        action: AuditAction.ACCESS_DENIED,
        module: "permissions",
        targetId: permission,
        ipAddress: req.ip,
        userAgent: req.header("user-agent"),
      });
      await writeAccessLog({
        user,
        action: AccessAction.ACCESS_DENIED,
        success: false,
        sessionId: req.sessionId,
        ipAddress: req.ip,
        userAgent: req.header("user-agent"),
        message: `Permissão negada: ${permission}.`,
      });
      res.status(403).json({ error: "Perfil sem permissão para esta ação." });
      return;
    }
    next();
  };
}

export async function logout(req: AuthenticatedRequest): Promise<void> {
  if (req.sessionId) {
    await prisma.session.updateMany({
      where: { id: req.sessionId },
      data: { revokedAt: new Date(), revokedReason: "logout" },
    });
  } else if (req.sessionTokenHash) {
    await prisma.session.updateMany({
      where: { tokenHash: req.sessionTokenHash },
      data: { revokedAt: new Date(), revokedReason: "logout" },
    });
  }
  if (req.authUser) {
    await writeAudit({
      user: req.authUser,
      action: AuditAction.LOGOUT,
      module: "auth",
      targetId: req.authUser.id,
      ipAddress: req.ip,
      userAgent: req.header("user-agent"),
    });
    await writeAccessLog({
      user: req.authUser,
      action: AccessAction.LOGOUT,
      success: true,
      sessionId: req.sessionId,
      ipAddress: req.ip,
      userAgent: req.header("user-agent"),
      message: "Logout realizado.",
    });
  }
}
