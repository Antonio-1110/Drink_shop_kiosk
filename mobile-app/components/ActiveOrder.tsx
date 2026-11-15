import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '@/constants/theme';
import { fetchOrderStatus, isPaid } from '@/lib/api';
import { SavedOrder, useCart } from '@/lib/cart';
import { useT } from '@/lib/i18n';

const POLL_MS = 15000;
// an order older than this isn't worth a banner any more
const SHOW_MS = 12 * 60 * 60 * 1000;
const DONE = ['COLLECTED', 'CANCELLED'];

// The customer's latest order that isn't collected yet, at the top of the menu, so the pickup code
// is one tap away even after the app was closed.
export default function ActiveOrder() {
  const { orders } = useCart();
  // checked when the menu opens, which is often enough for a 12-hour cut-off
  const [since] = useState(() => Date.now() - SHOW_MS);
  const order = orders.find((o) => !o.finished && o.placedAt > since);
  return order ? <Banner key={order.id} order={order} /> : null;
}

function Banner({ order }: { order: SavedOrder }) {
  const { finishOrder } = useCart();
  const t = useT();
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    const check = () => fetchOrderStatus(order.id, order.order_token)
      .then((res) => {
        if (stopped) return;
        if (DONE.includes(res.status)) finishOrder(order.id);
        else setStatus(res.status);
      })
      .catch(() => {});
    check();
    const timer = setInterval(check, POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
  }, [order.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const label = status === 'PREPARING' || status === 'READY'
    ? t(`status.${status}`)
    : t(isPaid(status ?? undefined) ? 'status.paid' : 'status.unpaid');
  const ready = status === 'READY';

  return (
    <Pressable accessibilityRole="button"
      onPress={() => router.push({ pathname: '/payment/[orderId]', params: { orderId: order.id } })}
      style={({ pressed }) => [styles.banner, ready && styles.ready, pressed && { opacity: 0.85 }]}>
      <View style={[styles.dot, ready && styles.dotReady]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>{status ? t('menu.activeOrder', { id: order.id, status: label }) : t('menu.order', { id: order.id })}</Text>
        <Text style={styles.hint}>{t('menu.activeHint')}</Text>
      </View>
      <Text style={styles.arrow}>›</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginHorizontal: 16,
    marginTop: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 16,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  ready: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.accent },
  dotReady: { backgroundColor: colors.primary },
  title: { fontFamily: fonts.sansBold, fontSize: 15, color: colors.text },
  hint: { fontFamily: fonts.sans, fontSize: 13, color: colors.muted, marginTop: 1 },
  arrow: { fontSize: 26, color: colors.muted },
});
