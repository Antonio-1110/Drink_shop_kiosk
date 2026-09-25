import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import ErrorBanner from '@/components/ErrorBanner';
import LevelPicker from '@/components/LevelPicker';
import QrCode from '@/components/QrCode';
import { colors } from '@/constants/theme';
import { fetchDesignerOptions } from '@/lib/api';
import { useCart } from '@/lib/cart';
import {
  categories, Design, DesignerOptions, designName, designNutrition, designPrice, designToCartItem,
  encodeDesign, ingredientPrice, missingChoice, newDesign, recipe, RecipeLine, togglePick,
} from '@/lib/designer';
import { formatPrice } from '@/lib/menu';
import { GRADE_COLORS } from '@/lib/nutrigrade';

// A cup preview: liquids stacked bottom first, toppings at the bottom.
function Cup({ lines, ice }: { lines: RecipeLine[]; ice: number }) {
  const liquids = lines.filter((line) => line.unit === 'mL');
  const total = liquids.reduce((sum, line) => sum + line.amount, 0) || 1;
  const toppings = lines.filter((line) => line.unit === 'g');
  return (
    <View style={styles.cup} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <View style={styles.cupLiquid}>
        {liquids.map((line) => (
          <View key={line.code} style={{ flexGrow: line.amount / total, backgroundColor: line.color }} />
        ))}
      </View>
      {ice > 0 && <Text style={styles.cupIce}>{'❄'.repeat(ice)}</Text>}
      <View style={styles.cupToppings}>
        {toppings.flatMap((line) => Array.from({ length: Math.max(2, Math.round(10 / toppings.length)) }, (_, j) => (
          <View key={`${line.code}-${j}`} style={[styles.toppingDot, { backgroundColor: line.color }]} />
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
  const [showCode, setShowCode] = useState(false);

  useEffect(() => {
    if (!shop) return;
    fetchDesignerOptions(shop.id)
      .then((data) => { setOptions(data); setDesign(newDesign(data)); })
      .catch((err) => setLoadError(err.message));
  }, [shop]);

  if (!shop) return <ErrorBanner message="Choose a shop first." />;
  if (loadError) return <ErrorBanner message={`Could not load the drink designer: ${loadError}`} />;
  if (!options || !design) return <Text style={styles.loading}>Loading…</Text>;

  const lines = recipe(options, design);
  const nutrition = designNutrition(options, design);
  const missing = missingChoice(options, design);
  const add = () => {
    addCustomToCart(designToCartItem(options, design));
    router.navigate('/cart');
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.preview}>
          <Cup lines={lines} ice={design.ice} />
          <View style={styles.previewText}>
            <Text style={styles.name}>{designName(options, design)}</Text>
            {/* amounts change as ingredients are added, so show what actually goes in */}
            {lines.map((line) => (
              <Text key={line.code} style={styles.recipeLine}>{line.name}: {Math.round(line.amount)} {line.unit}</Text>
            ))}
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
            <Chip key={size.value} label={size.label} sublabel={formatPrice(options.pricing.cup[size.value])}
              selected={design.size === size.value} onPress={() => setDesign({ ...design, size: size.value })} />
          ))}
        </View>

        {categories(options).map((category) => (
          <View key={category}>
            <Text style={styles.groupTitle}>{category}</Text>
            <View style={styles.chips}>
              {options.ingredients.filter((i) => i.category === category).map((i) => {
                const selected = design.picks.includes(i.code);
                const soldOut = i.available === false && !selected;
                const price = ingredientPrice(options, i);
                return (
                  <Chip key={i.code} label={i.name}
                    sublabel={soldOut ? 'Sold out' : price ? `+${formatPrice(price)}` : 'Included'}
                    selected={selected} disabled={soldOut}
                    onPress={() => setDesign(togglePick(options, design, i.code))} />
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
        <View style={styles.footerButtons}>
          <Pressable accessibilityRole="button" onPress={() => setShowCode(true)} disabled={Boolean(missing)}
            style={[styles.codeButton, missing && { opacity: 0.5 }]}>
            <Text style={styles.codeText}>Kiosk QR</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={add} disabled={Boolean(missing)}
            style={[styles.addButton, missing && { opacity: 0.5 }]}>
            <Text style={styles.addText}>{missing ?? 'Add to cart'}</Text>
          </Pressable>
        </View>
      </View>

      <Modal visible={showCode} transparent animationType="fade" onRequestClose={() => setShowCode(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Scan this at the kiosk</Text>
            <Text style={styles.modalText}>Hold it up to the kiosk&apos;s reader and your drink appears on its screen.</Text>
            <QrCode value={encodeDesign(design)} />
            <Text style={styles.codeValue} selectable>{encodeDesign(design)}</Text>
            <Pressable accessibilityRole="button" onPress={() => setShowCode(false)} style={styles.addButton}>
              <Text style={styles.addText}>Done</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 14, paddingBottom: 24 },
  loading: { textAlign: 'center', color: colors.muted, marginTop: 40 },
  preview: { flexDirection: 'row', gap: 16, alignItems: 'center', backgroundColor: colors.surface, borderRadius: 14, padding: 14 },
  previewText: { flex: 1, gap: 4 },
  name: { fontSize: 17, fontWeight: 'bold', color: colors.text, marginBottom: 2 },
  recipeLine: { fontSize: 12, color: colors.muted },
  gradeRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 },
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
  footerButtons: { flexDirection: 'row', gap: 8, flexShrink: 1 },
  muted: { color: colors.muted },
  total: { fontSize: 22, fontWeight: 'bold', color: colors.accent },
  codeButton: { backgroundColor: colors.secondary, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 14 },
  codeText: { color: colors.text, fontWeight: 'bold', fontSize: 16 },
  addButton: { backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 14, paddingHorizontal: 18, flexShrink: 1 },
  addText: { color: colors.surface, fontWeight: 'bold', fontSize: 16, textAlign: 'center' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', padding: 24 },
  modal: { backgroundColor: colors.surface, borderRadius: 16, padding: 20, gap: 12, alignItems: 'center' },
  modalTitle: { fontSize: 20, fontWeight: 'bold', color: colors.primary },
  modalText: { color: colors.muted, textAlign: 'center' },
  codeValue: { fontFamily: 'monospace', color: colors.text },
});
