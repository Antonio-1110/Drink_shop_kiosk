import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import PickupCode from '@/components/PickupCode';
import { colors } from '@/constants/theme';
import { cancelOrder, fetchOrderStatus, fetchPaynowQr, isPaid, PaynowQr } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { formatPrice } from '@/lib/menu';

const POLL_MS = 4000;

export default function PaymentScreen() {
  const { orderId } = useLocalSearchParams<{ orderId: string }>();
  const { shop, clearCart, lastOrder } = useCart();
  const [qr, setQr] = useState<PaynowQr | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const order = lastOrder && String(lastOrder.id) === orderId ? lastOrder : { id: Number(orderId), revenue: '' };
  const paid = isPaid(status ?? undefined);
  const cancelled = status === 'CANCELLED';
  const collected = status === 'COLLECTED';

  // the order is placed, so the cart is done with
  useEffect(() => { clearCart(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // start the payment straight away: the backend cancels orders that don't start one quickly
  useEffect(() => {
    fetchPaynowQr(orderId).then(setQr).catch((err) => setError(err.message));
  }, [orderId]);

  // poll until the order is paid or cancelled; older backends without /status/ just leave it unknown
  useEffect(() => {
    if (collected || cancelled) return;
    let stopped = false;
    const check = () => fetchOrderStatus(orderId)
      .then((res) => { if (!stopped) setStatus(res.status); })
      .catch(() => {});
    check();
    const timer = setInterval(check, POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
  }, [orderId, collected, cancelled]);

  const cancel = async () => {
    if (!order.order_token) return;
    setCancelling(true);
    try {
      const res = await cancelOrder(orderId, order.order_token);
      setStatus(res.status);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.orderLabel}>Order number</Text>
      <Text style={styles.orderNumber}>{orderId}</Text>
      {shop && <Text style={styles.muted}>Collect at {shop.name}</Text>}

      {cancelled ? (
        <Text style={styles.cancelled}>This order was cancelled and you haven&apos;t been charged.</Text>
      ) : collected ? (
        <Text style={styles.collected}>Collected. Enjoy your drink!</Text>
      ) : (
        <>
          <View style={styles.step}>
            <View style={styles.stepHeader}>
              <Text style={styles.stepTitle}>1. Pay with PayNow</Text>
              {paid && <Text style={styles.paidBadge}>Paid</Text>}
            </View>
            <ErrorBanner message={error} />
            {!qr && !error && <ActivityIndicator style={{ marginVertical: 30 }} color={colors.primary} />}
            {qr && !paid && (
              <>
                <Image source={{ uri: qr.qr_code }} style={styles.qr} accessibilityLabel="PayNow QR code" />
                <Text style={styles.amount}>Amount: {formatPrice(qr.amount)}</Text>
                <Text style={styles.muted}>Reference: {qr.reference}</Text>
                {qr.expires_at && (
                  <Text style={styles.deadline}>
                    Pay by {new Date(qr.expires_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} or the order is cancelled.
                  </Text>
                )}
                <Text style={styles.hint}>
                  Take a screenshot of this code, then open your banking app, choose Scan & Pay and pick the screenshot from your gallery.
                </Text>
              </>
            )}
            {qr && paid && <Text style={styles.muted}>Payment of {formatPrice(qr.amount)} received. Thank you!</Text>}
          </View>

          <View style={styles.step}>
            <Text style={styles.stepTitle}>2. Collect at the machine</Text>
            {!paid && <Text style={styles.muted}>Your code works once the payment comes through.</Text>}
            <PickupCode order={order} />
          </View>

          {order.order_token && !paid && (
            <Pressable accessibilityRole="button" onPress={cancel} disabled={cancelling} style={styles.cancelButton}>
              <Text style={styles.cancelText}>{cancelling ? 'Cancelling...' : 'Cancel order'}</Text>
            </Pressable>
          )}
        </>
      )}

      <Pressable accessibilityRole="button" onPress={() => router.dismissTo('/')} style={styles.newOrder}>
        <Text style={styles.newOrderText}>Start a new order</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', padding: 16, gap: 6 },
  orderLabel: { color: colors.muted, marginTop: 6 },
  orderNumber: { fontSize: 40, fontWeight: 'bold', color: colors.primary },
  muted: { color: colors.muted, textAlign: 'center' },
  step: {
    alignSelf: 'stretch',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 16,
    marginTop: 14,
    gap: 6,
  },
  stepHeader: { alignSelf: 'stretch', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  stepTitle: { alignSelf: 'flex-start', fontSize: 17, fontWeight: 'bold', color: colors.text },
  paidBadge: { backgroundColor: colors.primary, color: colors.surface, fontWeight: 'bold', borderRadius: 10, paddingHorizontal: 10, paddingVertical: 3, overflow: 'hidden' },
  qr: { width: 220, height: 220, marginVertical: 8 },
  amount: { fontSize: 20, fontWeight: 'bold', color: colors.accent },
  deadline: { color: colors.errorText, fontWeight: '600', textAlign: 'center' },
  hint: { textAlign: 'center', color: colors.text, backgroundColor: colors.primarySoft, borderRadius: 8, padding: 12, marginTop: 8 },
  cancelled: { textAlign: 'center', color: colors.errorText, backgroundColor: colors.errorBg, borderRadius: 8, padding: 14, marginTop: 14, alignSelf: 'stretch' },
  collected: { textAlign: 'center', color: colors.primary, fontWeight: 'bold', fontSize: 18, backgroundColor: colors.primarySoft, borderRadius: 8, padding: 16, marginTop: 14, alignSelf: 'stretch' },
  cancelButton: { marginTop: 14, paddingVertical: 10, paddingHorizontal: 18 },
  cancelText: { color: colors.errorText, fontWeight: '600', textDecorationLine: 'underline' },
  newOrder: { backgroundColor: colors.secondary, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 22, marginTop: 20 },
  newOrderText: { color: colors.text, fontWeight: 'bold' },
});
