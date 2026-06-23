import { Stack } from "expo-router";
import { StatusBar } from "react-native";

export default function RootLayout() {
  return (
    <>
      <StatusBar barStyle="light-content" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: "#0f172a" },
          headerTintColor: "#f8fafc",
          headerShadowVisible: false,
          contentStyle: { backgroundColor: "#0b1120" },
        }}
      >
        <Stack.Screen name="index" options={{ title: "SannySystem Operação" }} />
      </Stack>
    </>
  );
}
