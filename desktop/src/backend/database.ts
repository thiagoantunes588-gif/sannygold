import { PrismaClient } from "@prisma/client";
import { createHash } from "node:crypto";
import { URL } from "node:url";
import { loadEnvironment } from "./env";
import { logger } from "./logger";

loadEnvironment();

type DatabaseProvider = "supabase" | "neon" | "railway" | "custom-postgres" | "local-postgres";

export type DatabaseConnectionConfig = {
  url: string;
  source: string;
  provider: DatabaseProvider;
  host: string;
  database: string;
  sslEnabled: boolean;
  poolingEnabled: boolean;
  connectionLimit: number;
  poolTimeoutSeconds: number;
  connectTimeoutSeconds: number;
  fingerprint: string;
};

const FALLBACK_URL_ENV_NAMES = [
  "DATABASE_URL",
  "SANNYSYSTEM_DATABASE_URL",
  "POSTGRES_PRISMA_URL",
  "POSTGRES_URL",
  "POSTGRES_URL_NON_POOLING",
  "SUPABASE_DATABASE_URL",
  "NEON_DATABASE_URL",
  "RAILWAY_DATABASE_URL",
];

const DEFAULT_CONNECTION_LIMIT = 10;
const DEFAULT_POOL_TIMEOUT_SECONDS = 30;
const DEFAULT_CONNECT_TIMEOUT_SECONDS = 10;

function requiredIntEnv(name: string, fallback: number, min: number, max: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}

function providerFromHost(host: string): DatabaseProvider {
  const lowerHost = host.toLowerCase();
  if (lowerHost.includes("supabase")) return "supabase";
  if (lowerHost.includes("neon.tech") || lowerHost.includes("neon")) return "neon";
  if (lowerHost.includes("railway")) return "railway";
  if (["localhost", "127.0.0.1", "::1"].includes(lowerHost)) return "local-postgres";
  return "custom-postgres";
}

function firstConfiguredUrl(): { source: string; url: string } {
  for (const name of FALLBACK_URL_ENV_NAMES) {
    const value = process.env[name]?.trim();
    if (value) return { source: name, url: value };
  }
  throw new Error(
    `Nenhuma URL PostgreSQL configurada. Defina uma destas variaveis: ${FALLBACK_URL_ENV_NAMES.join(", ")}.`,
  );
}

function shouldForceSsl(provider: DatabaseProvider): boolean {
  if (process.env.SANNYSYSTEM_DB_SSLMODE) return false;
  return provider === "supabase" || provider === "neon" || provider === "railway";
}

function normalizeDatabaseUrl(rawUrl: string, provider: DatabaseProvider): string {
  const parsed = new URL(rawUrl);
  const connectionLimit = requiredIntEnv("SANNYSYSTEM_DB_POOL_MAX", DEFAULT_CONNECTION_LIMIT, 1, 50);
  const poolTimeout = requiredIntEnv("SANNYSYSTEM_DB_POOL_TIMEOUT_SECONDS", DEFAULT_POOL_TIMEOUT_SECONDS, 1, 120);
  const connectTimeout = requiredIntEnv("SANNYSYSTEM_DB_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS, 1, 60);
  const sslMode = process.env.SANNYSYSTEM_DB_SSLMODE?.trim() || (shouldForceSsl(provider) ? "require" : "");

  if (!parsed.searchParams.has("connection_limit")) parsed.searchParams.set("connection_limit", String(connectionLimit));
  if (!parsed.searchParams.has("pool_timeout")) parsed.searchParams.set("pool_timeout", String(poolTimeout));
  if (!parsed.searchParams.has("connect_timeout")) parsed.searchParams.set("connect_timeout", String(connectTimeout));
  if (sslMode && !parsed.searchParams.has("sslmode")) parsed.searchParams.set("sslmode", sslMode);

  return parsed.toString();
}

function fingerprint(value: string): string {
  return createHash("sha256").update(value).digest("hex").slice(0, 16);
}

export function resolveDatabaseConfig(): DatabaseConnectionConfig {
  const selected = firstConfiguredUrl();
  const initialUrl = new URL(selected.url);
  const provider = providerFromHost(initialUrl.hostname);
  const normalizedUrl = normalizeDatabaseUrl(selected.url, provider);
  const normalized = new URL(normalizedUrl);

  return {
    url: normalizedUrl,
    source: selected.source,
    provider,
    host: normalized.hostname,
    database: normalized.pathname.replace(/^\//, ""),
    sslEnabled: normalized.searchParams.get("sslmode") === "require",
    poolingEnabled: true,
    connectionLimit: Number.parseInt(normalized.searchParams.get("connection_limit") || String(DEFAULT_CONNECTION_LIMIT), 10),
    poolTimeoutSeconds: Number.parseInt(normalized.searchParams.get("pool_timeout") || String(DEFAULT_POOL_TIMEOUT_SECONDS), 10),
    connectTimeoutSeconds: Number.parseInt(normalized.searchParams.get("connect_timeout") || String(DEFAULT_CONNECT_TIMEOUT_SECONDS), 10),
    fingerprint: fingerprint(`${normalized.hostname}/${normalized.pathname}/${normalized.username}`),
  };
}

export function resolveMigrationDatabaseUrl(): string {
  const directUrl =
    process.env.SANNYSYSTEM_DIRECT_DATABASE_URL?.trim() ||
    process.env.DIRECT_URL?.trim() ||
    process.env.POSTGRES_URL_NON_POOLING?.trim();
  if (!directUrl) return resolveDatabaseConfig().url;
  const provider = providerFromHost(new URL(directUrl).hostname);
  return normalizeDatabaseUrl(directUrl, provider);
}

export function createPrismaClient(): PrismaClient {
  const config = resolveDatabaseConfig();
  return new PrismaClient({
    datasources: {
      db: {
        url: config.url,
      },
    },
    log: process.env.NODE_ENV === "development" ? ["warn", "error"] : ["error"],
  });
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export async function connectWithRetry(client: PrismaClient, attempts = 5): Promise<void> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await client.$connect();
      await client.$queryRaw`SELECT 1`;
      return;
    } catch (error) {
      lastError = error;
      logger.warn("Falha ao conectar ao PostgreSQL, tentando novamente", {
        attempt,
        attempts,
        message: error instanceof Error ? error.message : String(error),
      });
      await wait(Math.min(1000 * attempt, 5000));
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

export async function databaseHealth(client: PrismaClient): Promise<Record<string, unknown>> {
  const config = resolveDatabaseConfig();
  const startedAt = Date.now();
  try {
    await client.$queryRaw`SELECT 1`;
    return {
      ok: true,
      latencyMs: Date.now() - startedAt,
      provider: config.provider,
      source: config.source,
      host: config.host,
      database: config.database,
      sslEnabled: config.sslEnabled,
      poolingEnabled: config.poolingEnabled,
      connectionLimit: config.connectionLimit,
      poolTimeoutSeconds: config.poolTimeoutSeconds,
      connectTimeoutSeconds: config.connectTimeoutSeconds,
      fingerprint: config.fingerprint,
    };
  } catch (error) {
    return {
      ok: false,
      provider: config.provider,
      source: config.source,
      host: config.host,
      database: config.database,
      message: error instanceof Error ? error.message : String(error),
      fingerprint: config.fingerprint,
    };
  }
}

export function sanitizedDatabaseConfig(): Record<string, unknown> {
  const config = resolveDatabaseConfig();
  return {
    provider: config.provider,
    source: config.source,
    host: config.host,
    database: config.database,
    sslEnabled: config.sslEnabled,
    poolingEnabled: config.poolingEnabled,
    connectionLimit: config.connectionLimit,
    poolTimeoutSeconds: config.poolTimeoutSeconds,
    connectTimeoutSeconds: config.connectTimeoutSeconds,
    fingerprint: config.fingerprint,
  };
}
