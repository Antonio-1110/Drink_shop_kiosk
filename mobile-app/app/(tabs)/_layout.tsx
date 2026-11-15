import { Tabs } from 'expo-router';
import { SymbolView } from 'expo-symbols';

import { colors, fonts } from '@/constants/theme';
import { useCart } from '@/lib/cart';
import { useT } from '@/lib/i18n';
import { cartCount } from '@/lib/menu';

export default function TabLayout() {
  const { cartItems } = useCart();
  const t = useT();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarLabelStyle: { fontFamily: fonts.sansMedium },
        headerStyle: { backgroundColor: colors.background },
        headerShadowVisible: false,
        headerTitleStyle: { fontFamily: fonts.serif, fontSize: 22, color: colors.text },
        headerTintColor: colors.primary,
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: t('tab.menu'),
          // the menu draws its own slim header with the pickup shop
          headerShown: false,
          tabBarIcon: ({ color }) => (
            <SymbolView name={{ ios: 'cup.and.saucer', android: 'local_cafe', web: 'local_cafe' }} tintColor={color} size={26} />
          ),
        }}
      />
      <Tabs.Screen
        name="cart"
        options={{
          title: t('title.order'),
          tabBarLabel: t('tab.order'),
          tabBarBadgeStyle: { backgroundColor: colors.accent },
          tabBarBadge: cartCount(cartItems) || undefined,
          tabBarIcon: ({ color }) => (
            <SymbolView name={{ ios: 'cart', android: 'shopping_cart', web: 'shopping_cart' }} tintColor={color} size={26} />
          ),
        }}
      />
    </Tabs>
  );
}
