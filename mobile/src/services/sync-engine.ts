import * as Network from "expo-network";
import type { SyncSummary } from "@/types/operation";
import { SannyApi } from "./api";
import { cacheServiceOrders, markQueueStatus, pendingQueue } from "./offline-store";
import { notifySyncResult } from "./device-capabilities";

export async function isConnected(): Promise<boolean> {
  const state = await Network.getNetworkStateAsync();
  return Boolean(state.isConnected && state.isInternetReachable !== false);
}

export async function refreshServiceOrderCache(api: SannyApi): Promise<void> {
  const serviceOrders = await api.getServiceOrders();
  await cacheServiceOrders(serviceOrders);
}

export async function syncPending(api: SannyApi, notify = false): Promise<SyncSummary> {
  if (!(await isConnected())) {
    return { accepted: 0, sent: 0, failed: 0, conflicts: 0, message: "Sem conexão." };
  }

  const items = await pendingQueue();
  if (!items.length) {
    await refreshServiceOrderCache(api).catch(() => undefined);
    return { accepted: 0, sent: 0, failed: 0, conflicts: 0, message: "Fila local vazia." };
  }

  const ids = items.map((item) => item.clientMutationId);
  await markQueueStatus(ids, "sending");

  try {
    const queueResult = await api.sendOfflineItems(items);
    const serverSync = await api.processOfflineSync();
    await markQueueStatus(ids, "synced");
    await refreshServiceOrderCache(api).catch(() => undefined);
    const conflicts = Number(serverSync.queue?.conflicts || 0);
    const summary = {
      accepted: queueResult.accepted,
      sent: items.length,
      failed: 0,
      conflicts,
      message: conflicts ? "Sincronização concluída com conflito." : "Sincronização concluída.",
    };
    if (notify) {
      await notifySyncResult(
        conflicts ? "Conflito de sincronização" : "SannySystem sincronizado",
        `${summary.sent} ações enviadas. ${conflicts} conflitos.`,
      );
    }
    return summary;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Falha ao sincronizar.";
    await markQueueStatus(ids, "failed", message);
    if (notify) await notifySyncResult("Falha na sincronização", message);
    return { accepted: 0, sent: items.length, failed: items.length, conflicts: 0, message };
  }
}
