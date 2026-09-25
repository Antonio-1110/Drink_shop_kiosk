import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import LevelPicker from '@/components/LevelPicker';
import { colors } from '@/constants/theme';
import { fetchDesignerOptions } from '@/lib/api';
import { useCart } from '@/lib/cart';
import {
  blockedReason, cupLayers, Design, DesignerOptions, designName, designNutrition, designPrice,
  designToCartItem, findOption, missingChoice, newDesign, toggleOption,
} from '@/lib/designer';
import { formatPrice } from '@/lib/menu';
import { GRADE_COLORS } from '@/lib/nutrigrade';

// A tapered-looking cup: liquids stacked bottom first, toppings at the bottom.
function Cup({ options, design }: { options: DesignerOptions; design: Design }) {
  const layers = cupLayers(options, design);
  const total = layers.reduce((sum, layer) => sum + layer.ml, 0) || 1;
  const toppingColors = (design.selections.topping ?? []).map((id) => findOption(options, id).color);
  return (
    <View style={styles.cup} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <View style={styles.cupLiquid}>
        {layers.map((layer) => (
          <View key={layer.id} style={{ flexGrow: layer.ml / total, backgroundColor: layer.color }} />
        ))}
      </View>
      {design.ice > 0 && <Text style={styles.cupIce}>{'❄'.repeat(design.ice)}</Text>}
      <View style={styles.cupToppings}>
        {toppingColors.flatMap((color, i) => Array.from({ length: 5 }, (_, j) => (
          <View key={`${i}-${j}`} style={[styles.toppingDot, { backgroundColor: color }]} />
        )))}
      </View>
    </View>
  );
}

function Chip({ label, sublabel, selected, disabled, onPress }: {
  label: string; sublabel?: string; selected: boolean; disabled?: boolean; onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected, disabled && styles.chipDisabled]}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
      {sublabel ? <Text style={[styles.chipSub, selected && styles.chipTextSelected]}>{sublabel}</Text> : null}
    </Pressable>
  );
}

export default function DesignerScreen() {
  const { shop, addCustomToCart } = useCart();
  const [options, setOptions] = useState<DesignerOptions | null>(null);
  const [design, setDesign] = useState<Design | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!shop) return;
    fetchDesignerOptions(shop.id)
      .then((data) => { setOptions(data); setDesign(newDesign(data)); })
      .catch((err) => setLoadError(err.message));
  }, [shop]);

  if (!shop) return <ErrorBanner message="Choose a shop first." />;
  if (loadError) return <ErrorBanner message={`Could not load the drink designer: ${loadError}`} />;
  if (!options || !design) return <Text style={styles.loading}>Loading…</Text>;

  const nutrition = designNutrition(options, design);
  const missing = missingChoice(options, design);
  const add = () => {
    addCustomToCart(designToCartItem(options, design));
    router.navigate('/cart');
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        {options.stub && <Text style={styles.stubNote}>Demo options: prices and ingredients aren&apos;t final yet.</Text>}

        <View style={styles.preview}>
          <Cup options={options} design={design} />
          <View style={styles.previewText}>
            <Text style={styles.name}>{designName(options, design)}</Text>
            <View style={styles.gradeRow}>
              <Text style={[styles.gradeBadge, { backgroundColor: GRADE_COLORS[nutrition.grade] }]}>{nutrition.grade}</Text>
              <Text style={styles.gradeDetail}>
                Nutri-Grade{'\n'}{nutrition.sugar.toFixed(1)} g sugar{'\n'}{nutrition.satFat.toFixed(1)} g sat. fat / 100 mL
              </Text>
            </View>
          </View>
        </View>

        <Text style={styles.groupTitle}>Cup size</Text>
        <View style={styles.chips}>
          {options.sizes.map((size) => (
            <Chip key={size.value} label={size.label} sublabel={formatPrice(size.base_price)}
              selected={design.size === size.value} onPress={() => setDesign({ ...design, size: size.value })} />
          ))}
        </View>

        {options.groups.map((group) => (
          <View key={group.key}>
            <Text style={styles.groupTitle}>{group.label} <Text style={styles.hint}>{group.hint}</Text></Text>
            <View style={styles.chips}>
              {group.options.map((option) => {
                const reason = blockedReason(options, design, group, option.id);
                return (
                  <Chip key={option.id} label={option.name}
                    sublabel={reason ?? (Number(option.price) ? `+${formatPrice(option.price)}` : 'Included')}
                    selected={design.selections[group.key].includes(option.id)} disabled={Boolean(reason)}
                    onPress={() => setDesign(toggleOption(options, design, group, option.id))} />
                );
              })}
            </View>
          </View>
        ))}

        <Text style={styles.groupTitle}>Sugar and ice</Text>
        <View style={styles.levels}>
          <LevelPicker label="Sugar" value={design.sugar} onChange={(sugar) => setDesign({ ...design, sugar })} />
          <LevelPicker label="Ice" value={design.ice} onChange={(ice) => setDesign({ ...design, ice })} />
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <View>
          <Text style={styles.muted}>Price</Text>
          <Text style={styles.total}>{formatPrice(designPrice(options, design))}</Text>
        </View>
        <Pressable accessibilityRole="button" onPress={add} disabled={Boolean(missing)}
          style={[styles.addButton, missing && { opacity: 0.5 }]}>
          <Text style={styles.addText}>{missing ?? 'Add to cart'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 14, paddingBottom: 24 },
  loading: { textAlign: 'center', color: colors.muted, marginTop: 40 },
  stubNote: { backgroundColor: colors.header, color: colors.accent, padding: 10, borderRadius: 8, marginBottom: 12 },
  preview: { flexDirection: 'row', gap: 16, alignItems: 'center', backgroundColor: colors.surface, borderRadius: 14, padding: 14 },
  previewText: { flex: 1, gap: 10 },
  name: { fontSize: 17, fontWeight: 'bold', color: colors.text },
  gradeRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  gradeBadge: {
    width: 44, height: 44, lineHeight: 44, borderRadius: 8, overflow: 'hidden',
    color: colors.surface, fontSize: 26, fontWeight: 'bold', textAlign: 'center',
  },
  gradeDetail: { fontSize: 12, color: colors.muted, flexShrink: 1 },
  cup: {
    width: 90, height: 130, backgroundColor: colors.cream, overflow: 'hidden',
    borderBottomLeftRadius: 18, borderBottomRightRadius: 18, borderWidth: 2, borderColor: colors.border,
  },
  cupLiquid: { position: 'absolute', top: '12%', left: 0, right: 0, bottom: 0, flexDirection: 'column-reverse' },
  cupIce: { position: 'absolute', top: '15%', width: '100%', textAlign: 'center', color: 'rgba(255,255,255,0.9)', fontSize: 14 },
  cupToppings: {
    position: 'absolute', bottom: 4, left: 8, right: 8,
    flexDirection: 'row', flexWrap: 'wrap-reverse', justifyContent: 'center', gap: 2,
  },
  toppingDot: { width: 9, height: 9, borderRadius: 5, borderWidth: 1, borderColor: 'rgba(0,0,0,0.25)' },
  groupTitle: { fontSize: 17, fontWeight: 'bold', color: colors.primary, marginTop: 18, marginBottom: 8 },
  hint: { fontSize: 13, fontWeight: 'normal', color: colors.muted },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.primarySoft, alignItems: 'center' },
  chipSelected: { backgroundColor: colors.primary },
  chipDisabled: { opacity: 0.45 },
  chipText: { color: colors.primary, fontWeight: '600' },
  chipSub: { color: colors.accent, fontSize: 12 },
  chipTextSelected: { color: colors.surface },
  levels: { gap: 8 },
  footer: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14,
    borderTopWidth: 2, borderTopColor: colors.border, backgroundColor: colors.surface,
  },
  muted: { color: colors.muted },
  total: { fontSize: 22, fontWeight: 'bold', color: colors.accent },
  addButton: { backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 22 },
  addText: { color: colors.surface, fontWeight: 'bold', fontSize: 16 },
});
