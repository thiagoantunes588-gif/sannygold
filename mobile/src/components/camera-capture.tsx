import { useRef, useState } from "react";
import { Modal, Pressable, Text, View } from "react-native";
import { CameraView, type CameraType, useCameraPermissions } from "expo-camera";
import { colors } from "@/theme";
import { PrimaryButton } from "./ui";

type CameraCaptureProps = {
  visible: boolean;
  onClose: () => void;
  onPhoto: (uri: string) => Promise<void>;
};

export function CameraCapture({ visible, onClose, onPhoto }: CameraCaptureProps) {
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [facing, setFacing] = useState<CameraType>("back");
  const [busy, setBusy] = useState(false);

  async function takePhoto() {
    if (!cameraRef.current || busy) return;
    setBusy(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.78 });
      if (photo?.uri) await onPhoto(photo.uri);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="fullScreen">
      <View style={{ flex: 1, backgroundColor: "#000" }}>
        {permission?.granted ? (
          <CameraView ref={cameraRef} style={{ flex: 1 }} facing={facing} />
        ) : (
          <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 16 }}>
            <Text selectable style={{ color: colors.text, textAlign: "center", fontSize: 16 }}>
              Permita o acesso à câmera para registrar fotos da operação.
            </Text>
            <PrimaryButton onPress={requestPermission}>Permitir câmera</PrimaryButton>
          </View>
        )}

        <View
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            padding: 22,
            gap: 14,
            backgroundColor: "rgba(0,0,0,0.54)",
          }}
        >
          <Pressable
            disabled={!permission?.granted || busy}
            onPress={takePhoto}
            style={({ pressed }) => ({
              alignSelf: "center",
              width: 74,
              height: 74,
              borderRadius: 999,
              borderWidth: 5,
              borderColor: "#fff",
              backgroundColor: pressed ? "#e5e7eb" : "#fff",
              opacity: busy ? 0.55 : 1,
            })}
          />
          <View style={{ flexDirection: "row", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <PrimaryButton variant="secondary" onPress={onClose}>
                Fechar
              </PrimaryButton>
            </View>
            <View style={{ flex: 1 }}>
              <PrimaryButton variant="secondary" onPress={() => setFacing((value) => (value === "back" ? "front" : "back"))}>
                Virar câmera
              </PrimaryButton>
            </View>
          </View>
        </View>
      </View>
    </Modal>
  );
}
