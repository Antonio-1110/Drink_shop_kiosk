import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import PickupCode from '@/components/PickupCode';
import { colors, fonts } from '@/constants/theme';
import { ApiError, cancelOrder, DRINK_PROGRESS, fetchOrderStatus, fetchPaynowQr, isPaid, PaynowQr, PlacedOrder } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { useT } from '@/lib/i18n';
import { formatPrice } from '@/lib/menu';

const POLL_MS = 4000;

export default function PaymentScreen() {
  const { orderId } = useLocalSearchParams<{ orderId: string }>();
  const { shop, clearCart, orders, finishOrder } = useCart();
  const t = useT();
  const [qrTry, setQrTry] = useState(0);
  const [qr, setQr] = useState<PaynowQr | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  // the saved order has the pickup codes and the token to cancel, even after the app was closed
  const saved = orders.find((o) => String(o.id) === orderId);
  const order: PlacedOrder = saved ?? { id: Number(orderId), revenue: '' };
  const paid = isPaid(status ?? undefined);
  const cancelled = status === 'CANCELLED';
  const collected = status === 'COLLECTED';
  const progress = status ? DRINK_PROGRESS[status] : undefined;

  // the order is placed, so the cart is done with (only on the visit right after placing it, not
  // when an earlier order is opened from the menu)
  useEffect(() => {
    if (saved && Date.now() - saved.placedAt < 60000) clearCart();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // start the payment straight away: the backend cancels orders that don't start one quickly.
  // It reuses an open payment, so trying again never makes a second one.
  useEffect(() => {
    if (paid || cancelled || collected) return;
    fetchPaynowQr(orderId, order.order_token)
      .then((res) => { setQr(res); setError(null); })
      .catch((err: ApiError) => setError(err.data?.offline ? t('cart.offline') : t('pay.qrError')));
  }, [orderId, qrTry]); // eslint-disable-line react-hooks/exhaustive-deps

  // the menu stops showing an order once it's collected or cancelled
  useEffect(() => {
    if (collected || cancelled) finishOrder(Number(orderId));
  }, [collected, cancelled]); // eslint-disable-line react-hooks/exhaustive-deps

  // poll until the order is paid or cancelled; older backends without /status/ just leave it unknown
  useEffect(() => {
    if (collected || cancelled) return;
    let stopped = false;
    const check = () => fetchOrderStatus(orderId, order.order_token)
      .then((res) => { if (!stopped) setStatus(res.status); })
      .catch(() => {});
    check();
    const timer = setInterval(check, POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
  }, [orderId, collected, cancelled, order.order_token]);

  const cancel = async () => {
    if (!order.order_token) return;
    setCancelling(true);
    try {
      const res = await cancelOrder(orderId, order.order_token);
      setStatus(res.status);
    } catch (err) {
      setError((err as ApiError).data?.offline ? t('cart.offline') : (err as Error).message);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.orderLabel}>{t('pay.orderNumber')}</Text>
      <Text style={styles.orderNumber}>{orderId}</Text>
      {(saved?.shopName ?? shop?.name) && <Text style={styles.muted}>{t('pay.collectAt', { shop: saved?.shopName ?? shop?.name ?? '' })}</Text>}

      {cancelled ? (
        <Text style={styles.cancelled}>{t('pay.cancelled')}</Text>
      ) : collected ? (
        <Text style={styles.collected}>{t('pay.collected')}</Text>
      ) : (
        <>
          <View style={styles.step}>
            <View style={styles.stepHeader}>
              <Text style={styles.stepTitle}>{t('pay.step1')}</Text>
              {paid && <Text style={styles.paidBadge}>{t('pay.paid')}</Text>}
            </View>
            {/* sandbox or a gateway's test keys: say so, so nobody thinks this is a real charge */}
            {qr?.test_mode && <Text style={styles.testMode}>{t('pay.testMode')}</Text>}
            <ErrorBanner message={error} onRetry={qr ? undefined : () => { setError(null); setQrTry((n) => n + 1); }} />
            {!qr && !error && <ActivityIndicator style={{ marginVertical: 30 }} color={colors.primary} />}
            {qr && !paid && (
              <>
                <Image source={{ uri: qr.qr_code }} style={styles.qr} accessibilityLabel={t('pay.qrAlt')} />
                <Text style={styles.amount}>{formatPrice(qr.amount)}</Text>
                <Text style={styles.muted}>{t('pay.ref', { ref: qr.reference })}</Text>
                {qr.expires_at && (
                  <Text style={styles.deadline}>
                    {t('pay.payBy', { time: new Date(qr.expires_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) })}
                  </Text>
                )}
                <Text style={styles.hint}>{t('pay.hint')}</Text>
              </>
            )}
            {qr && paid && <Text style={styles.muted}>{t('pay.received', { amount: formatPrice(qr.amount) })}</Text>}
          </View>

          <View style={styles.step}>
            <Text style={styles.stepTitle}>{t('pay.step2')}</Text>
            {!paid && <Text style={styles.muted}>{t('pay.codeLater')}</Text>}
            {progress && (
              <Text style={[styles.progress, progress.tone === 'warn' && styles.progressWarn]}>{t(`progress.${status}`)}</Text>
            )}
            <PickupCode order={order} />
          </View>

          {order.order_token && !paid && (
            <Pressable accessibilityRole="button" onPress={cancel} disabled={cancelling} style={styles.cancelButton}>
              <Text style={styles.cancelText}>{cancelling ? t('pay.cancelling') : t('pay.cancel')}</Text>
            </Pressable>
          )}
        </>
      )}

      <Pressable accessibilityRole="button" onPress={() => router.dismissTo('/')} style={styles.newOrder}>
        <Text style={styles.newOrderText}>{t('pay.newOrder')}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', padding: 16, paddingBottom: 32, gap: 6 },
  orderLabel: { fontFamily: fonts.sansBold, fontSize: 11, letterSpacing: 1.2, textTransform: 'uppercase', color: colors.muted, marginTop: 6 },
  orderNumber: { fontFamily: fonts.serif, fontSize: 52, color: colors.primary },
  muted: { fontFamily: fonts.sans, color: colors.muted, textAlign: 'center' },
  step: {
    alignSelf: 'stretch',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 20,
    marginTop: 14,
    gap: 6,
  },
  stepHeader: { alignSelf: 'stretch', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  stepTitle: { alignSelf: 'flex-start', fontFamily: fonts.serif, fontSize: 20, color: colors.text },
  paidBadge: { backgroundColor: colors.primary, color: colors.surface, fontFamily: fonts.sansBold, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 3, overflow: 'hidden' },
  qr: { width: 220, height: 220, marginVertical: 8 },
  amount: { fontFamily: fonts.serif, fontSize: 30, color: colors.text },
  deadline: { fontFamily: fonts.sansMedium, color: colors.text, textAlign: 'center', backgroundColor: colors.header, borderRadius: 14, paddingVertical: 4, paddingHorizontal: 12, overflow: 'hidden' },
  hint: { fontFamily: fonts.sans, textAlign: 'center', color: colors.muted, lineHeight: 20, marginTop: 8 },
  cancelled: { fontFamily: fonts.sans, textAlign: 'center', color: colors.errorText, backgroundColor: colors.errorBg, borderRadius: 16, padding: 16, marginTop: 14, alignSelf: 'stretch' },
  collected: { textAlign: 'center', color: colors.primary, fontFamily: fonts.serif, fontSize: 20, backgroundColor: colors.primarySoft, borderRadius: 16, padding: 16, marginTop: 14, alignSelf: 'stretch' },
  cancelButton: { marginTop: 14, paddingVertical: 10, paddingHorizontal: 18 },
  progress: { fontFamily: fonts.sansMedium, color: colors.primary, backgroundColor: colors.primarySoft, borderRadius: 14, paddingVertical: 8, paddingHorizontal: 14, overflow: 'hidden', textAlign: 'center' },
  progressWarn: { color: colors.errorText, backgroundColor: colors.errorBg },
  testMode: {
    fontFamily: fonts.sansBold, color: colors.accent, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.accent,
    borderRadius: 14, paddingVertical: 4, paddingHorizontal: 12, overflow: 'hidden', textAlign: 'center',
  },
  cancelText: { fontFamily: fonts.sansMedium, color: colors.muted, textDecorationLine: 'underline' },
  newOrder: { borderWidth: 1, borderColor: colors.border, borderRadius: 26, minHeight: 52, justifyContent: 'center', paddingHorizontal: 28, marginTop: 20 },
  newOrderText: { fontFamily: fonts.sansBold, color: colors.text },
});
