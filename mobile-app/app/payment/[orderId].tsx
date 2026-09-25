import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import PickupCode from '@/components/PickupCode';
import { colors } from '@/constants/theme';
import { fetchPaynowQr, PaynowQr } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { formatPrice } from '@/lib/menu';

export default function PaymentScreen() {
  const { orderId } = useLocalSearchParams<{ orderId: string }>();
  const { shop, clearCart, lastOrder } = useCart();
  const [qr, setQr] = useState<PaynowQr | null>(null);
  const [error, setError] = useState<string | null>(null);
  const order = lastOrder && String(lastOrder.id) === orderId ? lastOrder : { id: Number(orderId), revenue: '' };

  // the order is placed, so the cart is done with
  useEffect(() => { clearCart(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchPaynowQr(orderId).then(setQr).catch((err) => setError(err.message));
  }, [orderId]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.orderLabel}>Order number</Text>
      <Text style={styles.orderNumber}>{orderId}</Text>
      {shop && <Text style={styles.muted}>Collect at {shop.name}</Text>}

      <View style={styles.step}>
        <Text style={styles.stepTitle}>1. Pay with PayNow</Text>
        <ErrorBanner message={error} />
        {!qr && !error && <ActivityIndicator style={{ marginVertical: 30 }} color={colors.primary} />}
        {qr && (
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
      </View>

      <View style={styles.step}>
        <Text style={styles.stepTitle}>2. Collect at the machine</Text>
        <PickupCode order={order} />
      </View>

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
  muted: { color: colors.muted },
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
  stepTitle: { alignSelf: 'flex-start', fontSize: 17, fontWeight: 'bold', color: colors.text, marginBottom: 4 },
  qr: { width: 220, height: 220, marginVertical: 8 },
  amount: { fontSize: 20, fontWeight: 'bold', color: colors.accent },
  deadline: { color: colors.errorText, fontWeight: '600', textAlign: 'center' },
  hint: { textAlign: 'center', color: colors.text, backgroundColor: colors.primarySoft, borderRadius: 8, padding: 12, marginTop: 8 },
  newOrder: { backgroundColor: colors.secondary, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 22, marginTop: 20 },
  newOrderText: { color: colors.text, fontWeight: 'bold' },
});
