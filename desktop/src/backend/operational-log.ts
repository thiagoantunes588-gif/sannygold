import { LogLevel, Prisma } from "@prisma/client";
import { hostname } from "node:os";
import { prisma } from "./prisma";
import { logger } from "./logger";

export async function writeOperationalLog(input: {
  level: LogLevel;
  module: string;
  message: string;
  metadata?: unknown;
}): Promise<void> {
  try {
    await prisma.operationalLog.create({
      data: {
        level: input.level,
        module: input.module,
        message: input.message,
        metadata:
          input.metadata === undefined
            ? undefined
            : (JSON.parse(JSON.stringify(input.metadata)) as Prisma.InputJsonValue),
        workstation: hostname(),
      },
    });
  } catch (error) {
    logger.warn("Falha ao persistir log operacional", {
      module: input.module,
      message: input.message,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
