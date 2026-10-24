import { Link, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import DrinkCard from '@/components/DrinkCard';
import DrinkSheet from '@/components/DrinkSheet';
import ErrorBanner from '@/components/ErrorBanner';
import OrderBar from '@/components/OrderBar';
import ShopList from '@/components/ShopList';
import { colors, fonts } from '@/constants/theme';
import { fetchAvailableDrinks } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { CATEGORIES, Drink, SIZE } from '@/lib/menu';

export default function MenuScreen() {
  const insets = useSafeAreaInsets();
  const { shop, cartItems, addToCart } = useCart();
  const [drinks, setDrinks] = useState<Drink[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Drink | null>(null);

  // reload the menu whenever the cart changes, so drinks that ran out disappear
  useEffect(() => {
    if (!shop) return;
    let cancelled = false;
    fetchAvailableDrinks(shop.id, cartItems)
      .then((data) => { if (!cancelled) { setDrinks(data); setLoadError(null); } })
      .catch((err) => { if (!cancelled) setLoadError(err.message); });
    return () => { cancelled = true; };
  }, [shop, cartItems]);

  if (!shop) return <View style={[styles.screen, { paddingTop: insets.top }]}><ShopList /></View>;

  const shown = category ? drinks.filter((d) => d.category === category) : drinks;

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      {/* a slim header: where you're collecting, which is what changes the menu */}
      <View style={styles.header}>
        <View style={{ flexShrink: 1 }}>
          <Text style={styles.eyebrow}>Pick up at</Text>
          <Text style={styles.shopName} numberOfLines={1}>{shop.name}</Text>
        </View>
        <Link href="/shops" style={styles.change}>Change</Link>
      </View>

      <View style={styles.categoryBar}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categories}>
          {[null, ...CATEGORIES].map((c) => {
            const active = c === category;
            return (
              <Pressable
                key={c ?? 'all'}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                onPress={() => setCategory(c)}
                style={[styles.category, active && styles.categoryActive]}>
                <Text style={[styles.categoryText, active && styles.categoryTextActive]}>{c ?? 'All'}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      <ErrorBanner message={loadError && `Could not load the menu: ${loadError}`} />

      <FlatList
        data={shown}
        keyExtractor={(drink) => String(drink.id)}
        contentContainerStyle={{ paddingBottom: cartItems.length ? 96 : 24 }}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        ListHeaderComponent={
          <Pressable accessibilityRole="button" onPress={() => router.push('/designer')}
            style={({ pressed }) => [styles.designer, pressed && { opacity: 0.85 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.designerTitle}>Design your own</Text>
              <Text style={styles.designerText}>Choose your tea, milk and toppings</Text>
            </View>
            <Text style={styles.designerArrow}>›</Text>
          </Pressable>
        }
        ListEmptyComponent={<Text style={styles.empty}>Nothing here right now. Try another section.</Text>}
        renderItem={({ item }) => <DrinkCard drink={item} onSelect={setSelected} />}
      />

      <OrderBar />

      <DrinkSheet
        item={selected && { drink: selected, size: SIZE.SMALL, sugar: 4, ice: 4 }}
        confirmLabel="Add to order"
        onConfirm={(choice) => { if (selected) addToCart(selected, choice); setSelected(null); }}
        onClose={() => setSelected(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    gap: 12,
  },
  eyebrow: { fontFamily: fonts.sansBold, fontSize: 11, letterSpacing: 1.1, textTransform: 'uppercase', color: colors.muted },
  shopName: { fontFamily: fonts.serif, fontSize: 22, color: colors.text },
  change: {
    fontFamily: fonts.sansBold,
    fontSize: 14,
    color: colors.primary,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  categoryBar: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  categories: { paddingHorizontal: 16, gap: 22 },
  category: { paddingVertical: 12, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  categoryActive: { borderBottomColor: colors.primary },
  categoryText: { fontFamily: fonts.sansMedium, fontSize: 15, color: colors.muted },
  categoryTextActive: { fontFamily: fonts.sansBold, color: colors.text },
  separator: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginLeft: 118 },
  designer: {
    flexDirection: 'row',
    alignItems: 'center',
    margin: 16,
    marginBottom: 6,
    paddingVertical: 14,
    paddingHorizontal: 18,
    borderRadius: 16,
    backgroundColor: colors.primary,
  },
  designerTitle: { fontFamily: fonts.serif, fontSize: 18, color: colors.surface },
  designerText: { fontFamily: fonts.sans, fontSize: 13, color: 'rgba(255,255,255,0.75)', marginTop: 2 },
  designerArrow: { fontSize: 28, color: colors.surface, marginLeft: 8 },
  empty: { textAlign: 'center', fontFamily: fonts.sans, color: colors.muted, marginTop: 40 },
});
