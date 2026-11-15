import { Link, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import ActiveOrder from '@/components/ActiveOrder';
import DrinkCard from '@/components/DrinkCard';
import DrinkSheet from '@/components/DrinkSheet';
import ErrorBanner from '@/components/ErrorBanner';
import OrderBar from '@/components/OrderBar';
import ShopList from '@/components/ShopList';
import { colors, fonts } from '@/constants/theme';
import { fetchAvailableDrinks } from '@/lib/api';
import { useCart } from '@/lib/cart';
import { LANGUAGES, useLanguage, useT } from '@/lib/i18n';
import { CATEGORIES, Drink, SIZE } from '@/lib/menu';

// English / 中文, each in its own language
function LanguageSwitch() {
  const { lang, setLang } = useLanguage();
  const t = useT();
  return (
    <View style={styles.lang} accessibilityRole="radiogroup" accessibilityLabel={t('menu.language')}>
      {LANGUAGES.map(({ code, label }) => (
        <Pressable key={code} accessibilityRole="radio" accessibilityState={{ checked: lang === code }}
          onPress={() => setLang(code)} style={[styles.langButton, lang === code && styles.langSelected]}>
          <Text style={[styles.langText, lang === code && styles.langTextSelected]}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export default function MenuScreen() {
  const insets = useSafeAreaInsets();
  const { ready, shop, cartItems, addToCart } = useCart();
  const t = useT();
  const [drinks, setDrinks] = useState<Drink[] | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [category, setCategory] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<Drink | null>(null);

  // reload the menu whenever the cart changes, so drinks that ran out disappear
  useEffect(() => {
    if (!shop) return;
    let cancelled = false;
    fetchAvailableDrinks(shop.id, cartItems)
      .then((data) => { if (!cancelled) { setDrinks(data); setLoadError(false); } })
      .catch(() => { if (!cancelled) setLoadError(true); });
    return () => { cancelled = true; };
  }, [shop, cartItems, attempt]);

  // wait for the saved shop and cart before deciding to ask for a shop
  if (!ready) return <View style={styles.screen}><ActivityIndicator style={{ marginTop: 80 }} color={colors.primary} /></View>;
  if (!shop) return <View style={[styles.screen, { paddingTop: insets.top }]}><ShopList /></View>;

  const shown = drinks ? (category ? drinks.filter((d) => d.category === category) : drinks) : [];

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      {/* a slim header: where you're collecting, which is what changes the menu */}
      <View style={styles.header}>
        <View style={{ flexShrink: 1 }}>
          <Text style={styles.eyebrow}>{t('menu.pickUpAt')}</Text>
          <Text style={styles.shopName} numberOfLines={1}>{shop.name}</Text>
        </View>
        <Link href="/shops" style={styles.change}>{t('menu.change')}</Link>
      </View>
      <View style={styles.subHeader}>
        <LanguageSwitch />
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
                <Text style={[styles.categoryText, active && styles.categoryTextActive]}>{c ? t(`cat.${c}`) : t('menu.all')}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      <ErrorBanner message={loadError ? t('menu.offline') : null} onRetry={() => setAttempt((n) => n + 1)} />

      <FlatList
        data={shown}
        keyExtractor={(drink) => String(drink.id)}
        contentContainerStyle={{ paddingBottom: cartItems.length ? 96 : 24 }}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        ListHeaderComponent={<>
          <ActiveOrder />
          <Pressable accessibilityRole="button" onPress={() => router.push('/designer')}
            style={({ pressed }) => [styles.designer, pressed && { opacity: 0.85 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.designerTitle}>{t('menu.design')}</Text>
              <Text style={styles.designerText}>{t('menu.designHint')}</Text>
            </View>
            <Text style={styles.designerArrow}>›</Text>
          </Pressable>
        </>}
        ListEmptyComponent={drinks === null
          ? (loadError ? null : <ActivityIndicator style={{ marginTop: 40 }} color={colors.primary} accessibilityLabel={t('menu.loading')} />)
          : <Text style={styles.empty}>{t('menu.empty')}</Text>}
        renderItem={({ item }) => <DrinkCard drink={item} onSelect={setSelected} />}
      />

      <OrderBar />

      <DrinkSheet
        item={selected && { drink: selected, size: SIZE.SMALL, sugar: 4, ice: 4 }}
        confirmLabel={t('drink.add')}
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
  subHeader: { flexDirection: 'row', paddingHorizontal: 16, paddingBottom: 8 },
  lang: { flexDirection: 'row', backgroundColor: colors.header, borderRadius: 20, padding: 3 },
  langButton: { minHeight: 36, minWidth: 64, paddingHorizontal: 12, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  langSelected: { backgroundColor: colors.surface, boxShadow: '0 1px 3px rgba(43,35,32,0.12)' },
  langText: { fontFamily: fonts.sansMedium, fontSize: 14, color: colors.muted },
  langTextSelected: { fontFamily: fonts.sansBold, color: colors.primary },
  categoryBar: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  categories: { paddingHorizontal: 16, gap: 22 },
  category: { minHeight: 44, justifyContent: 'center', paddingVertical: 12, borderBottomWidth: 2, borderBottomColor: 'transparent' },
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
