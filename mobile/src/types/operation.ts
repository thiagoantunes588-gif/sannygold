export type RoleLabel = "administrador" | "operação" | "motorista" | "financeiro" | "almoxarifado" | string;

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  roleLabel: RoleLabel;
  permissions: string[];
};

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
};

export type ServiceOrder = {
  id: string;
  status: string;
  version: number;
  scheduledAt?: string | null;
  updatedAt?: string | null;
  payload?: {
    title?: string;
    description?: string;
    operational?: Record<string, unknown>;
    [key: string]: unknown;
  } | null;
};

export type OfflineActionType =
  | "CHECKLIST"
  | "CHECK_IN"
  | "CHECK_OUT"
  | "PHOTO"
  | "SIGNATURE"
  | "SERVICE_ORDER"
  | "OCCURRENCE";

export type OfflineAttachment = {
  kind: "PHOTO" | "SIGNATURE" | "DOCUMENT";
  fileName: string;
  mimeType?: string | null;
  sizeBytes?: number | null;
  checksum?: string | null;
  dataBase64?: string | null;
};

export type OfflineQueueItem = {
  clientMutationId: string;
  actionType: OfflineActionType;
  entity: "serviceOrder";
  entityId?: string | null;
  operation: string;
  payload: Record<string, unknown>;
  baseVersion?: number | null;
  createdAt: string;
  attachments?: OfflineAttachment[];
  localStatus: "pending" | "sending" | "synced" | "failed";
  lastError?: string | null;
};

export type SyncSummary = {
  accepted: number;
  sent: number;
  failed: number;
  conflicts: number;
  message: string;
};

export type SignatureStroke = Array<{ x: number; y: number }>;
