import { useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import { colors } from '@/constants/theme';
import { fetchShops } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { Shop } from '@/lib/menu';

// Lets the customer pick which shop or kiosk they'll collect from; the menu depends on its stock.
export default function ShopList({ onChosen }: { onChosen?: (shop: Shop) => void }) {
  const { shop: current, chooseShop } = useCart();
  const [shops, setShops] = useState<Shop[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchShops().then(setShops).catch((err) => setError(err.message));
  }, []);

  if (error) return <ErrorBanner message={`Could not load shops: ${error}`} />;
  if (!shops) return <ActivityIndicator style={{ marginTop: 40 }} color={colors.primary} />;

  return (
    <FlatList
      data={shops}
      keyExtractor={(shop) => String(shop.id)}
      contentContainerStyle={{ padding: 12, gap: 10 }}
      ListHeaderComponent={<Text style={styles.heading}>Where will you pick up?</Text>}
      ListEmptyComponent={<Text style={styles.muted}>No shops are open right now.</Text>}
      renderItem={({ item }) => (
        <Pressable
          accessibilityRole="button"
          onPress={() => { chooseShop(item); onChosen?.(item); }}
          style={({ pressed }) => [styles.shop, item.id === current?.id && styles.current, pressed && { opacity: 0.7 }]}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.muted}>{item.address}</Text>
          <View style={styles.tag}><Text style={styles.tagText}>{item.shop_type}</Text></View>
        </Pressable>
      )}
    />
  );
}

const styles = StyleSheet.create({
  heading: { fontSize: 22, fontWeight: 'bold', color: colors.primary, marginBottom: 4 },
  shop: { backgroundColor: colors.surface, borderRadius: 10, padding: 14, gap: 4, borderWidth: 2, borderColor: 'transparent' },
  current: { borderColor: colors.primary },
  name: { fontSize: 17, fontWeight: '600', color: colors.text },
  muted: { color: colors.muted },
  tag: { alignSelf: 'flex-start', backgroundColor: colors.primarySoft, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 2, marginTop: 4 },
  tagText: { color: colors.primary, fontSize: 12 },
});
