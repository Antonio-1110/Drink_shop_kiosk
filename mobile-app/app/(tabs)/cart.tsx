import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import DrinkArt from '@/components/DrinkArt';
import DrinkSheet from '@/components/DrinkSheet';
import ErrorBanner from '@/components/ErrorBanner';
import { colors, fonts } from '@/constants/theme';
import { ApiError, placeOrder } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { formatPrice, itemPrice, LEVELS, SIZE } from '@/lib/menu';

const levelLabel = (value: number) => LEVELS.find((level) => level.value === value)?.label;

export default function CartScreen() {
  const { shop, cartItems, updateCartItem, removeFromCart, setLastOrder } = useCart();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState<number | null>(null); // the line whose options are open
  const total = cartItems.reduce((sum, item) => sum + itemPrice(item), 0);
  const blocked = cartItems.length === 0 || submitting;

  const checkout = async () => {
    if (!shop) return;
    setSubmitting(true);
    setError(null);
    try {
      const order = await placeOrder(shop.id, cartItems);
      setLastOrder(order);
      router.push({ pathname: '/payment/[orderId]', params: { orderId: order.id } });
    } catch (err) {
      // the backend lists the drinks and designer ingredients it no longer has stock for
      const soldOutIds: number[] = (err as ApiError).data?.drinks ?? [];
      const soldOutCodes: string[] = (err as ApiError).data?.options ?? [];
      const soldOut = cartItems
        .filter((item) => (item.custom
          ? item.custom.picks.some((code) => soldOutCodes.includes(code))
          : soldOutIds.includes(item.drink.id)))
        .map((item) => item.drink.name);
      setError(soldOut.length
        ? `Sorry, not enough stock for: ${[...new Set(soldOut)].join(', ')}`
        : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (cartItems.length === 0) {
    return (
      <View style={[styles.screen, styles.emptyScreen]}>
        <Text style={styles.emptyTitle}>Your order is empty</Text>
        <Text style={styles.muted}>Pick a drink from the menu to get started.</Text>
        <Pressable accessibilityRole="button" onPress={() => router.navigate('/')} style={styles.payButton}>
          <Text style={styles.payText}>Browse the menu</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <FlatList
        data={cartItems}
        keyExtractor={(_, index) => String(index)}
        contentContainerStyle={styles.list}
        ListHeaderComponent={shop ? <Text style={styles.pickup}>Pick up at {shop.name}</Text> : null}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        renderItem={({ item, index }) => (
          <View style={styles.item}>
            <DrinkArt drink={item.drink} size={64} rounded={12} />
            <View style={styles.itemMain}>
              <View style={styles.itemHeader}>
                <Text style={styles.itemName} numberOfLines={2}>{item.drink.name}</Text>
                <Text style={styles.itemPrice}>{formatPrice(itemPrice(item))}</Text>
              </View>
              {item.custom && <Text style={styles.customTag}>DESIGNED</Text>}
              <Text style={styles.itemDetail}>
                {item.size === SIZE.LARGE ? 'Large' : 'Regular'} · Sugar {levelLabel(item.sugar)} · Ice {levelLabel(item.ice)}
              </Text>
              <View style={styles.itemActions}>
                <Pressable accessibilityRole="button" accessibilityLabel={`Edit ${item.drink.name}`}
                  onPress={() => setEditing(index)} hitSlop={8}>
                  <Text style={styles.link}>Edit</Text>
                </Pressable>
                <Pressable accessibilityRole="button" accessibilityLabel={`Remove ${item.drink.name}`}
                  onPress={() => removeFromCart(index)} hitSlop={8}>
                  <Text style={styles.link}>Remove</Text>
                </Pressable>
              </View>
            </View>
          </View>
        )}
      />

      <ErrorBanner message={error} />

      <View style={styles.footer}>
        <View>
          <Text style={styles.footerLabel}>{cartItems.length} {cartItems.length === 1 ? 'drink' : 'drinks'}</Text>
          <Text style={styles.total}>{formatPrice(total)}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={checkout}
          disabled={blocked}
          style={[styles.payButton, blocked && { opacity: 0.5 }]}>
          <Text style={styles.payText}>{submitting ? 'Placing order…' : 'Place order'}</Text>
        </Pressable>
      </View>

      <DrinkSheet
        item={editing === null ? null : cartItems[editing] ?? null}
        confirmLabel="Save changes"
        onConfirm={(choice) => { if (editing !== null) updateCartItem(editing, choice); setEditing(null); }}
        onClose={() => setEditing(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  emptyScreen: { alignItems: 'center', justifyContent: 'center', gap: 10, padding: 24 },
  emptyTitle: { fontFamily: fonts.serif, fontSize: 26, color: colors.text },
  list: { paddingVertical: 8 },
  pickup: { fontFamily: fonts.sans, color: colors.muted, paddingHorizontal: 16, paddingBottom: 8 },
  separator: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginLeft: 94 },
  item: { flexDirection: 'row', gap: 14, paddingVertical: 14, paddingHorizontal: 16 },
  itemMain: { flex: 1, gap: 3 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  itemName: { fontFamily: fonts.serif, fontSize: 17, color: colors.text, flexShrink: 1 },
  itemPrice: { fontFamily: fonts.sansBold, fontSize: 15, color: colors.text },
  customTag: { fontFamily: fonts.sansBold, fontSize: 10, letterSpacing: 1, color: colors.primary },
  itemDetail: { fontFamily: fonts.sans, fontSize: 13, color: colors.muted },
  itemActions: { flexDirection: 'row', gap: 20, marginTop: 6 },
  link: { fontFamily: fonts.sansMedium, fontSize: 14, color: colors.primary },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  muted: { fontFamily: fonts.sans, color: colors.muted, textAlign: 'center' },
  footerLabel: { fontFamily: fonts.sans, color: colors.muted },
  total: { fontFamily: fonts.serif, fontSize: 26, color: colors.text },
  payButton: { backgroundColor: colors.primary, borderRadius: 26, minHeight: 52, justifyContent: 'center', paddingHorizontal: 28 },
  payText: { fontFamily: fonts.sansBold, color: colors.surface, fontSize: 16 },
});
