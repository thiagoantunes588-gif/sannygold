const recoveryParams = new URLSearchParams(window.location.search);
const reason = recoveryParams.get("reason") || "O sistema abriu em modo de recuperação.";
const reasonNode = document.getElementById("recoveryReason") as HTMLElement;
const versionNode = document.getElementById("recoveryVersion") as HTMLElement;
const diagnosticsNode = document.getElementById("diagnosticsOutput") as HTMLElement;

reasonNode.textContent = reason;

function renderRecoveryJson(value: unknown): void {
  diagnosticsNode.textContent = JSON.stringify(value, null, 2);
}

async function loadDiagnostics(): Promise<void> {
  diagnosticsNode.textContent = "Carregando...";
  renderRecoveryJson(await window.sannyDesktop?.getDiagnostics());
}

window.sannyDesktop?.getAppInfo().then((info) => {
  versionNode.textContent = `Versão ${String(info.version || "")}`;
}).catch(() => undefined);

document.getElementById("openLogsButton")?.addEventListener("click", () => {
  window.sannyDesktop?.openLogsFolder();
});

document.getElementById("openDataButton")?.addEventListener("click", () => {
  window.sannyDesktop?.openDataFolder();
});

document.getElementById("restartNormalButton")?.addEventListener("click", () => {
  window.sannyDesktop?.restartNormal();
});

document.getElementById("restartSafeButton")?.addEventListener("click", () => {
  window.sannyDesktop?.restartSafeMode();
});

document.getElementById("reloadDiagnosticsButton")?.addEventListener("click", () => {
  loadDiagnostics().catch((error) => {
    diagnosticsNode.textContent = error instanceof Error ? error.message : "Falha ao carregar diagnóstico.";
  });
});

loadDiagnostics().catch((error) => {
  diagnosticsNode.textContent = error instanceof Error ? error.message : "Falha ao carregar diagnóstico.";
});
