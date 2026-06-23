import { AuditAction, Role, User } from "@prisma/client";
import { hostname } from "node:os";
import { prisma } from "./prisma";
import { logger } from "./logger";

export type AuditActor = Pick<User, "id" | "email" | "role"> | null | undefined;

type AuditInput = {
  user?: AuditActor;
  action: AuditAction;
  module: string;
  targetId?: string | null;
  ipAddress?: string | null;
  userAgent?: string | null;
  requestId?: string | null;
  before?: unknown;
  after?: unknown;
  detail?: string;
};

export async function writeAudit(input: AuditInput): Promise<void> {
  try {
    await prisma.auditLog.create({
      data: {
        userId: input.user?.id,
        userEmail: input.user?.email,
        userRole: input.user?.role as Role | undefined,
        action: input.action,
        module: input.module,
        targetId: input.targetId || undefined,
        ipAddress: input.ipAddress || undefined,
        userAgent: input.userAgent || undefined,
        workstation: hostname(),
        requestId: input.requestId || undefined,
        before: input.before === undefined ? undefined : JSON.parse(JSON.stringify(input.before)),
        after: input.after === undefined ? undefined : JSON.parse(JSON.stringify(input.after)),
        detail: input.detail,
      },
    });
  } catch (error) {
    logger.error("Falha ao registrar auditoria", { error, input });
  }
}
