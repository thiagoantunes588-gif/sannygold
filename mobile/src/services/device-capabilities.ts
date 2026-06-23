import Constants from "expo-constants";
import * as Device from "expo-device";
import * as FileSystem from "expo-file-system";
import * as Location from "expo-location";
import * as Notifications from "expo-notifications";
import type { OfflineAttachment } from "@/types/operation";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function currentGps(): Promise<Record<string, number> | null> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) return null;
  const position = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced,
  });
  return {
    lat: position.coords.latitude,
    lng: position.coords.longitude,
    accuracy: position.coords.accuracy || 0,
  };
}

function fileNameFromUri(uri: string): string {
  const clean = uri.split("?")[0];
  return clean.split("/").pop() || `foto-${Date.now()}.jpg`;
}

export async function photoAttachment(uri: string): Promise<OfflineAttachment> {
  const base64 = await FileSystem.readAsStringAsync(uri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  const info = await FileSystem.getInfoAsync(uri);
  return {
    kind: "PHOTO",
    fileName: fileNameFromUri(uri),
    mimeType: "image/jpeg",
    sizeBytes: info.exists && "size" in info ? info.size || 0 : 0,
    dataBase64: `data:image/jpeg;base64,${base64}`,
  };
}

function base64Encode(input: string): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";
  let output = "";
  let i = 0;
  const encoded = unescape(encodeURIComponent(input));
  while (i < encoded.length) {
    const chr1 = encoded.charCodeAt(i++);
    const chr2 = encoded.charCodeAt(i++);
    const chr3 = encoded.charCodeAt(i++);
    const enc1 = chr1 >> 2;
    const enc2 = ((chr1 & 3) << 4) | (chr2 >> 4);
    let enc3 = ((chr2 & 15) << 2) | (chr3 >> 6);
    let enc4 = chr3 & 63;
    if (Number.isNaN(chr2)) {
      enc3 = 64;
      enc4 = 64;
    } else if (Number.isNaN(chr3)) {
      enc4 = 64;
    }
    output += chars.charAt(enc1) + chars.charAt(enc2) + chars.charAt(enc3) + chars.charAt(enc4);
  }
  return output;
}

export function signatureAttachment(svg: string): OfflineAttachment {
  const dataBase64 = `data:image/svg+xml;base64,${base64Encode(svg)}`;
  return {
    kind: "SIGNATURE",
    fileName: `assinatura-${Date.now()}.svg`,
    mimeType: "image/svg+xml",
    sizeBytes: svg.length,
    dataBase64,
  };
}

export async function registerForNotifications(): Promise<string | null> {
  if (!Device.isDevice) return null;
  const current = await Notifications.getPermissionsAsync();
  let finalStatus = current.status;
  if (finalStatus !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    finalStatus = requested.status;
  }
  if (finalStatus !== "granted") return null;
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId) return null;
  const token = await Notifications.getExpoPushTokenAsync({ projectId });
  return token.data;
}

export async function notifySyncResult(title: string, body: string): Promise<void> {
  await Notifications.scheduleNotificationAsync({
    content: { title, body },
    trigger: null,
  });
}
