import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import type { AuthSession } from "@/types/operation";

const sessionKey = "sannysystem.mobile.session";
const apiUrlKey = "sannysystem.mobile.apiUrl";

export async function saveSession(session: AuthSession): Promise<void> {
  await SecureStore.setItemAsync(sessionKey, JSON.stringify(session));
}

export async function loadSession(): Promise<AuthSession | null> {
  const value = await SecureStore.getItemAsync(sessionKey);
  return value ? (JSON.parse(value) as AuthSession) : null;
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(sessionKey);
}

export async function saveApiUrl(apiUrl: string): Promise<void> {
  await SecureStore.setItemAsync(apiUrlKey, apiUrl.trim());
}

export async function loadApiUrl(): Promise<string> {
  const fromSecureStore = await SecureStore.getItemAsync(apiUrlKey);
  return (
    fromSecureStore ||
    process.env.EXPO_PUBLIC_SANNY_API_URL ||
    "http://127.0.0.1:3000/api"
  ).replace(/\/$/, "");
}

export async function canUseBiometrics(): Promise<boolean> {
  const [hasHardware, enrolled] = await Promise.all([
    LocalAuthentication.hasHardwareAsync(),
    LocalAuthentication.isEnrolledAsync(),
  ]);
  return hasHardware && enrolled;
}

export async function unlockWithBiometrics(): Promise<boolean> {
  if (!(await canUseBiometrics())) return false;
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: "Entrar no SannySystem",
    fallbackLabel: "Usar senha",
    cancelLabel: "Cancelar",
  });
  return result.success;
}
