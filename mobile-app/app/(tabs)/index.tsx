import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import DrinkCard from '@/components/DrinkCard';
import ErrorBanner from '@/components/ErrorBanner';
import ShopList from '@/components/ShopList';
import { colors } from '@/constants/theme';
import { fetchAvailableDrinks } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { CATEGORIES, Drink } from '@/lib/menu';

export default function MenuScreen() {
  const { shop, cartItems, addToCart } = useCart();
  const [drinks, setDrinks] = useState<Drink[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // reload the menu whenever the cart changes, so drinks that ran out disappear
  useEffect(() => {
    if (!shop) return;
    let cancelled = false;
    fetchAvailableDrinks(shop.id, cartItems)
      .then((data) => { if (!cancelled) { setDrinks(data); setLoadError(null); } })
      .catch((err) => { if (!cancelled) setLoadError(err.message); });
    return () => { cancelled = true; };
  }, [shop, cartItems]);

  if (!shop) return <ShopList />;

  const shown = category ? drinks.filter((d) => d.category === category) : drinks;

  return (
    <View style={styles.screen}>
      <View style={styles.shopBar}>
        <Text style={styles.shopText} numberOfLines={1}>Pick up at <Text style={styles.bold}>{shop.name}</Text></Text>
        <Link href="/shops" style={styles.change}>Change</Link>
      </View>

      <View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categories}>
          {[null, ...CATEGORIES].map((c) => (
            <Pressable
              key={c ?? 'all'}
              accessibilityRole="button"
              accessibilityState={{ selected: c === category }}
              onPress={() => setCategory(c)}
              style={[styles.category, c === category && styles.categorySelected]}>
              <Text style={[styles.categoryText, c === category && styles.categoryTextSelected]}>{c ?? 'All Drinks'}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      <ErrorBanner message={loadError && `Could not load the menu: ${loadError}`} />

      <FlatList
        data={shown}
        keyExtractor={(drink) => String(drink.id)}
        numColumns={2}
        contentContainerStyle={styles.grid}
        ListEmptyComponent={<Text style={styles.empty}>No drinks available right now.</Text>}
        renderItem={({ item, index }) => (
          <>
            <DrinkCard drink={item} onAdd={addToCart} />
            {/* keep the last card half width when the count is odd */}
            {index === shown.length - 1 && shown.length % 2 === 1 && <View style={{ flex: 1, margin: 6 }} />}
          </>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  shopBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: colors.lightBlue,
    gap: 12,
  },
  shopText: { color: colors.text, flexShrink: 1 },
  bold: { fontWeight: 'bold', color: colors.navy },
  change: { color: colors.navy, fontWeight: 'bold', textDecorationLine: 'underline' },
  categories: { paddingHorizontal: 10, paddingVertical: 10, gap: 8 },
  category: { paddingVertical: 8, paddingHorizontal: 14, borderRadius: 18, backgroundColor: colors.lightBlue },
  categorySelected: { backgroundColor: colors.navy },
  categoryText: { color: colors.navy },
  categoryTextSelected: { color: colors.surface, fontWeight: 'bold' },
  grid: { paddingHorizontal: 6, paddingBottom: 20 },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 40 },
});
