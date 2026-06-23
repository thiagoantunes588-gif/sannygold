type DesktopBridge = {
  getAppInfo: () => Promise<Record<string, unknown>>;
  getDiagnostics: () => Promise<Record<string, unknown>>;
  openLogsFolder: () => Promise<unknown>;
  openDataFolder: () => Promise<unknown>;
  restartNormal: () => Promise<unknown>;
  restartSafeMode: () => Promise<unknown>;
  restartRecoveryMode: () => Promise<unknown>;
  checkForUpdates: () => Promise<unknown>;
  installUpdate: () => Promise<unknown>;
  onStartupStatus: (callback: (payload: unknown) => void) => () => void;
  onUpdateStatus: (callback: (payload: unknown) => void) => () => void;
};

interface Window {
  sannyDesktop?: DesktopBridge;
}

const params = new URLSearchParams(window.location.search);
const apiBase = params.get("apiBase") || "http://127.0.0.1:3000/api";
let token = window.localStorage.getItem("sannysystem.token") || "";
let refreshToken = window.localStorage.getItem("sannysystem.refreshToken") || "";
let currentView = "dashboard";
let refreshTimer: number | undefined;
let offlineSyncTimer: number | undefined;
let idleLogoutTimer: number | undefined;
let currentOfflineServiceOrderId = "";

const IDLE_LOGOUT_MINUTES = 30;
const IDLE_LOGOUT_MS = IDLE_LOGOUT_MINUTES * 60 * 1000;

type DashboardOperations = {
  serviceOrders?: {
    total?: number;
    active?: number;
    delayed?: number;
    latest?: Array<Record<string, unknown>>;
  };
  events?: {
    today?: number;
    future?: number;
    simultaneous?: number;
  };
  equipment?: {
    total?: number;
    available?: number;
    inUse?: number;
    maintenance?: number;
    other?: number;
  };
  vehicles?: {
    active?: number;
    total?: number;
  };
  warehouse?: {
    total?: number;
    lowStock?: number;
  };
  financial?: {
    openCount?: number;
    openAmount?: number;
  };
  sync?: {
    openConflicts?: number;
    lastSnapshot?: Record<string, unknown> | null;
  };
  offline?: {
    pending?: number;
    conflicts?: number;
  };
};

const elements = {
  loginView: document.getElementById("loginView") as HTMLElement,
  appView: document.getElementById("appView") as HTMLElement,
  loadingScreen: document.getElementById("loadingScreen") as HTMLElement,
  loadingMessage: document.getElementById("loadingMessage") as HTMLElement,
  appVersion: document.getElementById("appVersion") as HTMLElement,
  safeModePill: document.getElementById("safeModePill") as HTMLElement,
  loginForm: document.getElementById("loginForm") as HTMLFormElement,
  loginEmail: document.getElementById("loginEmail") as HTMLInputElement,
  loginPassword: document.getElementById("loginPassword") as HTMLInputElement,
  loginMessage: document.getElementById("loginMessage") as HTMLElement,
  sessionBox: document.getElementById("sessionBox") as HTMLElement,
  viewTitle: document.getElementById("viewTitle") as HTMLElement,
  viewSubtitle: document.getElementById("viewSubtitle") as HTMLElement,
  globalSearch: document.getElementById("globalSearch") as HTMLInputElement,
  connectionPill: document.getElementById("connectionPill") as HTMLElement,
  syncPill: document.getElementById("syncPill") as HTMLElement,
  roleTopbar: document.getElementById("roleTopbar") as HTMLElement,
  healthOutput: document.getElementById("healthOutput") as HTMLElement,
  dropboxMetric: document.getElementById("dropboxMetric") as HTMLElement,
  conflictMetric: document.getElementById("conflictMetric") as HTMLElement,
  activeOrdersMetric: document.getElementById("activeOrdersMetric") as HTMLElement,
  dashboardQueueMetric: document.getElementById("dashboardQueueMetric") as HTMLElement,
  eventTodayMetric: document.getElementById("eventTodayMetric") as HTMLElement,
  futureEventsMetric: document.getElementById("futureEventsMetric") as HTMLElement,
  simultaneousEventsMetric: document.getElementById("simultaneousEventsMetric") as HTMLElement,
  equipmentAvailableMetric: document.getElementById("equipmentAvailableMetric") as HTMLElement,
  equipmentInUseMetric: document.getElementById("equipmentInUseMetric") as HTMLElement,
  equipmentMaintenanceMetric: document.getElementById("equipmentMaintenanceMetric") as HTMLElement,
  vehicleActiveMetric: document.getElementById("vehicleActiveMetric") as HTMLElement,
  financialPendingMetric: document.getElementById("financialPendingMetric") as HTMLElement,
  stockRiskMetric: document.getElementById("stockRiskMetric") as HTMLElement,
  dashboardEquipmentGrid: document.getElementById("dashboardEquipmentGrid") as HTMLElement,
  dashboardTimeline: document.getElementById("dashboardTimeline") as HTMLElement,
  dashboardAlerts: document.getElementById("dashboardAlerts") as HTMLElement,
  dashboardOrdersTable: document.getElementById("dashboardOrdersTable") as HTMLElement,
  todayLabel: document.getElementById("todayLabel") as HTMLElement,
  offlineConnectionMetric: document.getElementById("offlineConnectionMetric") as HTMLElement,
  offlineLocalMetric: document.getElementById("offlineLocalMetric") as HTMLElement,
  offlineServerMetric: document.getElementById("offlineServerMetric") as HTMLElement,
  offlineLastSyncMetric: document.getElementById("offlineLastSyncMetric") as HTMLElement,
  offlineServiceOrder: document.getElementById("offlineServiceOrder") as HTMLSelectElement,
  offlineTitle: document.getElementById("offlineTitle") as HTMLInputElement,
  offlineChecklist: document.getElementById("offlineChecklist") as HTMLTextAreaElement,
  offlineNotes: document.getElementById("offlineNotes") as HTMLTextAreaElement,
  offlinePhotoInput: document.getElementById("offlinePhotoInput") as HTMLInputElement,
  signatureCanvas: document.getElementById("signatureCanvas") as HTMLCanvasElement,
  signatureName: document.getElementById("signatureName") as HTMLInputElement,
  offlineMessage: document.getElementById("offlineMessage") as HTMLElement,
  offlineQueueList: document.getElementById("offlineQueueList") as HTMLElement,
  offlineConflictLog: document.getElementById("offlineConflictLog") as HTMLElement,
  syncOutput: document.getElementById("syncOutput") as HTMLElement,
  conflictList: document.getElementById("conflictList") as HTMLElement,
  updateStatus: document.getElementById("updateStatus") as HTMLElement,
  appInfoOutput: document.getElementById("appInfoOutput") as HTMLElement,
  clientsTable: document.getElementById("clientsTable") as HTMLElement,
  usersTable: document.getElementById("usersTable") as HTMLElement,
  auditTable: document.getElementById("auditTable") as HTMLElement,
  userMessage: document.getElementById("userMessage") as HTMLElement,
  userId: document.getElementById("userId") as HTMLInputElement,
  userName: document.getElementById("userName") as HTMLInputElement,
  userLogin: document.getElementById("userLogin") as HTMLInputElement,
  userEmail: document.getElementById("userEmail") as HTMLInputElement,
  userRole: document.getElementById("userRole") as HTMLSelectElement,
  userStatus: document.getElementById("userStatus") as HTMLSelectElement,
  userPassword: document.getElementById("userPassword") as HTMLInputElement,
  permissionMatrix: document.getElementById("permissionMatrix") as HTMLElement,
  userHistory: document.getElementById("userHistory") as HTMLElement,
};

const titles: Record<string, [string, string]> = {
  dashboard: ["Painel", "Base PostgreSQL local/rede com sincronização segura por Dropbox."],
  offline: ["Operação offline", "Checklist, check-in, fotos, assinaturas e OS com fila local resiliente."],
  clients: ["Clientes", "Cadastro operacional já gravado no PostgreSQL."],
  users: ["Usuários", "Perfis: administrador, operação, motorista, financeiro e almoxarifado."],
  sync: ["Sincronização", "Snapshots em Dropbox/SannySystemData com controle de conflito."],
  audit: ["Auditoria", "Registro de acessos, alterações, sincronização e bloqueios."],
};

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function decodeJwtPayload(value: string): { exp?: number } | null {
  try {
    const [, body] = value.split(".");
    if (!body) return null;
    const normalized = body.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(atob(padded)) as { exp?: number };
  } catch {
    return null;
  }
}

function clearAuth(): void {
  token = "";
  refreshToken = "";
  window.localStorage.removeItem("sannysystem.token");
  window.localStorage.removeItem("sannysystem.refreshToken");
  if (refreshTimer) window.clearTimeout(refreshTimer);
  if (idleLogoutTimer) window.clearTimeout(idleLogoutTimer);
  refreshTimer = undefined;
  idleLogoutTimer = undefined;
}

function persistAuth(result: { token?: string; accessToken?: string; refreshToken?: string }): void {
  token = result.accessToken || result.token || "";
  refreshToken = result.refreshToken || refreshToken;
  if (token) window.localStorage.setItem("sannysystem.token", token);
  if (refreshToken) window.localStorage.setItem("sannysystem.refreshToken", refreshToken);
  scheduleRefresh();
  resetIdleLogoutTimer();
}

async function autoLogoutForInactivity(): Promise<void> {
  if (!token && !refreshToken) return;
  await api("/auth/logout", { method: "POST" }).catch(() => undefined);
  clearAuth();
  showApp(false);
  elements.loginMessage.textContent = `Sessão encerrada automaticamente após ${IDLE_LOGOUT_MINUTES} minutos sem uso.`;
}

function resetIdleLogoutTimer(): void {
  if (idleLogoutTimer) window.clearTimeout(idleLogoutTimer);
  if (!token && !refreshToken) return;
  idleLogoutTimer = window.setTimeout(() => {
    autoLogoutForInactivity().catch(() => undefined);
  }, IDLE_LOGOUT_MS);
}

function bindIdleLogout(): void {
  for (const eventName of ["click", "keydown", "input", "mousemove", "touchstart", "scroll"]) {
    window.addEventListener(eventName, resetIdleLogoutTimer, { passive: true });
  }
}

async function refreshAuth(): Promise<boolean> {
  if (!refreshToken) return false;
  try {
    const response = await fetch(`${apiBase}/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refreshToken }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "Sessão expirada.");
    persistAuth(body as { token: string; accessToken: string; refreshToken: string });
    return true;
  } catch {
    clearAuth();
    return false;
  }
}

function scheduleRefresh(): void {
  if (refreshTimer) window.clearTimeout(refreshTimer);
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return;
  const delay = Math.max(payload.exp * 1000 - Date.now() - 60_000, 30_000);
  refreshTimer = window.setTimeout(() => {
    refreshAuth().then((ok) => {
      if (!ok) showApp(false);
    });
  }, delay);
}

async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("content-type", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (response.status === 401 && retry && refreshToken && (await refreshAuth())) {
    return api<T>(path, options, false);
  }
  if (!response.ok) throw new Error(body.error || "Falha na comunicação local.");
  return body as T;
}

function showApp(isLogged: boolean): void {
  elements.loginView.classList.toggle("hidden", isLogged);
  elements.appView.classList.toggle("hidden", !isLogged);
  elements.loadingScreen.classList.add("hidden");
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  return new Date(value).toLocaleString("pt-BR");
}

function formatNumber(value: unknown): string {
  return Number(value || 0).toLocaleString("pt-BR");
}

function formatCurrency(value: unknown): string {
  return Number(value || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  });
}

function renderJson(target: HTMLElement, value: unknown): void {
  target.textContent = JSON.stringify(value, null, 2);
}

function isOnline(): boolean {
  return navigator.onLine;
}

function updateConnectionUi(): void {
  const online = isOnline();
  elements.connectionPill.textContent = online ? "Online" : "Offline";
  elements.connectionPill.classList.toggle("online", online);
  elements.connectionPill.classList.toggle("offline", !online);
  elements.offlineConnectionMetric.textContent = online ? "Online" : "Offline";
}

function checklistItems(): Array<{ label: string; done: boolean }> {
  return elements.offlineChecklist.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((label) => ({ label, done: true }));
}

function selectedServiceOrder(): { id: string | null; version?: number | null } {
  const value = elements.offlineServiceOrder.value;
  if (value && value !== "__new__") {
    const option = elements.offlineServiceOrder.selectedOptions[0];
    return { id: value, version: option ? Number(option.getAttribute("data-version") || "0") : null };
  }
  if (!currentOfflineServiceOrderId) currentOfflineServiceOrderId = `local-os-${Date.now()}`;
  return { id: currentOfflineServiceOrderId, version: null };
}

function resetOfflineDraft(): void {
  currentOfflineServiceOrderId = "";
  elements.offlineTitle.value = "";
  elements.offlineChecklist.value = "";
  elements.offlineNotes.value = "";
  elements.offlinePhotoInput.value = "";
  clearSignature();
}

async function currentGps(): Promise<Record<string, number> | null> {
  if (!navigator.geolocation) return null;
  return new Promise((resolve) => {
    const timeout = window.setTimeout(() => resolve(null), 4500);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        window.clearTimeout(timeout);
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      () => {
        window.clearTimeout(timeout);
        resolve(null);
      },
      { enableHighAccuracy: true, timeout: 4000, maximumAge: 60_000 },
    );
  });
}

async function loadServiceOrders(): Promise<void> {
  let serviceOrders: Array<Record<string, unknown>> = [];
  if (token && isOnline()) {
    try {
      const result = await api<{ serviceOrders: Array<Record<string, unknown>> }>("/service-orders");
      serviceOrders = result.serviceOrders;
      await window.sannyOffline?.cacheServiceOrders(serviceOrders);
    } catch {
      serviceOrders = await window.sannyOffline?.cachedServiceOrders() || [];
    }
  } else {
    serviceOrders = await window.sannyOffline?.cachedServiceOrders() || [];
  }

  elements.offlineServiceOrder.innerHTML = [
    `<option value="__new__">Nova ordem offline</option>`,
    ...serviceOrders.map((order) => {
      const payload = (order.payload || {}) as Record<string, unknown>;
      const title = String(payload.title || payload.description || order.id || "Ordem sem título");
      return `<option value="${escapeHtml(order.id)}" data-version="${escapeHtml(order.version || 0)}">${escapeHtml(title)} - ${escapeHtml(order.status || "aberta")}</option>`;
    }),
  ].join("");
}

async function renderOfflineQueue(): Promise<void> {
  const localQueue = await window.sannyOffline?.listQueue() || [];
  const localPending = localQueue.filter((item) => item.localStatus === "pending" || item.localStatus === "failed");
  elements.offlineLocalMetric.textContent = String(localPending.length);
  elements.syncPill.textContent = `Fila ${localPending.length}`;

  if (!localQueue.length) {
    elements.offlineQueueList.textContent = "Nenhuma ação local pendente.";
  } else {
    elements.offlineQueueList.innerHTML = localQueue
      .slice(-40)
      .reverse()
      .map(
        (item) => `
          <div class="status-item">
            <strong>${escapeHtml(item.operation)} / ${escapeHtml(item.actionType)}</strong>
            <div>OS: ${escapeHtml(item.entityId || item.payload.serviceOrderId || "nova")}</div>
            <div>Status local: ${escapeHtml(item.localStatus)}</div>
            <small>${formatDate(item.createdAt)}${item.lastError ? ` - ${escapeHtml(item.lastError)}` : ""}</small>
          </div>
        `,
      )
      .join("");
  }
}

async function loadOfflineStatus(): Promise<void> {
  updateConnectionUi();
  await renderOfflineQueue();
  await loadServiceOrders();

  if (!token || !isOnline()) {
    elements.offlineServerMetric.textContent = "-";
    elements.offlineLastSyncMetric.textContent = "-";
    elements.offlineConflictLog.textContent = "Conflitos serão atualizados quando a conexão local voltar.";
    return;
  }

  try {
    const status = await api<{
      queue?: { pending?: number; failed?: number; conflicts?: number };
      lastSyncedAt?: string | null;
      recentConflicts?: Array<Record<string, unknown>>;
    }>("/offline/status");
    const serverPending = Number(status.queue?.pending || 0) + Number(status.queue?.failed || 0);
    elements.offlineServerMetric.textContent = String(serverPending);
    elements.offlineLastSyncMetric.textContent = status.lastSyncedAt ? formatDate(status.lastSyncedAt) : "-";
    const conflicts = status.recentConflicts || [];
    elements.offlineConflictLog.innerHTML = conflicts.length
      ? conflicts
          .map(
            (conflict) => `
              <div class="status-item">
                <strong>${escapeHtml(conflict.actionType)} / ${escapeHtml(conflict.entityId || conflict.clientMutationId)}</strong>
                <div>${escapeHtml(conflict.lastError || "Conflito pendente")}</div>
                <small>${formatDate(String(conflict.updatedAt || ""))}</small>
              </div>
            `,
          )
          .join("")
      : "Nenhum conflito offline pendente.";
  } catch (error) {
    elements.offlineServerMetric.textContent = "-";
    elements.offlineConflictLog.textContent = error instanceof Error ? error.message : "Falha ao consultar fila do servidor.";
  }
}

async function syncOfflineNow(forceServer = false): Promise<void> {
  updateConnectionUi();
  if (!token || !isOnline() || !window.sannyOffline) return;

  const pending = await window.sannyOffline.pendingQueue();
  if (!pending.length) {
    if (forceServer) await api("/offline/sync", { method: "POST" }).catch(() => undefined);
    await loadOfflineStatus();
    return;
  }

  const ids = pending.map((item) => item.clientMutationId);
  try {
    await api("/offline/queue", {
      method: "POST",
      body: JSON.stringify({
        items: pending.map(({ localStatus: _localStatus, lastError: _lastError, ...item }) => item),
      }),
    });
    await api("/offline/sync", { method: "POST" });
    await window.sannyOffline.markSynced(ids);
    elements.offlineMessage.textContent = "Fila sincronizada.";
  } catch (error) {
    const message = error instanceof Error ? error.message : "Falha ao sincronizar fila offline.";
    await window.sannyOffline.markFailed(ids, message);
    elements.offlineMessage.textContent = message;
  } finally {
    await loadOfflineStatus();
  }
}

let signatureDrawing = false;
let signatureDirty = false;

function signatureContext(): CanvasRenderingContext2D | null {
  const context = elements.signatureCanvas.getContext("2d");
  if (!context) return null;
  context.lineWidth = 3;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.strokeStyle = "#18202a";
  return context;
}

function signaturePoint(event: PointerEvent): { x: number; y: number } {
  const rect = elements.signatureCanvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * elements.signatureCanvas.width,
    y: ((event.clientY - rect.top) / rect.height) * elements.signatureCanvas.height,
  };
}

function clearSignature(): void {
  const context = signatureContext();
  if (!context) return;
  context.clearRect(0, 0, elements.signatureCanvas.width, elements.signatureCanvas.height);
  signatureDirty = false;
}

function setupSignaturePad(): void {
  const canvas = elements.signatureCanvas;
  const context = signatureContext();
  if (!context) return;
  clearSignature();

  canvas.addEventListener("pointerdown", (event) => {
    signatureDrawing = true;
    signatureDirty = true;
    canvas.setPointerCapture(event.pointerId);
    const point = signaturePoint(event);
    context.beginPath();
    context.moveTo(point.x, point.y);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (!signatureDrawing) return;
    const point = signaturePoint(event);
    context.lineTo(point.x, point.y);
    context.stroke();
  });

  const stop = (event: PointerEvent) => {
    if (!signatureDrawing) return;
    signatureDrawing = false;
    canvas.releasePointerCapture(event.pointerId);
  };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
}

async function signatureAttachment(): Promise<Record<string, unknown> | null> {
  if (!signatureDirty) return null;
  const dataBase64 = elements.signatureCanvas.toDataURL("image/png");
  return {
    kind: "SIGNATURE",
    fileName: `assinatura-${Date.now()}.png`,
    mimeType: "image/png",
    sizeBytes: Math.round((dataBase64.length * 3) / 4),
    dataBase64,
  };
}

async function loadHealth(): Promise<void> {
  const health = await api<Record<string, unknown>>("/health");
  renderJson(elements.healthOutput, health);
  elements.dropboxMetric.textContent = health.dropboxDetected ? "Detectado" : "Local";
}

async function loadAppInfo(): Promise<void> {
  const info = await window.sannyDesktop?.getAppInfo();
  if (!info) return;
  const version = String(info.version || "");
  elements.appVersion.textContent = version ? `SannySystem ${version}` : "SannySystem";
  elements.safeModePill.classList.toggle("hidden", !info.safeMode);
  renderJson(elements.appInfoOutput, info);
}

function payloadTitle(item: Record<string, unknown>): string {
  const payload = (item.payload || {}) as Record<string, unknown>;
  return String(payload.title || payload.description || item.id || "Ordem sem título");
}

function statusTone(status: unknown): string {
  const normalized = String(status || "").toLowerCase();
  if (["concluida", "finalizada", "done"].includes(normalized)) return "done";
  if (["em_andamento", "em andamento", "active"].includes(normalized)) return "active";
  if (["atrasada", "bloqueada", "erro"].includes(normalized)) return "danger";
  return "pending";
}

function renderStatus(status: unknown): string {
  const label = String(status || "aberta").replace(/_/g, " ");
  return `<span class="status-chip ${statusTone(status)}">${escapeHtml(label)}</span>`;
}

async function loadOperationalDashboard(): Promise<void> {
  elements.todayLabel.textContent = new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });

  const [sync, localPending, summary] = await Promise.all([
    api<Record<string, unknown>>("/sync/status").catch(() => ({ openConflicts: 0 } as Record<string, unknown>)),
    window.sannyOffline?.pendingCount().catch(() => 0) || Promise.resolve(0),
    api<DashboardOperations>("/dashboard/operations").catch(() => null),
  ]);

  let serviceOrders: Array<Record<string, unknown>> = Array.isArray(summary?.serviceOrders?.latest)
    ? summary.serviceOrders.latest
    : [];
  if (!serviceOrders.length) {
    try {
    const result = await api<{ serviceOrders: Array<Record<string, unknown>> }>("/service-orders");
    serviceOrders = result.serviceOrders || [];
    await window.sannyOffline?.cacheServiceOrders(serviceOrders);
    } catch {
    serviceOrders = await window.sannyOffline?.cachedServiceOrders() || [];
    }
  }

  const search = elements.globalSearch.value.trim().toLowerCase();
  const filtered = search
    ? serviceOrders.filter((item) => `${payloadTitle(item)} ${item.status || ""} ${item.id || ""}`.toLowerCase().includes(search))
    : serviceOrders;
  const active = serviceOrders.filter((item) => !["concluida", "finalizada"].includes(String(item.status || "").toLowerCase()));
  const openConflicts = Number(summary?.sync?.openConflicts ?? sync.openConflicts ?? 0);
  const pendingOffline = Number(summary?.offline?.pending ?? localPending ?? 0);
  const equipment = summary?.equipment || {};
  const equipmentTotal = Number(equipment.total || 0);
  const availableEquipment = Number(equipment.available || 0);
  const inUseEquipment = Number(equipment.inUse || 0);
  const maintenanceEquipment = Number(equipment.maintenance || 0);
  const otherEquipment = Number(equipment.other || 0);
  const totalForBars = Math.max(equipmentTotal, availableEquipment + inUseEquipment + maintenanceEquipment + otherEquipment, 1);
  const availabilityPercent = (value: number) => `${Math.min(100, Math.round((value / totalForBars) * 100))}%`;

  elements.activeOrdersMetric.textContent = formatNumber(summary?.serviceOrders?.active ?? active.length);
  elements.dashboardQueueMetric.textContent = formatNumber(pendingOffline);
  elements.conflictMetric.textContent = formatNumber(openConflicts);
  elements.eventTodayMetric.textContent = formatNumber(summary?.events?.today || 0);
  elements.futureEventsMetric.textContent = formatNumber(summary?.events?.future || 0);
  elements.simultaneousEventsMetric.textContent = formatNumber(summary?.events?.simultaneous || 0);
  elements.equipmentAvailableMetric.textContent = formatNumber(availableEquipment);
  elements.equipmentInUseMetric.textContent = formatNumber(inUseEquipment);
  elements.equipmentMaintenanceMetric.textContent = formatNumber(maintenanceEquipment);
  elements.vehicleActiveMetric.textContent = formatNumber(summary?.vehicles?.active || 0);
  elements.financialPendingMetric.textContent = formatNumber(summary?.financial?.openCount || 0);
  elements.stockRiskMetric.textContent = formatNumber(summary?.warehouse?.lowStock || 0);

  elements.dashboardEquipmentGrid.innerHTML = `
    <article class="availability-item positive">
      <div><span>Disponíveis</span><strong>${formatNumber(availableEquipment)}</strong></div>
      <div class="availability-bar"><span style="width: ${availabilityPercent(availableEquipment)}"></span></div>
    </article>
    <article class="availability-item active">
      <div><span>Em uso</span><strong>${formatNumber(inUseEquipment)}</strong></div>
      <div class="availability-bar"><span style="width: ${availabilityPercent(inUseEquipment)}"></span></div>
    </article>
    <article class="availability-item warning">
      <div><span>Manutenção</span><strong>${formatNumber(maintenanceEquipment)}</strong></div>
      <div class="availability-bar"><span style="width: ${availabilityPercent(maintenanceEquipment)}"></span></div>
    </article>
    <article class="availability-item muted">
      <div><span>Outros status</span><strong>${formatNumber(otherEquipment)}</strong></div>
      <div class="availability-bar"><span style="width: ${availabilityPercent(otherEquipment)}"></span></div>
    </article>
  `;

  const timelineItems = filtered.slice(0, 6);
  elements.dashboardTimeline.innerHTML = timelineItems.length
    ? timelineItems
        .map(
          (item) => `
            <article class="timeline-item">
              <span class="timeline-dot ${statusTone(item.status)}"></span>
              <div>
                <strong>${escapeHtml(payloadTitle(item))}</strong>
                <p>${escapeHtml(String(item.id || ""))} · ${escapeHtml(formatDate(String(item.scheduledAt || item.updatedAt || "")) || "sem agenda")}</p>
              </div>
              ${renderStatus(item.status)}
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">Nenhuma ordem encontrada para o filtro atual.</div>`;

  elements.dashboardOrdersTable.innerHTML = filtered.slice(0, 10)
    .map(
      (item) => `
        <tr>
          <td>
            <strong>${escapeHtml(payloadTitle(item))}</strong>
            <small>${escapeHtml(String(item.id || ""))}</small>
          </td>
          <td>${renderStatus(item.status)}</td>
          <td>${formatDate(String(item.scheduledAt || item.updatedAt || "")) || "-"}</td>
          <td>${escapeHtml(item.version || 1)}</td>
        </tr>
      `,
    )
    .join("") || `<tr><td colspan="4">Nenhuma ordem cadastrada.</td></tr>`;

  const alerts = [
    !isOnline()
      ? { tone: "danger", title: "Sem conexão", detail: "A operação continua no cache local." }
      : null,
    pendingOffline
      ? { tone: "warning", title: "Fila offline pendente", detail: `${pendingOffline} ações aguardam sincronização.` }
      : null,
    openConflicts
      ? { tone: "danger", title: "Conflitos de dados", detail: `${openConflicts} registros exigem decisão.` }
      : null,
    summary?.serviceOrders?.delayed
      ? { tone: "danger", title: "Ordens atrasadas", detail: `${summary.serviceOrders.delayed} OS passaram do horário previsto.` }
      : null,
    maintenanceEquipment
      ? { tone: "warning", title: "Equipamentos em manutenção", detail: `${maintenanceEquipment} itens precisam de atenção antes da escala.` }
      : null,
    summary?.warehouse?.lowStock
      ? { tone: "warning", title: "Risco de estoque", detail: `${summary.warehouse.lowStock} itens abaixo do mínimo no almoxarifado.` }
      : null,
    summary?.financial?.openCount
      ? { tone: "info", title: "Pendências financeiras", detail: `${summary.financial.openCount} lançamentos em aberto (${formatCurrency(summary.financial.openAmount)}).` }
      : null,
    (summary?.sync?.lastSnapshot || sync.lastSnapshot)
      ? {
          tone: "info",
          title: "Último snapshot",
          detail: formatDate(String(((summary?.sync?.lastSnapshot || sync.lastSnapshot) as Record<string, unknown>).createdAt || "")),
        }
      : { tone: "warning", title: "Snapshot não encontrado", detail: "Execute uma sincronização para criar histórico." },
  ].filter(Boolean) as Array<{ tone: string; title: string; detail: string }>;

  elements.dashboardAlerts.innerHTML = alerts
    .map(
      (alert) => `
        <article class="alert-card ${alert.tone}">
          <strong>${escapeHtml(alert.title)}</strong>
          <p>${escapeHtml(alert.detail)}</p>
        </article>
      `,
    )
    .join("");
}

async function loadSync(): Promise<void> {
  const status = await api<Record<string, unknown>>("/sync/status");
  renderJson(elements.syncOutput, status);
  elements.conflictMetric.textContent = String(status.openConflicts || 0);
}

async function loadConflicts(): Promise<void> {
  const result = await api<{ conflicts: Array<Record<string, unknown>> }>("/sync/conflicts");
  elements.conflictList.innerHTML = "";
  if (!result.conflicts.length) {
    elements.conflictList.textContent = "Nenhum conflito pendente.";
    return;
  }
  for (const conflict of result.conflicts) {
    const item = document.createElement("div");
    item.className = "status-item";
    item.innerHTML = `
      <strong>${conflict.entity} / ${conflict.recordId}</strong>
      <div>Origem: ${conflict.sourceWorkstationId}</div>
      <div>Status: ${conflict.status}</div>
      <div class="button-row">
        <button data-resolution="accept_remote" data-id="${conflict.id}">Usar remoto</button>
        <button data-resolution="accept_local" data-id="${conflict.id}">Manter local</button>
        <button data-resolution="ignore" data-id="${conflict.id}">Ignorar</button>
      </div>
    `;
    elements.conflictList.appendChild(item);
  }
}

async function loadClients(): Promise<void> {
  const result = await api<{ clients: Array<Record<string, string>> }>("/clients");
  elements.clientsTable.innerHTML = result.clients
    .map(
      (client) => `
      <tr>
        <td>${client.customerName || ""}</td>
        <td>${client.phone || ""}</td>
        <td>${client.address || ""}</td>
        <td>${formatDate(client.updatedAt)}</td>
      </tr>
    `,
    )
    .join("");
}

async function loadUsers(): Promise<void> {
  const result = await api<{ users: Array<Record<string, string>> }>("/users");
  elements.usersTable.innerHTML = result.users
    .map(
      (user) => `
      <tr>
        <td>${escapeHtml(user.name)}</td>
        <td>${escapeHtml(user.login)}</td>
        <td>${escapeHtml(user.email)}</td>
        <td>${escapeHtml(user.role)}</td>
        <td>${escapeHtml(user.status)}${user.deletedAt ? " / excluído" : ""}</td>
        <td>${formatDate(user.lastLoginAt)}</td>
        <td>
          <div class="button-row">
            <button class="table-action" data-user-action="edit" data-id="${escapeHtml(user.id)}">Editar</button>
            <button class="table-action" data-user-action="history" data-id="${escapeHtml(user.id)}">Histórico</button>
            <button class="table-action" data-user-action="reset" data-id="${escapeHtml(user.id)}">Senha</button>
            <button class="table-action danger" data-user-action="delete" data-id="${escapeHtml(user.id)}">Excluir</button>
          </div>
        </td>
      </tr>
    `,
    )
    .join("");
  (window as unknown as { __sannyUsers?: Array<Record<string, string>> }).__sannyUsers = result.users;
}

async function loadPermissions(): Promise<void> {
  const result = await api<{
    roles: Array<{ role: string; label: string; permissions: string[] }>;
    permissions: Array<{ key: string; module: string; description: string }>;
  }>("/permissions");
  elements.permissionMatrix.innerHTML = result.roles
    .map(
      (role) => `
        <div class="status-item">
          <strong>${escapeHtml(role.label)}</strong>
          <small>${escapeHtml(role.permissions.includes("*") ? "acesso total" : `${role.permissions.length} permissões`)}</small>
          <ul>
            ${(role.permissions.includes("*") ? result.permissions.map((item) => item.key) : role.permissions)
              .slice(0, 12)
              .map((permission) => `<li>${escapeHtml(permission)}</li>`)
              .join("")}
          </ul>
        </div>
      `,
    )
    .join("");
}

async function loadUserHistory(userId: string): Promise<void> {
  const result = await api<{
    user: { name: string; email: string; roleLabel: string };
    audit: Array<Record<string, string>>;
    access: Array<Record<string, string>>;
    sessions: Array<Record<string, string>>;
  }>(`/users/${userId}/history`);
  elements.userHistory.innerHTML = `
    <div class="status-item">
      <strong>${escapeHtml(result.user.name)}</strong>
      <div>${escapeHtml(result.user.email)} / ${escapeHtml(result.user.roleLabel)}</div>
      <small>${result.access.length} acessos, ${result.audit.length} auditorias, ${result.sessions.length} sessões recentes</small>
    </div>
    <div class="status-item">
      <strong>Últimos acessos</strong>
      <ul>
        ${result.access
          .slice(0, 8)
          .map(
            (entry) =>
              `<li>${formatDate(entry.createdAt)} - ${escapeHtml(entry.action)} - IP ${escapeHtml(entry.ipAddress || "-")} - máquina ${escapeHtml(entry.workstation || "-")}</li>`,
          )
          .join("") || "<li>Nenhum acesso registrado.</li>"}
      </ul>
    </div>
    <div class="status-item">
      <strong>Últimas alterações</strong>
      <ul>
        ${result.audit
          .slice(0, 8)
          .map(
            (entry) =>
              `<li>${formatDate(entry.createdAt)} - ${escapeHtml(entry.action)} - ${escapeHtml(entry.module)} - IP ${escapeHtml(entry.ipAddress || "-")} - máquina ${escapeHtml(entry.workstation || "-")}</li>`,
          )
          .join("") || "<li>Nenhuma alteração registrada.</li>"}
      </ul>
    </div>
  `;
}

async function loadAudit(): Promise<void> {
  const result = await api<{ entries: Array<Record<string, string>> }>("/audit");
  elements.auditTable.innerHTML = result.entries
    .map(
      (entry) => `
      <tr>
        <td>${formatDate(entry.createdAt)}</td>
        <td>${entry.userEmail || ""}</td>
        <td>${entry.action || ""}</td>
        <td>${entry.module || ""}</td>
        <td>${entry.detail || ""}</td>
      </tr>
    `,
    )
    .join("");
}

async function loadMe(): Promise<void> {
  const result = await api<{ user: { name: string; email: string; roleLabel: string; permissions: string[] } }>("/auth/me");
  elements.sessionBox.innerHTML = `
    <strong>${result.user.name}</strong>
    <p>${result.user.email}</p>
    <p>Perfil: ${result.user.roleLabel}</p>
  `;
  elements.roleTopbar.textContent = result.user.roleLabel;
}

async function queueOfflineAction(
  actionType: SannyOfflineQueueItem["actionType"],
  operation: string,
  extraPayload: Record<string, unknown> = {},
  attachments: SannyOfflineAttachment[] = [],
): Promise<void> {
  if (!window.sannyOffline) throw new Error("Cache offline indisponível.");
  const selected = selectedServiceOrder();
  const notes = elements.offlineNotes.value.trim();
  const title = elements.offlineTitle.value.trim();
  const gps = actionType === "CHECK_IN" || actionType === "CHECK_OUT" ? await currentGps() : null;
  await window.sannyOffline.queueAction({
    actionType,
    entity: "serviceOrder",
    entityId: selected.id,
    operation,
    baseVersion: selected.version || undefined,
    payload: {
      serviceOrderId: selected.id,
      title,
      notes,
      at: new Date().toISOString(),
      gps,
      checklist: checklistItems(),
      serviceOrderPayload: {
        title: title || "Ordem criada offline",
        description: notes,
      },
      ...extraPayload,
    },
    attachments,
  });
  elements.offlineMessage.textContent = isOnline()
    ? "Ação registrada. Sincronização iniciada."
    : "Ação salva offline. Será sincronizada quando a conexão voltar.";
  await loadOfflineStatus();
  if (isOnline()) await syncOfflineNow();
}

async function queuePhotoAction(): Promise<void> {
  const files = Array.from(elements.offlinePhotoInput.files || []);
  if (!files.length) {
    elements.offlineMessage.textContent = "Selecione pelo menos uma foto.";
    return;
  }
  const attachments = [];
  for (const file of files) {
    const attachment = await window.sannyOffline?.fileToAttachment(file, "PHOTO");
    if (attachment) attachments.push(attachment);
  }
  await queueOfflineAction("PHOTO", "photo.upload", { photoCount: attachments.length }, attachments);
  elements.offlinePhotoInput.value = "";
}

async function queueSignatureAction(): Promise<void> {
  const attachment = await signatureAttachment();
  if (!attachment) {
    elements.offlineMessage.textContent = "Colete a assinatura antes de salvar.";
    return;
  }
  await queueOfflineAction(
    "SIGNATURE",
    "signature.capture",
    { signerName: elements.signatureName.value.trim() },
    [attachment as SannyOfflineAttachment],
  );
  elements.signatureName.value = "";
  clearSignature();
}

async function refreshCurrentView(): Promise<void> {
  updateConnectionUi();
  if (currentView === "dashboard") {
    await loadHealth();
    await loadSync().catch(() => undefined);
    await renderOfflineQueue().catch(() => undefined);
    await loadOperationalDashboard().catch((error) => {
      elements.dashboardAlerts.innerHTML = `<article class="alert-card danger"><strong>Dashboard indisponível</strong><p>${escapeHtml(error instanceof Error ? error.message : "Falha ao carregar dados.")}</p></article>`;
    });
  }
  if (currentView === "offline") await loadOfflineStatus();
  if (currentView === "clients") await loadClients();
  if (currentView === "users") {
    await loadUsers();
    await loadPermissions();
  }
  if (currentView === "sync") {
    await loadSync();
    await loadConflicts();
  }
  if (currentView === "audit") await loadAudit();
}

function switchView(view: string): void {
  currentView = view;
  for (const node of document.querySelectorAll(".view")) node.classList.add("hidden");
  document.getElementById(`${view}View`)?.classList.remove("hidden");
  for (const nav of document.querySelectorAll(".nav-item")) nav.classList.toggle("active", nav.getAttribute("data-view") === view);
  const [title, subtitle] = titles[view] || titles.dashboard;
  elements.viewTitle.textContent = title;
  elements.viewSubtitle.textContent = subtitle;
  refreshCurrentView().catch((error) => {
    elements.healthOutput.textContent = error.message;
  });
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.loginMessage.textContent = "";
  try {
    const result = await api<{ token: string; accessToken: string; refreshToken: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ login: elements.loginEmail.value, password: elements.loginPassword.value }),
    });
    persistAuth(result);
    showApp(true);
    await loadMe();
    switchView("dashboard");
    await syncOfflineNow().catch(() => undefined);
  } catch (error) {
    elements.loginMessage.textContent = error instanceof Error ? error.message : "Falha no login.";
  }
});

document.getElementById("logoutButton")?.addEventListener("click", async () => {
  await api("/auth/logout", { method: "POST" }).catch(() => undefined);
  clearAuth();
  showApp(false);
});

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => switchView(button.getAttribute("data-view") || "dashboard"));
});

document.querySelectorAll("[data-view-jump]").forEach((button) => {
  button.addEventListener("click", () => switchView(button.getAttribute("data-view-jump") || "dashboard"));
});

elements.globalSearch.addEventListener("input", () => {
  if (currentView === "dashboard") loadOperationalDashboard().catch(() => undefined);
});

document.getElementById("clientForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await api("/clients", {
    method: "POST",
    body: JSON.stringify({
      customerName: (document.getElementById("clientName") as HTMLInputElement).value,
      phone: (document.getElementById("clientPhone") as HTMLInputElement).value,
      address: (document.getElementById("clientAddress") as HTMLInputElement).value,
    }),
  });
  (event.currentTarget as HTMLFormElement).reset();
  await loadClients();
});

document.getElementById("userForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.userMessage.textContent = "";
  const editingId = elements.userId.value;
  const result = await api<{ temporaryPassword?: string }>(editingId ? `/users/${editingId}` : "/users", {
    method: editingId ? "PUT" : "POST",
    body: JSON.stringify({
      name: elements.userName.value,
      login: elements.userLogin.value || elements.userEmail.value,
      email: elements.userEmail.value,
      role: elements.userRole.value,
      status: elements.userStatus.value,
      password: editingId ? undefined : elements.userPassword.value || undefined,
    }),
  });
  if (result.temporaryPassword) elements.userMessage.textContent = `Senha temporária gerada: ${result.temporaryPassword}`;
  (event.currentTarget as HTMLFormElement).reset();
  elements.userId.value = "";
  await loadUsers();
});

document.getElementById("clearUserFormButton")?.addEventListener("click", () => {
  (document.getElementById("userForm") as HTMLFormElement).reset();
  elements.userId.value = "";
  elements.userMessage.textContent = "";
});

elements.usersTable.addEventListener("click", async (event) => {
  const target = event.target as HTMLElement;
  const action = target.getAttribute("data-user-action");
  const id = target.getAttribute("data-id");
  if (!action || !id) return;
  const users = (window as unknown as { __sannyUsers?: Array<Record<string, string>> }).__sannyUsers || [];
  const user = users.find((item) => item.id === id);
  if (action === "edit" && user) {
    elements.userId.value = user.id || "";
    elements.userName.value = user.name || "";
    elements.userLogin.value = user.login || "";
    elements.userEmail.value = user.email || "";
    elements.userRole.value = String(user.role || "operacao").toLowerCase();
    elements.userStatus.value = String(user.status || "ativo").toLowerCase();
    elements.userMessage.textContent = "Editando usuário selecionado.";
    return;
  }
  if (action === "history") {
    await loadUserHistory(id);
    return;
  }
  if (action === "reset") {
    const result = await api<{ temporaryPassword?: string }>(`/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({}) });
    elements.userMessage.textContent = result.temporaryPassword
      ? `Senha temporária gerada: ${result.temporaryPassword}`
      : "Senha redefinida.";
    await loadUsers();
    await loadUserHistory(id).catch(() => undefined);
    return;
  }
  if (action === "delete") {
    await api(`/users/${id}`, { method: "DELETE" });
    elements.userMessage.textContent = "Usuário inativado e histórico preservado.";
    await loadUsers();
  }
});

document.getElementById("exportSyncButton")?.addEventListener("click", async () => {
  renderJson(elements.syncOutput, await api("/sync/export", { method: "POST" }));
  await loadSync();
});

document.getElementById("importSyncButton")?.addEventListener("click", async () => {
  renderJson(elements.syncOutput, await api("/sync/import", { method: "POST" }));
  await loadSync();
  await loadConflicts();
});

elements.conflictList.addEventListener("click", async (event) => {
  const target = event.target as HTMLElement;
  const id = target.getAttribute("data-id");
  const resolution = target.getAttribute("data-resolution");
  if (!id || !resolution) return;
  await api(`/sync/conflicts/${id}/resolve`, { method: "POST", body: JSON.stringify({ resolution }) });
  await loadConflicts();
  await loadSync();
});

document.getElementById("offlineSaveOrderButton")?.addEventListener("click", () => {
  queueOfflineAction("SERVICE_ORDER", "service-order.save").catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao salvar offline.";
  });
});

document.getElementById("offlineChecklistButton")?.addEventListener("click", () => {
  queueOfflineAction("CHECKLIST", "checklist.save").catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao salvar checklist.";
  });
});

document.getElementById("offlineCheckInButton")?.addEventListener("click", () => {
  queueOfflineAction("CHECK_IN", "check-in").catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao registrar check-in.";
  });
});

document.getElementById("offlineCheckOutButton")?.addEventListener("click", () => {
  queueOfflineAction("CHECK_OUT", "check-out").catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao registrar check-out.";
  });
});

document.getElementById("offlinePhotoButton")?.addEventListener("click", () => {
  queuePhotoAction().catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao salvar fotos.";
  });
});

document.getElementById("offlineSignatureButton")?.addEventListener("click", () => {
  queueSignatureAction().catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao salvar assinatura.";
  });
});

document.getElementById("offlineOccurrenceButton")?.addEventListener("click", () => {
  queueOfflineAction("OCCURRENCE", "occurrence.save").catch((error) => {
    elements.offlineMessage.textContent = error instanceof Error ? error.message : "Falha ao registrar ocorrência.";
  });
});

document.getElementById("flushOfflineButton")?.addEventListener("click", () => syncOfflineNow(true));
document.getElementById("reloadOfflineButton")?.addEventListener("click", () => loadOfflineStatus());
document.getElementById("clearSignatureButton")?.addEventListener("click", () => clearSignature());

document.getElementById("reloadClientsButton")?.addEventListener("click", () => loadClients());
document.getElementById("reloadUsersButton")?.addEventListener("click", () => loadUsers());
document.getElementById("reloadAuditButton")?.addEventListener("click", () => loadAudit());
document.getElementById("reloadConflictsButton")?.addEventListener("click", () => loadConflicts());
document.getElementById("reloadDashboardButton")?.addEventListener("click", () => loadOperationalDashboard());

document.getElementById("checkUpdatesButton")?.addEventListener("click", async () => {
  elements.updateStatus.textContent = "Verificando atualizações...";
  const result = await window.sannyDesktop?.checkForUpdates();
  if (result) renderJson(elements.updateStatus, result);
});

document.getElementById("installUpdateButton")?.addEventListener("click", async () => {
  await window.sannyDesktop?.installUpdate();
});

window.sannyDesktop?.onStartupStatus((payload) => {
  const value = payload as { status?: string; detail?: unknown };
  elements.loadingMessage.textContent = String(value.detail || value.status || "Preparando ambiente...");
});

window.sannyDesktop?.onUpdateStatus((payload) => {
  renderJson(elements.updateStatus, payload);
  const status = (payload as { status?: string }).status;
  document.getElementById("installUpdateButton")?.classList.toggle("hidden", status !== "downloaded");
});

setupSignaturePad();
bindIdleLogout();
updateConnectionUi();
renderOfflineQueue().catch(() => undefined);

window.addEventListener("online", () => {
  updateConnectionUi();
  syncOfflineNow().catch(() => undefined);
});

window.addEventListener("offline", () => {
  updateConnectionUi();
  loadOfflineStatus().catch(() => undefined);
});

offlineSyncTimer = window.setInterval(() => {
  if (token && isOnline()) syncOfflineNow().catch(() => undefined);
}, 60_000);

loadAppInfo().catch(() => undefined);

if (token || refreshToken) {
  showApp(true);
  Promise.resolve(token ? true : refreshAuth())
    .then((ok) => {
      if (!ok) throw new Error("Sessão expirada.");
      scheduleRefresh();
      return loadMe();
    })
    .then(() => {
      switchView("dashboard");
      return syncOfflineNow().catch(() => undefined);
    })
    .catch(() => {
      clearAuth();
      showApp(false);
    });
} else {
  showApp(false);
}
