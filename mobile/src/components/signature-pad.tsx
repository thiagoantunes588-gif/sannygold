import { useMemo, useRef, useState } from "react";
import { PanResponder, Text, View } from "react-native";
import Svg, { Polyline } from "react-native-svg";
import { colors, radius } from "@/theme";
import type { SignatureStroke } from "@/types/operation";
import { PrimaryButton } from "./ui";

type SignaturePadProps = {
  strokes: SignatureStroke[];
  onChange: (strokes: SignatureStroke[]) => void;
};

export function signatureToSvg(strokes: SignatureStroke[], width = 720, height = 240): string {
  const lines = strokes
    .filter((stroke) => stroke.length > 1)
    .map((stroke) => {
      const points = stroke.map((point) => `${Math.round(point.x)},${Math.round(point.y)}`).join(" ");
      return `<polyline points="${points}" fill="none" stroke="#111827" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" />`;
    })
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#ffffff"/>${lines}</svg>`;
}

export function SignaturePad({ strokes, onChange }: SignaturePadProps) {
  const [size, setSize] = useState({ width: 1, height: 1 });
  const currentStroke = useRef<SignatureStroke>([]);

  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (event) => {
          const { locationX, locationY } = event.nativeEvent;
          currentStroke.current = [{ x: (locationX / size.width) * 720, y: (locationY / size.height) * 240 }];
        },
        onPanResponderMove: (event) => {
          const { locationX, locationY } = event.nativeEvent;
          currentStroke.current = [
            ...currentStroke.current,
            { x: (locationX / size.width) * 720, y: (locationY / size.height) * 240 },
          ];
          onChange([...strokes, currentStroke.current]);
        },
        onPanResponderRelease: () => {
          if (currentStroke.current.length > 1) onChange([...strokes, currentStroke.current]);
          currentStroke.current = [];
        },
      }),
    [onChange, size.height, size.width, strokes],
  );

  return (
    <View style={{ gap: 8 }}>
      <View
        onLayout={(event) => setSize(event.nativeEvent.layout)}
        {...responder.panHandlers}
        style={{
          height: 170,
          borderRadius: radius.md,
          overflow: "hidden",
          backgroundColor: "#ffffff",
          borderColor: colors.line,
          borderWidth: 1,
        }}
      >
        <Svg width="100%" height="100%" viewBox="0 0 720 240">
          {strokes.map((stroke, index) => (
            <Polyline
              key={`${index}-${stroke.length}`}
              points={stroke.map((point) => `${point.x},${point.y}`).join(" ")}
              fill="none"
              stroke="#111827"
              strokeWidth="5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </Svg>
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <Text selectable style={{ color: colors.muted, fontSize: 12 }}>
          {strokes.length ? `${strokes.length} traços capturados` : "Assinatura vazia"}
        </Text>
        <PrimaryButton variant="secondary" onPress={() => onChange([])}>
          Limpar
        </PrimaryButton>
      </View>
    </View>
  );
}
