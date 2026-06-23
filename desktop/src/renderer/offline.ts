type SannyOfflineAttachment = {
  kind: "PHOTO" | "SIGNATURE" | "DOCUMENT";
  fileName: string;
  mimeType?: string | null;
  sizeBytes?: number | null;
  checksum?: string | null;
  dataBase64?: string | null;
};

type SannyOfflineQueueItem = {
  clientMutationId: string;
  actionType: "CHECKLIST" | "CHECK_IN" | "CHECK_OUT" | "PHOTO" | "SIGNATURE" | "SERVICE_ORDER" | "OCCURRENCE";
  entity: "serviceOrder";
  entityId?: string | null;
  operation: string;
  payload: Record<string, unknown>;
  baseVersion?: number | null;
  createdAt: string;
  attachments?: SannyOfflineAttachment[];
  localStatus: "pending" | "sending" | "synced" | "failed";
  lastError?: string | null;
};

type SannyCachedServiceOrder = {
  id: string;
  status?: string;
  version?: number;
  scheduledAt?: string | null;
  payload?: Record<string, unknown> | null;
  updatedAt?: string;
  cachedAt: string;
};

type SannyOfflineApi = {
  queueAction: (item: Omit<SannyOfflineQueueItem, "clientMutationId" | "createdAt" | "localStatus"> & {
    clientMutationId?: string;
    createdAt?: string;
  }) => Promise<SannyOfflineQueueItem>;
  listQueue: () => Promise<SannyOfflineQueueItem[]>;
  pendingQueue: () => Promise<SannyOfflineQueueItem[]>;
  markSynced: (ids: string[]) => Promise<void>;
  markFailed: (ids: string[], message: string) => Promise<void>;
  cacheServiceOrders: (items: Array<Record<string, unknown>>) => Promise<void>;
  cachedServiceOrders: () => Promise<SannyCachedServiceOrder[]>;
  fileToAttachment: (file: File, kind: SannyOfflineAttachment["kind"]) => Promise<SannyOfflineAttachment>;
  pendingCount: () => Promise<number>;
};

interface Window {
  sannyOffline?: SannyOfflineApi;
}

const offlineDbName = "SannySystemOffline";
const offlineDbVersion = 1;

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Falha no cache local."));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("Falha ao gravar cache local."));
    transaction.onabort = () => reject(transaction.error || new Error("Operação de cache cancelada."));
  });
}

function openOfflineDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(offlineDbName, offlineDbVersion);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("queue")) {
        const queue = db.createObjectStore("queue", { keyPath: "clientMutationId" });
        queue.createIndex("localStatus", "localStatus", { unique: false });
        queue.createIndex("createdAt", "createdAt", { unique: false });
      }
      if (!db.objectStoreNames.contains("serviceOrders")) {
        const serviceOrders = db.createObjectStore("serviceOrders", { keyPath: "id" });
        serviceOrders.createIndex("status", "status", { unique: false });
        serviceOrders.createIndex("cachedAt", "cachedAt", { unique: false });
      }
      if (!db.objectStoreNames.contains("meta")) {
        db.createObjectStore("meta", { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Não foi possível abrir o cache offline."));
  });
}

function createMutationId(): string {
  const random = crypto.getRandomValues(new Uint32Array(4));
  return `offline-${Date.now()}-${Array.from(random).map((part) => part.toString(16)).join("")}`;
}

async function putQueueItem(item: SannyOfflineQueueItem): Promise<void> {
  const db = await openOfflineDb();
  const transaction = db.transaction("queue", "readwrite");
  transaction.objectStore("queue").put(item);
  await transactionDone(transaction);
  db.close();
}

async function getQueueItems(): Promise<SannyOfflineQueueItem[]> {
  const db = await openOfflineDb();
  const transaction = db.transaction("queue", "readonly");
  const items = await requestToPromise<SannyOfflineQueueItem[]>(transaction.objectStore("queue").getAll());
  await transactionDone(transaction);
  db.close();
  return items.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

async function updateQueueItems(ids: string[], patch: Partial<SannyOfflineQueueItem>): Promise<void> {
  if (!ids.length) return;
  const db = await openOfflineDb();
  const transaction = db.transaction("queue", "readwrite");
  const store = transaction.objectStore("queue");
  for (const id of ids) {
    const current = await requestToPromise<SannyOfflineQueueItem | undefined>(store.get(id));
    if (!current) continue;
    store.put({ ...current, ...patch });
  }
  await transactionDone(transaction);
  db.close();
}

async function queueAction(
  input: Omit<SannyOfflineQueueItem, "clientMutationId" | "createdAt" | "localStatus"> & {
    clientMutationId?: string;
    createdAt?: string;
  },
): Promise<SannyOfflineQueueItem> {
  const item: SannyOfflineQueueItem = {
    ...input,
    clientMutationId: input.clientMutationId || createMutationId(),
    createdAt: input.createdAt || new Date().toISOString(),
    localStatus: "pending",
  };
  await putQueueItem(item);
  return item;
}

async function cacheServiceOrders(items: Array<Record<string, unknown>>): Promise<void> {
  const db = await openOfflineDb();
  const transaction = db.transaction("serviceOrders", "readwrite");
  const store = transaction.objectStore("serviceOrders");
  const cachedAt = new Date().toISOString();
  for (const item of items) {
    if (!item.id) continue;
    store.put({ ...item, cachedAt });
  }
  await transactionDone(transaction);
  db.close();
}

async function cachedServiceOrders(): Promise<SannyCachedServiceOrder[]> {
  const db = await openOfflineDb();
  const transaction = db.transaction("serviceOrders", "readonly");
  const items = await requestToPromise<SannyCachedServiceOrder[]>(transaction.objectStore("serviceOrders").getAll());
  await transactionDone(transaction);
  db.close();
  return items.sort((a, b) => String(a.scheduledAt || "").localeCompare(String(b.scheduledAt || "")));
}

function readFileAsDataBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Falha ao ler arquivo."));
    reader.readAsDataURL(file);
  });
}

async function sha256File(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function fileToAttachment(file: File, kind: SannyOfflineAttachment["kind"]): Promise<SannyOfflineAttachment> {
  return {
    kind,
    fileName: file.name || `${kind.toLowerCase()}-${Date.now()}`,
    mimeType: file.type || "application/octet-stream",
    sizeBytes: file.size,
    checksum: await sha256File(file),
    dataBase64: await readFileAsDataBase64(file),
  };
}

window.sannyOffline = {
  queueAction,
  listQueue: getQueueItems,
  pendingQueue: async () => (await getQueueItems()).filter((item) => item.localStatus === "pending" || item.localStatus === "failed"),
  markSynced: (ids: string[]) => updateQueueItems(ids, { localStatus: "synced", lastError: null }),
  markFailed: (ids: string[], message: string) => updateQueueItems(ids, { localStatus: "failed", lastError: message }),
  cacheServiceOrders,
  cachedServiceOrders,
  fileToAttachment,
  pendingCount: async () => (await getQueueItems()).filter((item) => item.localStatus === "pending" || item.localStatus === "failed").length,
};
