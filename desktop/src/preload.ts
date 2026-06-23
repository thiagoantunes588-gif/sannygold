import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("sannyDesktop", {
  platform: process.platform,
  versions: process.versions,
  getAppInfo: () => ipcRenderer.invoke("app:info"),
  getDiagnostics: () => ipcRenderer.invoke("app:diagnostics"),
  openLogsFolder: () => ipcRenderer.invoke("app:open-logs"),
  openDataFolder: () => ipcRenderer.invoke("app:open-data-folder"),
  restartNormal: () => ipcRenderer.invoke("app:restart-normal"),
  restartSafeMode: () => ipcRenderer.invoke("app:restart-safe-mode"),
  restartRecoveryMode: () => ipcRenderer.invoke("app:restart-recovery-mode"),
  checkForUpdates: () => ipcRenderer.invoke("updates:check"),
  installUpdate: () => ipcRenderer.invoke("updates:install"),
  onStartupStatus: (callback: (payload: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, payload: unknown) => callback(payload);
    ipcRenderer.on("startup:status", listener);
    return () => ipcRenderer.removeListener("startup:status", listener);
  },
  onUpdateStatus: (callback: (payload: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, payload: unknown) => callback(payload);
    ipcRenderer.on("updates:status", listener);
    return () => ipcRenderer.removeListener("updates:status", listener);
  },
});
