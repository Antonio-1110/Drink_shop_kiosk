import { Tabs } from 'expo-router';
import { SymbolView } from 'expo-symbols';

import { colors } from '@/constants/theme';
import { useCart } from '@/lib/cart';

export default function TabLayout() {
  const { cartItems } = useCart();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.navy,
        tabBarStyle: { backgroundColor: colors.lightBlue },
        headerStyle: { backgroundColor: colors.paleBlue },
        headerTintColor: colors.navy,
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Menu',
          tabBarIcon: ({ color }) => (
            <SymbolView name={{ ios: 'cup.and.saucer', android: 'local_cafe', web: 'local_cafe' }} tintColor={color} size={26} />
          ),
        }}
      />
      <Tabs.Screen
        name="cart"
        options={{
          title: 'Cart',
          tabBarBadge: cartItems.length || undefined,
          tabBarIcon: ({ color }) => (
            <SymbolView name={{ ios: 'cart', android: 'shopping_cart', web: 'shopping_cart' }} tintColor={color} size={26} />
          ),
        }}
      />
    </Tabs>
  );
}
