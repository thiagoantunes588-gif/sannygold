import { app, BrowserWindow, ipcMain, shell } from "electron";
import log from "electron-log";
import { autoUpdater } from "electron-updater";
import path from "node:path";
import { createBackendServer } from "./backend/server";
import { logger } from "./backend/logger";
import { buildStartupDiagnostics } from "./backend/diagnostics";
import { validateRuntimeLayout } from "./backend/paths";

let mainWindow: BrowserWindow | null = null;
let splashWindow: BrowserWindow | null = null;
let backend: Awaited<ReturnType<typeof createBackendServer>> | null = null;
let lastMode: "normal" | "recovery" = "normal";

const safeMode =
  app.commandLine.hasSwitch("safe-mode") ||
  ["1", "true", "yes", "on"].includes(String(process.env.SANNYSYSTEM_SAFE_MODE || "").toLowerCase());
const recoveryMode =
  app.commandLine.hasSwitch("recovery") ||
  app.commandLine.hasSwitch("recovery-mode") ||
  ["1", "true", "yes", "on"].includes(String(process.env.SANNYSYSTEM_RECOVERY_MODE || "").toLowerCase());

if (safeMode) {
  process.env.SANNYSYSTEM_AUTO_MIGRATE = "false";
  process.env.SANNYSYSTEM_BACKUP_ENABLED = "false";
}

function isPackagedOrConfiguredForUpdates(): boolean {
  return app.isPackaged || Boolean(process.env.SANNYSYSTEM_UPDATE_URL?.trim());
}

function iconPath(): string {
  const iconsDir = app.isPackaged
    ? path.join(process.resourcesPath, "icons")
    : path.join(__dirname, "..", "resources", "icons");
  return path.join(iconsDir, process.platform === "win32" ? "icon.ico" : "icon.png");
}

function rendererPath(fileName: string): string {
  return path.join(__dirname, "renderer", fileName);
}

function updateStatus(status: string, detail?: unknown): void {
  logger.info("Atualizador", { status, detail });
  mainWindow?.webContents.send("updates:status", { status, detail });
}

function startupStatus(status: string, detail?: unknown): void {
  logger.info("Inicialização", { status, detail });
  splashWindow?.webContents.send("startup:status", { status, detail });
  mainWindow?.webContents.send("startup:status", { status, detail });
}

function configureUpdates(): void {
  autoUpdater.logger = log;
  autoUpdater.autoDownload = true;
  const updateUrl = process.env.SANNYSYSTEM_UPDATE_URL?.trim();
  if (updateUrl) {
    autoUpdater.setFeedURL({ provider: "generic", url: updateUrl });
  }

  autoUpdater.on("checking-for-update", () => updateStatus("checking"));
  autoUpdater.on("update-available", (info) => updateStatus("available", info));
  autoUpdater.on("update-not-available", (info) => updateStatus("not_available", info));
  autoUpdater.on("download-progress", (progress) => updateStatus("downloading", progress));
  autoUpdater.on("update-downloaded", (info) => updateStatus("downloaded", info));
  autoUpdater.on("error", (error) => updateStatus("error", error.message));

  ipcMain.handle("updates:check", async () => {
    if (safeMode) return { skipped: true, reason: "Safe mode ativo. Atualizações automáticas desativadas." };
    if (!isPackagedOrConfiguredForUpdates()) {
      return { skipped: true, reason: "Atualização automática só roda com app empacotado ou SANNYSYSTEM_UPDATE_URL definido." };
    }
    await autoUpdater.checkForUpdates();
    return { ok: true };
  });

  ipcMain.handle("updates:install", () => {
    autoUpdater.quitAndInstall(false, true);
    return { ok: true };
  });
}

function relaunchWith(extraArgs: string[]): Record<string, boolean> {
  const existingArgs = process.argv
    .slice(1)
    .filter((arg) => !["--safe-mode", "--recovery", "--recovery-mode"].includes(arg));
  app.relaunch({ args: [...existingArgs, ...extraArgs] });
  app.exit(0);
  return { ok: true };
}

function configureAppIpc(): void {
  ipcMain.handle("app:info", () => ({
    name: app.getName(),
    version: app.getVersion(),
    isPackaged: app.isPackaged,
    platform: process.platform,
    safeMode,
    recoveryMode: lastMode === "recovery" || recoveryMode,
  }));

  ipcMain.handle("app:diagnostics", () => buildStartupDiagnostics({ safeMode, recoveryMode: lastMode === "recovery" || recoveryMode }));

  ipcMain.handle("app:open-logs", async () => {
    const logsDir = validateRuntimeLayout().layout.directories.logsDir;
    await shell.openPath(logsDir);
    return { ok: true, path: logsDir };
  });

  ipcMain.handle("app:open-data-folder", async () => {
    const dataDir = validateRuntimeLayout().layout.dataDir;
    await shell.openPath(dataDir);
    return { ok: true, path: dataDir };
  });

  ipcMain.handle("app:restart-normal", () => relaunchWith([]));
  ipcMain.handle("app:restart-safe-mode", () => relaunchWith(["--safe-mode"]));
  ipcMain.handle("app:restart-recovery-mode", () => relaunchWith(["--recovery"]));
}

function configureProcessLogging(): void {
  log.initialize();
  log.info("SannySystem desktop iniciando", {
    version: app.getVersion(),
    packaged: app.isPackaged,
    safeMode,
    recoveryMode,
  });

  process.on("uncaughtException", (error) => {
    log.error("Erro não tratado", error);
    logger.error("Erro não tratado no processo principal", { error });
  });

  process.on("unhandledRejection", (reason) => {
    log.error("Promise rejeitada sem tratamento", reason);
    logger.error("Promise rejeitada sem tratamento no processo principal", { reason });
  });
}

async function createSplashWindow(): Promise<void> {
  splashWindow = new BrowserWindow({
    width: 500,
    height: 320,
    resizable: false,
    movable: true,
    frame: false,
    show: false,
    title: "SannySystem",
    backgroundColor: "#111827",
    icon: iconPath(),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  await splashWindow.loadFile(rendererPath("splash.html"));
  splashWindow.show();
}

async function createMainWindow(options: { mode: "normal"; port: number } | { mode: "recovery"; reason: string }): Promise<void> {
  lastMode = options.mode;
  mainWindow = new BrowserWindow({
    width: options.mode === "recovery" ? 1120 : 1280,
    height: options.mode === "recovery" ? 760 : 820,
    minWidth: 980,
    minHeight: 640,
    show: false,
    title: "SannySystem",
    backgroundColor: "#07090e",
    icon: iconPath(),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  if (options.mode === "recovery") {
    await mainWindow.loadFile(rendererPath("recovery.html"), {
      query: {
        reason: options.reason,
        version: app.getVersion(),
        safeMode: String(safeMode),
      },
    });
  } else {
    await mainWindow.loadFile(rendererPath("index.html"), {
      query: {
        apiBase: `http://127.0.0.1:${options.port}/api`,
        version: app.getVersion(),
        safeMode: String(safeMode),
      },
    });
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function closeSplashWindow(): void {
  if (!splashWindow) return;
  splashWindow.close();
  splashWindow = null;
}

async function launchApplication(): Promise<void> {
  await createSplashWindow();

  if (recoveryMode) {
    startupStatus("recovery", "Abrindo modo de recuperação.");
    await createMainWindow({ mode: "recovery", reason: "Modo de recuperação solicitado na inicialização." });
    closeSplashWindow();
    return;
  }

  try {
    startupStatus("setup", "Validando pastas locais e Dropbox.");
    const setup = validateRuntimeLayout();
    if (!setup.ready) logger.warn("Setup inicial com pendências", { issues: setup.issues });

    startupStatus("database", safeMode ? "Conectando PostgreSQL em safe mode." : "Conectando PostgreSQL e aplicando migrations.");
    backend = await createBackendServer({ safeMode });

    startupStatus("ready", "Abrindo aplicação.");
    await createMainWindow({ mode: "normal", port: backend.port });
    closeSplashWindow();

    if (!safeMode && isPackagedOrConfiguredForUpdates()) {
      setTimeout(() => {
        autoUpdater.checkForUpdates().catch((error) => updateStatus("error", error.message));
      }, 8000);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logger.error("Falha ao iniciar SannySystem. Abrindo recovery mode.", { error });
    startupStatus("recovery", message);
    await createMainWindow({ mode: "recovery", reason: message });
    closeSplashWindow();
  }
}

configureProcessLogging();
configureUpdates();
configureAppIpc();

app.whenReady().then(launchApplication).catch((error) => {
  logger.error("Falha crítica ao iniciar SannySystem", { error });
  app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length > 0) return;
  if (backend && lastMode === "normal") {
    createMainWindow({ mode: "normal", port: backend.port }).catch((error) => logger.error("Falha ao reabrir janela", { error }));
    return;
  }
  createMainWindow({ mode: "recovery", reason: "Aplicação reaberta sem backend ativo." }).catch((error) =>
    logger.error("Falha ao reabrir recovery mode", { error }),
  );
});

app.on("before-quit", async () => {
  if (backend) {
    await backend.close().catch((error) => logger.error("Falha ao encerrar backend local", { error }));
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
