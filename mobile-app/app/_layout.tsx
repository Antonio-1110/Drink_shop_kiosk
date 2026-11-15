import { Fraunces_500Medium, Fraunces_600SemiBold } from '@expo-google-fonts/fraunces';
import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold, useFonts } from '@expo-google-fonts/inter';
import { DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { colors, fonts } from '@/constants/theme';
import { CartProvider } from '@/lib/cart';
import { LanguageProvider, useT } from '@/lib/i18n';

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
  // the system fonts stand in until these load, so nothing waits on them
  useFonts({ Fraunces_500Medium, Fraunces_600SemiBold, Inter_400Regular, Inter_500Medium, Inter_600SemiBold });
  return (
    <LanguageProvider>
      <CartProvider>
        <Screens />
      </CartProvider>
    </LanguageProvider>
  );
}

function Screens() {
  const t = useT();
  return (
      <ThemeProvider value={theme}>
        <StatusBar style="dark" />
        <Stack screenOptions={{
          headerStyle: { backgroundColor: colors.background },
          headerShadowVisible: false,
          headerTitleStyle: { fontFamily: fonts.serif, fontSize: 20, color: colors.text },
          headerTintColor: colors.primary,
        }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="designer" options={{ title: t('title.designer') }} />
          <Stack.Screen name="shops" options={{ title: t('title.shops'), presentation: 'modal' }} />
          <Stack.Screen name="payment/[orderId]" options={{ title: t('title.payment'), headerBackVisible: false, headerLeft: () => null, gestureEnabled: false }} />
        </Stack>
      </ThemeProvider>
  );
}
