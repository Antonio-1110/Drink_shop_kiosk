import { Pressable, StyleSheet, Text, View } from 'react-native';

import DrinkArt from '@/components/DrinkArt';
import { colors, fonts } from '@/constants/theme';
import { Drink, formatPrice } from '@/lib/menu';

// One drink on the phone menu: a full-width row, so names and descriptions have room and the
// whole row is one easy target. Tapping it opens the drink's options (see DrinkSheet).
export default function DrinkCard({ drink, onSelect }: { drink: Drink; onSelect: (drink: Drink) => void }) {
  const from = Math.min(Number(drink.s_price), Number(drink.l_price));
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${drink.name}, from ${formatPrice(from)}`}
      onPress={() => onSelect(drink)}
      style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.cream }]}>
      <DrinkArt drink={drink} size={88} />
      <View style={styles.info}>
        <Text style={styles.name} numberOfLines={2}>{drink.name}</Text>
        {drink.description ? <Text style={styles.description} numberOfLines={2}>{drink.description}</Text> : null}
        <View style={styles.foot}>
          <Text style={styles.price}>{formatPrice(from)}</Text>
          <View style={styles.add}><Text style={styles.addText}>+</Text></View>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 14, paddingVertical: 14, paddingHorizontal: 16 },
  info: { flex: 1, gap: 3 },
  name: { fontFamily: fonts.serif, fontSize: 18, color: colors.text },
  description: { fontFamily: fonts.sans, fontSize: 13, lineHeight: 18, color: colors.muted },
  foot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto', paddingTop: 4 },
  price: { fontFamily: fonts.sansBold, fontSize: 15, color: colors.text },
  add: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  addText: { color: colors.surface, fontSize: 20, lineHeight: 22, fontFamily: fonts.sans },
});
