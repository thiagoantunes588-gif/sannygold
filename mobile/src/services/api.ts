import Constants from "expo-constants";
import * as Device from "expo-device";
import type { AuthSession, AuthUser, OfflineQueueItem, ServiceOrder } from "@/types/operation";
import { loadApiUrl, loadSession, saveSession } from "./session";

type LoginResponse = {
  token?: string;
  accessToken?: string;
  refreshToken: string;
  user: AuthUser;
};

async function parseJson(response: Response): Promise<Record<string, unknown>> {
  return (await response.json().catch(() => ({}))) as Record<string, unknown>;
}

export class SannyApi {
  constructor(private apiUrl: string, private session: AuthSession | null) {}

  static async create(): Promise<SannyApi> {
    return new SannyApi(await loadApiUrl(), await loadSession());
  }

  setSession(session: AuthSession | null): void {
    this.session = session;
  }

  setApiUrl(apiUrl: string): void {
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  async login(login: string, password: string): Promise<AuthSession> {
    const response = await fetch(`${this.apiUrl}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ login, password }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(String(body.error || "Falha no login."));
    const result = body as LoginResponse;
    const session: AuthSession = {
      accessToken: result.accessToken || result.token || "",
      refreshToken: result.refreshToken,
      user: result.user,
    };
    this.session = session;
    await saveSession(session);
    return session;
  }

  async refresh(): Promise<boolean> {
    if (!this.session?.refreshToken) return false;
    try {
      const response = await fetch(`${this.apiUrl}/auth/refresh`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refreshToken: this.session.refreshToken }),
      });
      const body = await parseJson(response);
      if (!response.ok) throw new Error(String(body.error || "Sessão expirada."));
      const result = body as LoginResponse;
      const nextSession: AuthSession = {
        accessToken: result.accessToken || result.token || "",
        refreshToken: result.refreshToken || this.session.refreshToken,
        user: result.user || this.session.user,
      };
      this.session = nextSession;
      await saveSession(nextSession);
      return true;
    } catch {
      return false;
    }
  }

  async request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
    const headers = new Headers(options.headers);
    headers.set("content-type", "application/json");
    if (this.session?.accessToken) headers.set("authorization", `Bearer ${this.session.accessToken}`);
    const response = await fetch(`${this.apiUrl}${path}`, { ...options, headers });
    const body = await parseJson(response);
    if (response.status === 401 && retry && (await this.refresh())) {
      return this.request<T>(path, options, false);
    }
    if (!response.ok) throw new Error(String(body.error || "Falha de comunicação."));
    return body as T;
  }

  async getServiceOrders(): Promise<ServiceOrder[]> {
    const result = await this.request<{ serviceOrders: ServiceOrder[] }>("/service-orders");
    return result.serviceOrders;
  }

  async sendOfflineItems(items: OfflineQueueItem[]): Promise<{ accepted: number; duplicates: number }> {
    return this.request<{ accepted: number; duplicates: number }>("/offline/queue", {
      method: "POST",
      body: JSON.stringify({
        items: items.map(({ localStatus: _localStatus, lastError: _lastError, ...item }) => item),
      }),
    });
  }

  async processOfflineSync(): Promise<{ queue?: { conflicts?: number } }> {
    return this.request<{ queue?: { conflicts?: number } }>("/offline/sync", { method: "POST" });
  }

  async registerDevice(pushToken?: string | null): Promise<void> {
    await this.request("/mobile/devices", {
      method: "POST",
      body: JSON.stringify({
        deviceId: `${Device.osName || "mobile"}-${Device.modelId || Device.modelName || "device"}`,
        platform: Device.osName || "mobile",
        deviceName: Device.deviceName || Device.modelName || null,
        appVersion: Constants.expoConfig?.version || "1.0.0",
        pushToken,
      }),
    });
  }
}
