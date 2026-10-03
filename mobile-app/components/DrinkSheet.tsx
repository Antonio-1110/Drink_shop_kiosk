import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import DrinkArt from '@/components/DrinkArt';
import { colors, fonts } from '@/constants/theme';
import { CartItem, formatPrice, itemPrice, LEVELS, SIZE, Size } from '@/lib/menu';

export type DrinkChoice = { size: Size; sugar: number; ice: number };

function Chip({ label, sublabel, selected, onPress, a11y }: {
  label: string; sublabel?: string; selected: boolean; onPress: () => void; a11y: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={a11y}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
      {sublabel ? <Text style={[styles.chipSub, selected && styles.chipSubSelected]}>{sublabel}</Text> : null}
    </Pressable>
  );
}

function LevelRow({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <View style={styles.group}>
      <Text style={styles.groupLabel}>{label}</Text>
      {/* five equal chips fill the width, so they're easy to hit with a thumb */}
      <View style={styles.levelRow}>
        {LEVELS.map((level) => (
          <Chip key={level.value} label={level.label} selected={value === level.value}
            onPress={() => onChange(level.value)} a11y={`${label} ${level.label}`} />
        ))}
      </View>
    </View>
  );
}

// Choose size, sugar and ice for a drink, in a sheet that slides up from the bottom of the phone.
// `item` is the cart line being added or edited; a designed drink keeps the size it was designed
// in, so only sugar and ice show for it.
export default function DrinkSheet({ item, confirmLabel, onConfirm, onClose }: {
  item: CartItem | null;
  confirmLabel: string;
  onConfirm: (choice: DrinkChoice) => void;
  onClose: () => void;
}) {
  return (
    <Modal visible={item !== null} transparent animationType="slide" onRequestClose={onClose}>
      {item && <SheetBody key={String(item.drink.id) + item.drink.name} item={item} confirmLabel={confirmLabel}
        onConfirm={onConfirm} onClose={onClose} />}
    </Modal>
  );
}

function SheetBody({ item, confirmLabel, onConfirm, onClose }: {
  item: CartItem; confirmLabel: string; onConfirm: (choice: DrinkChoice) => void; onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [choice, setChoice] = useState<DrinkChoice>({ size: item.size, sugar: item.sugar, ice: item.ice });
  const set = (changes: Partial<DrinkChoice>) => setChoice({ ...choice, ...changes });
  const price = itemPrice({ ...item, ...choice } as CartItem);
  const drink = item.drink;
  const description = 'description' in drink ? drink.description : '';

  return (
    <View style={styles.backdrop}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
      <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        <View style={styles.handle} />
        <ScrollView contentContainerStyle={styles.content} bounces={false}>
          <View style={styles.header}>
            <DrinkArt drink={drink} size={96} rounded={18} />
            <View style={styles.headerText}>
              <Text style={styles.name}>{drink.name}</Text>
              {description ? <Text style={styles.description}>{description}</Text> : null}
            </View>
          </View>

          {!item.custom && (
            <View style={styles.group}>
              <Text style={styles.groupLabel}>Size</Text>
              <View style={styles.sizeRow}>
                <Chip label="Regular" sublabel={formatPrice(item.drink.s_price)} selected={choice.size === SIZE.SMALL}
                  onPress={() => set({ size: SIZE.SMALL })} a11y="Regular size" />
                <Chip label="Large" sublabel={formatPrice(item.drink.l_price)} selected={choice.size === SIZE.LARGE}
                  onPress={() => set({ size: SIZE.LARGE })} a11y="Large size" />
              </View>
            </View>
          )}
          <LevelRow label="Sugar" value={choice.sugar} onChange={(sugar) => set({ sugar })} />
          <LevelRow label="Ice" value={choice.ice} onChange={(ice) => set({ ice })} />
        </ScrollView>

        <Pressable accessibilityRole="button" onPress={() => onConfirm(choice)}
          style={({ pressed }) => [styles.confirm, pressed && { opacity: 0.85 }]}>
          <Text style={styles.confirmText}>{confirmLabel}</Text>
          <Text style={styles.confirmText}>{formatPrice(price)}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(43,35,32,0.4)' },
  sheet: {
    maxHeight: '88%',
    backgroundColor: colors.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
  },
  handle: { alignSelf: 'center', width: 40, height: 5, borderRadius: 3, backgroundColor: colors.border, marginTop: 10, marginBottom: 6 },
  content: { paddingTop: 10, paddingBottom: 8, gap: 22 },
  header: { flexDirection: 'row', gap: 16, alignItems: 'center' },
  headerText: { flex: 1, gap: 4 },
  name: { fontFamily: fonts.serif, fontSize: 24, color: colors.text },
  description: { fontFamily: fonts.sans, fontSize: 14, lineHeight: 20, color: colors.muted },
  group: { gap: 10 },
  groupLabel: { fontFamily: fonts.sansBold, fontSize: 12, letterSpacing: 1.2, textTransform: 'uppercase', color: colors.muted },
  sizeRow: { flexDirection: 'row', gap: 10 },
  levelRow: { flexDirection: 'row', gap: 6 },
  chip: {
    flex: 1,
    minHeight: 46,
    borderRadius: 23,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontFamily: fonts.sansMedium, fontSize: 14, color: colors.text },
  chipTextSelected: { color: colors.surface },
  chipSub: { fontFamily: fonts.sans, fontSize: 13, color: colors.muted },
  chipSubSelected: { color: 'rgba(255,255,255,0.8)' },
  confirm: {
    marginTop: 12,
    minHeight: 54,
    borderRadius: 27,
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
  },
  confirmText: { fontFamily: fonts.sansBold, fontSize: 16, color: colors.surface },
});
