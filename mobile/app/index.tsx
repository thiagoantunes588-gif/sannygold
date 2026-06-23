import { useCallback, useEffect, useMemo, useState } from "react";
import { AppState, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { CameraCapture } from "@/components/camera-capture";
import { signatureToSvg, SignaturePad } from "@/components/signature-pad";
import { Label, Panel, PrimaryButton, StatusPill, Value } from "@/components/ui";
import { colors, radius } from "@/theme";
import type { AuthSession, OfflineAttachment, OfflineActionType, OfflineQueueItem, ServiceOrder, SignatureStroke } from "@/types/operation";
import { SannyApi } from "@/services/api";
import { currentGps, photoAttachment, registerForNotifications, signatureAttachment } from "@/services/device-capabilities";
import { cachedServiceOrders, enqueueOfflineAction, initOfflineStore, listQueue, queueCounts } from "@/services/offline-store";
import { canUseBiometrics, clearSession, loadApiUrl, loadSession, saveApiUrl, unlockWithBiometrics } from "@/services/session";
import { isConnected, refreshServiceOrderCache, syncPending } from "@/services/sync-engine";

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function orderTitle(order: ServiceOrder): string {
  return order.payload?.title || order.payload?.description || order.id;
}

export default function MobileOperationScreen() {
  const [api, setApi] = useState<SannyApi | null>(null);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [apiUrl, setApiUrl] = useState("");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [biometricsAvailable, setBiometricsAvailable] = useState(false);
  const [connected, setConnected] = useState(false);
  const [queue, setQueue] = useState<OfflineQueueItem[]>([]);
  const [counts, setCounts] = useState({ pending: 0, failed: 0, synced: 0 });
  const [serviceOrders, setServiceOrders] = useState<ServiceOrder[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [draftOrderId, setDraftOrderId] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [checklist, setChecklist] = useState("");
  const [occurrence, setOccurrence] = useState("");
  const [stock, setStock] = useState("");
  const [signerName, setSignerName] = useState("");
  const [signature, setSignature] = useState<SignatureStroke[]>([]);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const selectedOrder = useMemo(
    () => serviceOrders.find((order) => order.id === selectedOrderId) || null,
    [selectedOrderId, serviceOrders],
  );

  const reloadLocalState = useCallback(async () => {
    setConnected(await isConnected());
    setQueue(await listQueue());
    setCounts(await queueCounts());
    const cached = await cachedServiceOrders();
    setServiceOrders(cached);
    if (!selectedOrderId && cached[0]) setSelectedOrderId(cached[0].id);
  }, [selectedOrderId]);

  const runSync = useCallback(
    async (notify = false) => {
      if (!api || !session) return;
      setBusy(true);
      try {
        const summary = await syncPending(api, notify);
        setMessage(summary.message);
      } finally {
        setBusy(false);
        await reloadLocalState();
      }
    },
    [api, reloadLocalState, session],
  );

  useEffect(() => {
    let mounted = true;
    async function boot() {
      await initOfflineStore();
      const nextApi = await SannyApi.create();
      const [savedApiUrl, savedSession, hasBiometrics] = await Promise.all([
        loadApiUrl(),
        loadSession(),
        canUseBiometrics(),
      ]);
      if (!mounted) return;
      setApi(nextApi);
      setApiUrl(savedApiUrl);
      setBiometricsAvailable(hasBiometrics);
      if (savedSession) {
        if (hasBiometrics && !(await unlockWithBiometrics())) {
          await reloadLocalState();
          return;
        }
        nextApi.setSession(savedSession);
        setSession(savedSession);
        await refreshServiceOrderCache(nextApi).catch(() => undefined);
      }
      await reloadLocalState();
    }
    boot().catch((error) => setMessage(error instanceof Error ? error.message : "Falha ao iniciar app."));
    return () => {
      mounted = false;
    };
  }, [reloadLocalState]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (session) runSync(false).catch(() => undefined);
      else reloadLocalState().catch(() => undefined);
    }, 45_000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        if (session) runSync(false).catch(() => undefined);
        else reloadLocalState().catch(() => undefined);
      }
    });
    return () => {
      clearInterval(interval);
      subscription.remove();
    };
  }, [reloadLocalState, runSync, session]);

  async function handleLogin() {
    if (!api) return;
    setBusy(true);
    try {
      await saveApiUrl(apiUrl);
      api.setApiUrl(apiUrl);
      const nextSession = await api.login(login.trim(), password);
      setSession(nextSession);
      const pushToken = await registerForNotifications().catch(() => null);
      await api.registerDevice(pushToken).catch(() => undefined);
      await refreshServiceOrderCache(api).catch(() => undefined);
      await runSync(true);
      setPassword("");
      setMessage("Login realizado.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha no login.");
    } finally {
      setBusy(false);
      await reloadLocalState();
    }
  }

  async function handleBiometricUnlock() {
    const savedSession = await loadSession();
    if (!savedSession || !api) return;
    if (!(await unlockWithBiometrics())) return;
    api.setSession(savedSession);
    setSession(savedSession);
    await runSync(false);
  }

  async function logout() {
    await clearSession();
    api?.setSession(null);
    setSession(null);
    setMessage("Sessão encerrada.");
  }

  async function queueAction(actionType: OfflineActionType, operation: string, extra: Record<string, unknown> = {}, attachments: OfflineAttachment[] = []) {
    const serviceOrderId = selectedOrder?.id || draftOrderId || `mobile-os-${Date.now()}`;
    if (!selectedOrder && !draftOrderId) setDraftOrderId(serviceOrderId);
    const gps = actionType === "CHECK_IN" || actionType === "CHECK_OUT" ? await currentGps() : null;
    await enqueueOfflineAction({
      actionType,
      entity: "serviceOrder",
      entityId: serviceOrderId,
      operation,
      baseVersion: selectedOrder?.version || null,
      payload: {
        serviceOrderId,
        title: draftTitle || selectedOrder ? (selectedOrder ? orderTitle(selectedOrder) : draftTitle) : "Ordem criada no celular",
        checklist: parseLines(checklist).map((label) => ({ label, done: true })),
        notes: occurrence,
        stockMovements: parseLines(stock),
        signerName,
        at: new Date().toISOString(),
        gps,
        source: "mobile",
        ...extra,
        serviceOrderPayload: {
          title: draftTitle || (selectedOrder ? orderTitle(selectedOrder) : "Ordem criada no celular"),
          description: occurrence,
        },
      },
      attachments,
    });
    setMessage(connected ? "Ação salva. Sincronização iniciada." : "Ação salva offline.");
    await reloadLocalState();
    if (connected) await runSync(false);
  }

  async function handlePhoto(uri: string) {
    const attachment = await photoAttachment(uri);
    await queueAction("PHOTO", "photo.capture", { photoCount: 1 }, [attachment]);
  }

  async function handleSignature() {
    if (!signature.length) {
      setMessage("Assinatura vazia.");
      return;
    }
    const svg = signatureToSvg(signature);
    await queueAction("SIGNATURE", "signature.capture", { signatureStrokes: signature }, [signatureAttachment(svg)]);
    setSignature([]);
    setSignerName("");
  }

  if (!session) {
    return (
      <ScrollView contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ padding: 18, gap: 16 }}>
        <Panel>
          <Text selectable style={{ color: colors.text, fontSize: 26, fontWeight: "900" }}>
            Operação mobile
          </Text>
          <Text selectable style={{ color: colors.muted, lineHeight: 20 }}>
            Check-in, fotos, assinatura, checklist, estoque e ocorrências com fila offline.
          </Text>
        </Panel>
        <Panel>
          <Label>API do SannySystem</Label>
          <TextInput
            value={apiUrl}
            onChangeText={setApiUrl}
            autoCapitalize="none"
            style={inputStyle}
            placeholder="https://sua-api/api"
            placeholderTextColor={colors.muted}
          />
          <Label>Login</Label>
          <TextInput value={login} onChangeText={setLogin} autoCapitalize="none" style={inputStyle} />
          <Label>Senha</Label>
          <TextInput value={password} onChangeText={setPassword} secureTextEntry style={inputStyle} />
          <PrimaryButton disabled={busy || !login || !password} onPress={handleLogin}>
            Entrar
          </PrimaryButton>
          {biometricsAvailable ? (
            <PrimaryButton variant="secondary" onPress={handleBiometricUnlock}>
              Entrar com biometria
            </PrimaryButton>
          ) : null}
        </Panel>
        <StatusArea connected={connected} counts={counts} message={message} />
      </ScrollView>
    );
  }

  return (
    <>
      <ScrollView contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ padding: 14, gap: 14, paddingBottom: 34 }}>
        <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
          <StatusPill label={connected ? "Online" : "Offline"} tone={connected ? "ok" : "danger"} />
          <StatusPill label={`Fila ${counts.pending + counts.failed}`} tone={counts.failed ? "warn" : "info"} />
          <StatusPill label={session.user.roleLabel} tone="info" />
        </View>

        <View style={{ flexDirection: "row", gap: 10 }}>
          <Panel style={{ flex: 1 }}>
            <Label>Pendentes</Label>
            <Value>{counts.pending + counts.failed}</Value>
          </Panel>
          <Panel style={{ flex: 1 }}>
            <Label>Sincronizadas</Label>
            <Value>{counts.synced}</Value>
          </Panel>
        </View>

        <Panel>
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
            <View style={{ flex: 1 }}>
              <Text selectable style={{ color: colors.text, fontSize: 18, fontWeight: "900" }}>
                {session.user.name}
              </Text>
              <Text selectable style={{ color: colors.muted }}>{session.user.email}</Text>
            </View>
            <PrimaryButton variant="secondary" onPress={logout}>
              Sair
            </PrimaryButton>
          </View>
        </Panel>

        <Panel>
          <Label>Ordem de serviço</Label>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            <OrderChip selected={!selectedOrderId} title="Nova OS" onPress={() => setSelectedOrderId(null)} />
            {serviceOrders.map((order) => (
              <OrderChip
                key={order.id}
                selected={selectedOrderId === order.id}
                title={orderTitle(order)}
                status={order.status}
                onPress={() => setSelectedOrderId(order.id)}
              />
            ))}
          </ScrollView>
          {!selectedOrderId ? (
            <TextInput
              value={draftTitle}
              onChangeText={setDraftTitle}
              style={inputStyle}
              placeholder="Título da nova ordem"
              placeholderTextColor={colors.muted}
            />
          ) : null}
        </Panel>

        <Panel>
          <Label>Checklist</Label>
          <TextInput
            value={checklist}
            onChangeText={setChecklist}
            multiline
            numberOfLines={5}
            style={[inputStyle, { minHeight: 118, textAlignVertical: "top" }]}
            placeholder="Um item por linha"
            placeholderTextColor={colors.muted}
          />
          <View style={gridStyle}>
            <PrimaryButton onPress={() => queueAction("CHECKLIST", "checklist.save")}>Checklist</PrimaryButton>
            <PrimaryButton onPress={() => queueAction("CHECK_IN", "check-in")}>Check-in</PrimaryButton>
            <PrimaryButton onPress={() => queueAction("CHECK_OUT", "check-out")}>Check-out</PrimaryButton>
          </View>
        </Panel>

        <Panel>
          <Label>Fotos e assinatura</Label>
          <PrimaryButton onPress={() => setCameraOpen(true)}>Abrir câmera</PrimaryButton>
          <TextInput
            value={signerName}
            onChangeText={setSignerName}
            style={inputStyle}
            placeholder="Nome de quem assinou"
            placeholderTextColor={colors.muted}
          />
          <SignaturePad strokes={signature} onChange={setSignature} />
          <PrimaryButton onPress={handleSignature}>Salvar assinatura</PrimaryButton>
        </Panel>

        <Panel>
          <Label>Estoque</Label>
          <TextInput
            value={stock}
            onChangeText={setStock}
            multiline
            numberOfLines={3}
            style={[inputStyle, { minHeight: 82, textAlignVertical: "top" }]}
            placeholder="Ex.: 12 cadeiras retiradas"
            placeholderTextColor={colors.muted}
          />
          <PrimaryButton onPress={() => queueAction("OCCURRENCE", "stock.movement", { stockMovements: parseLines(stock) })}>
            Registrar estoque
          </PrimaryButton>
        </Panel>

        <Panel>
          <Label>Ocorrência</Label>
          <TextInput
            value={occurrence}
            onChangeText={setOccurrence}
            multiline
            numberOfLines={4}
            style={[inputStyle, { minHeight: 98, textAlignVertical: "top" }]}
            placeholder="Descreva a ocorrência"
            placeholderTextColor={colors.muted}
          />
          <View style={gridStyle}>
            <PrimaryButton onPress={() => queueAction("SERVICE_ORDER", "service-order.save")}>Salvar OS</PrimaryButton>
            <PrimaryButton onPress={() => queueAction("OCCURRENCE", "occurrence.save")}>Ocorrência</PrimaryButton>
            <PrimaryButton disabled={busy} onPress={() => runSync(true)}>
              Sincronizar
            </PrimaryButton>
          </View>
        </Panel>

        <Panel>
          <Label>Fila local</Label>
          {queue.slice(0, 12).map((item) => (
            <View key={item.clientMutationId} style={{ borderTopColor: colors.line, borderTopWidth: 1, paddingTop: 10, gap: 2 }}>
              <Text selectable style={{ color: colors.text, fontWeight: "800" }}>
                {item.operation} / {item.actionType}
              </Text>
              <Text selectable style={{ color: colors.muted, fontSize: 12 }}>
                {item.localStatus} - {new Date(item.createdAt).toLocaleString("pt-BR")}
              </Text>
              {item.lastError ? (
                <Text selectable style={{ color: colors.warn, fontSize: 12 }}>
                  {item.lastError}
                </Text>
              ) : null}
            </View>
          ))}
          {!queue.length ? <Text selectable style={{ color: colors.muted }}>Fila vazia.</Text> : null}
        </Panel>

        <StatusArea connected={connected} counts={counts} message={message} />
      </ScrollView>
      <CameraCapture visible={cameraOpen} onClose={() => setCameraOpen(false)} onPhoto={handlePhoto} />
    </>
  );
}

function OrderChip({
  selected,
  title,
  status,
  onPress,
}: {
  selected: boolean;
  title: string;
  status?: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={{
        minWidth: 132,
        maxWidth: 220,
        borderRadius: radius.md,
        padding: 10,
        gap: 4,
        backgroundColor: selected ? colors.accent : colors.panelSoft,
        borderColor: selected ? colors.accent : colors.line,
        borderWidth: 1,
      }}
    >
      <Text numberOfLines={2} style={{ color: selected ? colors.accentText : colors.text, fontWeight: "900" }}>
        {title}
      </Text>
      {status ? (
        <Text style={{ color: selected ? colors.accentText : colors.muted, fontSize: 12 }}>{status}</Text>
      ) : null}
    </Pressable>
  );
}

function StatusArea({
  connected,
  counts,
  message,
}: {
  connected: boolean;
  counts: { pending: number; failed: number; synced: number };
  message: string;
}) {
  return (
    <Panel>
      <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
        <StatusPill label={connected ? "Online" : "Offline"} tone={connected ? "ok" : "danger"} />
        <StatusPill label={`${counts.pending} pendentes`} tone={counts.pending ? "warn" : "ok"} />
        <StatusPill label={`${counts.failed} falhas`} tone={counts.failed ? "danger" : "ok"} />
      </View>
      {message ? (
        <Text selectable style={{ color: colors.muted, lineHeight: 20 }}>
          {message}
        </Text>
      ) : null}
    </Panel>
  );
}

const inputStyle = {
  minHeight: 46,
  borderRadius: radius.md,
  borderColor: colors.line,
  borderWidth: 1,
  backgroundColor: colors.panelSoft,
  color: colors.text,
  paddingHorizontal: 12,
  paddingVertical: 10,
  fontSize: 15,
} as const;

const gridStyle = {
  flexDirection: "row",
  flexWrap: "wrap",
  gap: 8,
} as const;
