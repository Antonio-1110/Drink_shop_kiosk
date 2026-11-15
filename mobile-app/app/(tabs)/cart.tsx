import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import DrinkArt from '@/components/DrinkArt';
import DrinkSheet from '@/components/DrinkSheet';
import ErrorBanner from '@/components/ErrorBanner';
import { colors, fonts } from '@/constants/theme';
import { ApiError, placeOrder } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { Translate, useT } from '@/lib/i18n';
import { CartItem, cartCount, cartTotal, formatPrice, lineQty, lineTotal, LEVELS, MAX_ORDER_DRINKS, SIZE } from '@/lib/menu';

const levelLabel = (value: number) => LEVELS.find((level) => level.value === value)?.label;
// why the shop can't take orders (the backend's 503 `reason`); nothing is placed or charged
const SHOP_CLOSED = ['machine_offline', 'maintenance', 'machine_not_ready'];

// what the customer should see when the backend turns the order down
function orderErrorMessage(err: ApiError, cartItems: CartItem[], t: Translate) {
  if (err.data?.offline) return t('cart.offline');
  if (err.status === 503 && SHOP_CLOSED.includes(err.data?.reason)) return t(`closed.${err.data.reason}`);
  if (err.status === 429) return t('cart.busy');
  // more drinks than the backend allows (its limit may differ from ours)
  if (err.status === 400 && err.data?.items) return t('cart.tooMany', { max: MAX_ORDER_DRINKS });
  // the backend lists the drinks and designer ingredients it no longer has stock for
  const soldOutIds: number[] = err.data?.drinks ?? [];
  const soldOutCodes: string[] = err.data?.options ?? [];
  const soldOut = cartItems
    .filter((item) => (item.custom
      ? item.custom.picks.some((code) => soldOutCodes.includes(code))
      : soldOutIds.includes(item.drink.id)))
    .map((item) => item.drink.name);
  return soldOut.length ? t('cart.soldOut', { names: [...new Set(soldOut)].join(', ') }) : err.message;
}

// − 2 + : one less (a bin at 1, which removes the line) or one more of the same cup
function Quantity({ item, onChange }: { item: CartItem; onChange: (qty: number) => void }) {
  const t = useT();
  const qty = lineQty(item);
  const name = item.drink.name;
  return (
    <View style={styles.qty}>
      <Pressable accessibilityRole="button" accessibilityLabel={t(qty === 1 ? 'cart.remove' : 'cart.less', { name })}
        onPress={() => onChange(qty - 1)} style={styles.qtyButton} hitSlop={4}>
        <Text style={styles.qtySign}>{qty === 1 ? '×' : '−'}</Text>
      </Pressable>
      <Text style={styles.qtyValue} accessibilityLiveRegion="polite">{qty}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel={t('cart.more', { name })}
        onPress={() => onChange(qty + 1)} style={styles.qtyButton} hitSlop={4}>
        <Text style={styles.qtySign}>+</Text>
      </Pressable>
    </View>
  );
}

export default function CartScreen() {
  const { shop, cartItems, updateCartItem, removeFromCart, saveOrder } = useCart();
  const t = useT();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState<number | null>(null); // the line whose options are open
  const total = cartTotal(cartItems);
  const count = cartCount(cartItems);
  const tooMany = count > MAX_ORDER_DRINKS;
  const tooManyText = t('cart.tooMany', { max: MAX_ORDER_DRINKS });
  const blocked = cartItems.length === 0 || submitting || tooMany;

  const checkout = async () => {
    if (!shop) return;
    setSubmitting(true);
    setError(null);
    try {
      const order = await placeOrder(shop.id, cartItems);
      saveOrder(order, count);
      router.push({ pathname: '/payment/[orderId]', params: { orderId: order.id } });
    } catch (err) {
      setError(orderErrorMessage(err as ApiError, cartItems, t));
    } finally {
      setSubmitting(false);
    }
  };

  if (cartItems.length === 0) {
    return (
      <View style={[styles.screen, styles.emptyScreen]}>
        <Text style={styles.emptyTitle}>{t('cart.emptyTitle')}</Text>
        <Text style={styles.muted}>{t('cart.emptyText')}</Text>
        <Pressable accessibilityRole="button" onPress={() => router.navigate('/')} style={styles.payButton}>
          <Text style={styles.payText}>{t('cart.browse')}</Text>
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
        ListHeaderComponent={shop ? <Text style={styles.pickup}>{t('cart.pickUpAt', { shop: shop.name })}</Text> : null}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        renderItem={({ item, index }) => (
          <View style={styles.item}>
            <DrinkArt drink={item.drink} size={64} rounded={12} />
            <View style={styles.itemMain}>
              <View style={styles.itemHeader}>
                <Text style={styles.itemName} numberOfLines={2}>{item.drink.name}</Text>
                <Text style={styles.itemPrice}>{formatPrice(lineTotal(item))}</Text>
              </View>
              {item.custom && <Text style={styles.customTag}>{t('cart.designed')}</Text>}
              <Text style={styles.itemDetail}>
                {t('cart.detail', {
                  size: t(item.size === SIZE.LARGE ? 'drink.large' : 'drink.regular'),
                  sugar: levelLabel(item.sugar) ?? '',
                  ice: levelLabel(item.ice) ?? '',
                })}
              </Text>
              <View style={styles.itemActions}>
                <Pressable accessibilityRole="button" accessibilityLabel={t('cart.editLabel', { name: item.drink.name })}
                  onPress={() => setEditing(index)} style={styles.editButton}>
                  <Text style={styles.link}>{t('cart.edit')}</Text>
                </Pressable>
                <Quantity item={item} onChange={(qty) => {
                  setError(null);
                  if (qty < 1) removeFromCart(index);
                  else updateCartItem(index, { qty });
                }} />
              </View>
            </View>
          </View>
        )}
      />

      <ErrorBanner message={error ?? (tooMany ? tooManyText : null)} />

      <View style={styles.footer}>
        <View>
          <Text style={styles.footerLabel}>{t('cart.drinks', { count })}</Text>
          <Text style={styles.total}>{formatPrice(total)}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={checkout}
          disabled={blocked}
          style={[styles.payButton, blocked && { opacity: 0.5 }]}>
          <Text style={styles.payText}>{submitting ? t('cart.placing') : t('cart.place')}</Text>
        </Pressable>
      </View>

      <DrinkSheet
        item={editing === null ? null : cartItems[editing] ?? null}
        confirmLabel={t('drink.save')}
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
  itemActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  editButton: { minHeight: 44, minWidth: 64, justifyContent: 'center', paddingHorizontal: 16, borderRadius: 22, borderWidth: 1, borderColor: colors.border },
  qty: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: 22 },
  qtyButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  qtySign: { fontSize: 22, lineHeight: 26, color: colors.primary, fontFamily: fonts.sans },
  qtyValue: { minWidth: 22, textAlign: 'center', fontFamily: fonts.sansBold, fontSize: 16, color: colors.text },
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
