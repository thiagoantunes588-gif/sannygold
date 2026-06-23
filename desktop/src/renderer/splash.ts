const statusNode = document.getElementById("splashStatus");

window.sannyDesktop?.getAppInfo().then((info) => {
  if (!statusNode) return;
  statusNode.textContent = `Versão ${String(info.version || "")}`;
}).catch(() => undefined);

window.sannyDesktop?.onStartupStatus((payload) => {
  if (!statusNode) return;
  const value = payload as { status?: string; detail?: unknown };
  statusNode.textContent = String(value.detail || value.status || "Iniciando...");
});
