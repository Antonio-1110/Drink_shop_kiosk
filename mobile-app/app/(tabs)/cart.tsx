import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import LevelPicker from '@/components/LevelPicker';
import { colors } from '@/constants/theme';
import { ApiError, placeOrder } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { formatPrice, itemPrice, SIZE } from '@/lib/menu';

export default function CartScreen() {
  const { shop, cartItems, updateCartItem, removeFromCart, setLastOrder } = useCart();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const total = cartItems.reduce((sum, item) => sum + itemPrice(item), 0);

  const checkout = async () => {
    if (!shop) return;
    setSubmitting(true);
    setError(null);
    try {
      const order = await placeOrder(shop.id, cartItems);
      setLastOrder(order);
      router.push({ pathname: '/payment/[orderId]', params: { orderId: order.id } });
    } catch (err) {
      // the backend lists the drinks it no longer has stock for
      const soldOutIds: number[] = (err as ApiError).data?.drinks ?? [];
      const soldOut = cartItems.filter((item) => soldOutIds.includes(item.drink.id)).map((item) => item.drink.name);
      setError(soldOut.length
        ? `Sorry, not enough stock for: ${[...new Set(soldOut)].join(', ')}`
        : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.screen}>
      <FlatList
        data={cartItems}
        keyExtractor={(_, index) => String(index)}
        contentContainerStyle={{ padding: 12, gap: 10 }}
        ListEmptyComponent={<Text style={styles.empty}>Your cart is empty.</Text>}
        renderItem={({ item, index }) => (
          <View style={styles.item}>
            <View style={styles.itemHeader}>
              <Text style={styles.itemName}>{item.drink.name} ({item.size === SIZE.LARGE ? 'L' : 'S'})</Text>
              <Text style={styles.itemPrice}>{formatPrice(itemPrice(item))}</Text>
            </View>
            <LevelPicker label="Sugar" value={item.sugar} onChange={(sugar) => updateCartItem(index, { sugar })} />
            <LevelPicker label="Ice" value={item.ice} onChange={(ice) => updateCartItem(index, { ice })} />
            <Pressable accessibilityRole="button" onPress={() => removeFromCart(index)} style={styles.remove}>
              <Text style={styles.removeText}>Remove</Text>
            </Pressable>
          </View>
        )}
      />

      <ErrorBanner message={error} />

      <View style={styles.footer}>
        <View>
          <Text style={styles.muted}>Total</Text>
          <Text style={styles.total}>{formatPrice(total)}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={checkout}
          disabled={cartItems.length === 0 || submitting}
          style={[styles.payButton, (cartItems.length === 0 || submitting) && { opacity: 0.5 }]}>
          <Text style={styles.payText}>{submitting ? 'Placing order...' : 'Place order →'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40 },
  item: { backgroundColor: colors.surface, borderRadius: 10, padding: 12, gap: 8 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  itemName: { fontSize: 16, fontWeight: '600', color: colors.text, flexShrink: 1 },
  itemPrice: { fontSize: 16, fontWeight: '600', color: colors.accent },
  remove: { alignSelf: 'flex-end', backgroundColor: colors.errorBg, borderRadius: 6, paddingVertical: 6, paddingHorizontal: 12 },
  removeText: { color: colors.errorText },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
    borderTopWidth: 2,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  muted: { color: colors.muted },
  total: { fontSize: 22, fontWeight: 'bold', color: colors.text },
  payButton: { backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 22 },
  payText: { color: colors.surface, fontWeight: 'bold', fontSize: 16 },
});
