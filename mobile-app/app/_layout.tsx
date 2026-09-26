import { DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { colors } from '@/constants/theme';
import { CartProvider } from '@/lib/cart';

export {
  // Catch any errors thrown by the Layout component.
  ErrorBoundary,
} from 'expo-router';

export const unstable_settings = {
  // Ensure that reloading on a pushed screen keeps a back button present.
  initialRouteName: '(tabs)',
};

// the kiosk UI is light only, so the app is too
const theme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, primary: colors.primary, background: colors.background },
};

export default function RootLayout() {
  return (
    <CartProvider>
      <ThemeProvider value={theme}>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerStyle: { backgroundColor: colors.header }, headerTintColor: colors.primary }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="designer" options={{ title: 'Design your own' }} />
          <Stack.Screen name="shops" options={{ title: 'Choose a shop', presentation: 'modal' }} />
          <Stack.Screen name="payment/[orderId]" options={{ title: 'Your order', headerBackVisible: false, headerLeft: () => null, gestureEnabled: false }} />
        </Stack>
      </ThemeProvider>
    </CartProvider>
  );
}
