import { createLogger, format, transports } from "winston";
import { join } from "node:path";
import { ensureRuntimeFolders } from "./paths";

const { directories } = ensureRuntimeFolders();
const logsDir = directories.logsDir;

export const logger = createLogger({
  level: process.env.SANNYSYSTEM_LOG_LEVEL || "info",
  format: format.combine(format.timestamp(), format.errors({ stack: true }), format.json()),
  transports: [
    new transports.File({ filename: join(logsDir, "sannysystem.log"), maxsize: 5 * 1024 * 1024, maxFiles: 5 }),
    new transports.File({ filename: join(logsDir, "audit-errors.log"), level: "error", maxsize: 5 * 1024 * 1024, maxFiles: 3 }),
  ],
});

if (process.env.NODE_ENV !== "production") {
  logger.add(new transports.Console({ format: format.simple() }));
}
