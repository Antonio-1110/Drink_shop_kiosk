import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import { colors } from '@/constants/theme';
import { fetchPaynowQr, PaynowQr } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { formatPrice } from '@/lib/menu';

export default function PaymentScreen() {
  const { orderId } = useLocalSearchParams<{ orderId: string }>();
  const { shop, clearCart } = useCart();
  const [qr, setQr] = useState<PaynowQr | null>(null);
  const [error, setError] = useState<string | null>(null);

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

      <ErrorBanner message={error} />
      {!qr && !error && <ActivityIndicator style={{ marginTop: 30 }} color={colors.navy} />}
      {qr && (
        <>
          <Image source={{ uri: qr.qr_code }} style={styles.qr} accessibilityLabel="PayNow QR code" />
          <Text style={styles.amount}>Amount: {formatPrice(qr.amount)}</Text>
          <Text style={styles.muted}>Reference: {qr.reference}</Text>
          <Text style={styles.hint}>
            Take a screenshot of this code, then open your banking app, choose Scan & Pay and pick the screenshot from your gallery.
          </Text>
        </>
      )}

      <Pressable accessibilityRole="button" onPress={() => router.dismissTo('/')} style={styles.newOrder}>
        <Text style={styles.newOrderText}>Start a new order</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', padding: 20, gap: 6 },
  orderLabel: { color: colors.muted, marginTop: 10 },
  orderNumber: { fontSize: 40, fontWeight: 'bold', color: colors.navy },
  muted: { color: colors.muted },
  qr: { width: 260, height: 260, marginVertical: 16 },
  amount: { fontSize: 20, fontWeight: 'bold', color: colors.text },
  hint: { textAlign: 'center', color: colors.text, backgroundColor: colors.lightBlue, borderRadius: 8, padding: 12, marginTop: 12 },
  newOrder: { backgroundColor: colors.greyDark, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 22, marginTop: 20 },
  newOrderText: { color: colors.text, fontWeight: 'bold' },
});
