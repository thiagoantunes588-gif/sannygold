import { Pressable, Text, View, type PressableProps, type ViewProps } from "react-native";
import { colors, radius } from "@/theme";

export function Panel({ children, style }: ViewProps) {
  return (
    <View
      style={[
        {
          backgroundColor: colors.panel,
          borderColor: colors.line,
          borderWidth: 1,
          borderRadius: radius.lg,
          padding: 14,
          gap: 12,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function Label({ children }: { children: string }) {
  return (
    <Text selectable style={{ color: colors.muted, fontSize: 12, fontWeight: "700" }}>
      {children}
    </Text>
  );
}

export function Value({ children }: { children: string | number }) {
  return (
    <Text selectable style={{ color: colors.text, fontSize: 22, fontWeight: "800", fontVariant: ["tabular-nums"] }}>
      {children}
    </Text>
  );
}

export function PrimaryButton({
  children,
  disabled,
  variant = "primary",
  ...props
}: PressableProps & { children: string; variant?: "primary" | "secondary" | "danger" }) {
  const backgroundColor =
    variant === "primary" ? colors.accent : variant === "danger" ? colors.danger : colors.panelSoft;
  const color = variant === "primary" ? colors.accentText : colors.text;
  return (
    <Pressable
      {...props}
      disabled={disabled}
      style={({ pressed }) => ({
        minHeight: 46,
        alignItems: "center",
        justifyContent: "center",
        borderRadius: radius.md,
        paddingHorizontal: 14,
        paddingVertical: 10,
        backgroundColor,
        borderColor: variant === "secondary" ? colors.line : backgroundColor,
        borderWidth: 1,
        opacity: disabled ? 0.45 : pressed ? 0.8 : 1,
      })}
    >
      <Text style={{ color, fontWeight: "800", fontSize: 14 }}>{children}</Text>
    </Pressable>
  );
}

export function StatusPill({ label, tone }: { label: string; tone: "ok" | "warn" | "danger" | "info" }) {
  const toneColor = tone === "ok" ? colors.ok : tone === "warn" ? colors.warn : tone === "danger" ? colors.danger : colors.info;
  return (
    <View
      style={{
        borderColor: toneColor,
        borderWidth: 1,
        borderRadius: 999,
        paddingHorizontal: 10,
        paddingVertical: 5,
        backgroundColor: `${toneColor}22`,
      }}
    >
      <Text selectable style={{ color: toneColor, fontSize: 12, fontWeight: "800" }}>
        {label}
      </Text>
    </View>
  );
}
