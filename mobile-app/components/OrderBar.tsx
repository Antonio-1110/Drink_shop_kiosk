import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '@/constants/theme';
import { useCart } from '@/lib/cart';
import { formatPrice, itemPrice } from '@/lib/menu';

// The running order floating above the tab bar, like a food-chain app's cart bar.
export default function OrderBar() {
  const { cartItems } = useCart();
  if (cartItems.length === 0) return null;
  const total = cartItems.reduce((sum, item) => sum + itemPrice(item), 0);
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={`Review order, ${cartItems.length} drinks, ${formatPrice(total)}`}
      onPress={() => router.navigate('/cart')} style={({ pressed }) => [styles.bar, pressed && { opacity: 0.9 }]}>
      <View style={styles.count}><Text style={styles.countText}>{cartItems.length}</Text></View>
      <Text style={styles.total}>{formatPrice(total)}</Text>
      <Text style={styles.go}>Review order</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: {
    position: 'absolute',
    left: 16,
    right: 16,
    bottom: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 8,
    paddingRight: 20,
    borderRadius: 30,
    backgroundColor: colors.text,
    boxShadow: '0 8px 24px rgba(43,35,32,0.28)',
  },
  count: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' },
  countText: { fontFamily: fonts.sansBold, fontSize: 16, color: colors.surface },
  total: { flex: 1, fontFamily: fonts.sansBold, fontSize: 17, color: colors.surface },
  go: { fontFamily: fonts.sansBold, fontSize: 15, color: colors.surface },
});
