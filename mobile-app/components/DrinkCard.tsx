import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/theme';
import { Drink, formatPrice, SIZE, Size } from '@/lib/menu';

// Phone version of the kiosk's DrinkCard: picture on top, S / L buttons that add to the cart.
export default function DrinkCard({ drink, onAdd }: { drink: Drink; onAdd: (drink: Drink, size: Size) => void }) {
  return (
    <View style={styles.card}>
      <View style={styles.image}>
        {drink.image_url ? (
          <Image source={{ uri: drink.image_url }} style={StyleSheet.absoluteFill} resizeMode="cover" />
        ) : (
          <Text style={styles.placeholder}>{drink.name.charAt(0)}</Text>
        )}
      </View>
      <View style={styles.info}>
        <Text style={styles.name} numberOfLines={2}>{drink.name}</Text>
        <View style={styles.sizes}>
          <SizeButton label={`S ${formatPrice(drink.s_price)}`} onPress={() => onAdd(drink, SIZE.SMALL)} />
          <SizeButton label={`L ${formatPrice(drink.l_price)}`} onPress={() => onAdd(drink, SIZE.LARGE)} />
        </View>
      </View>
    </View>
  );
}

function SizeButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Add ${label}`}
      onPress={onPress}
      style={({ pressed }) => [styles.sizeButton, pressed && { opacity: 0.7 }]}>
      <Text style={styles.sizeText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    margin: 6,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: colors.surface,
    boxShadow: '0 2px 6px rgba(0,0,0,0.1)',
  },
  image: {
    aspectRatio: 1.2,
    backgroundColor: colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholder: { color: colors.surface, fontSize: 36, fontWeight: 'bold' },
  info: { backgroundColor: colors.grey, padding: 10, gap: 8, alignItems: 'center', flexGrow: 1 },
  name: { fontSize: 15, fontWeight: '600', color: colors.text, textAlign: 'center' },
  sizes: { flexDirection: 'row', gap: 6, marginTop: 'auto' },
  sizeButton: { backgroundColor: colors.navy, borderRadius: 6, paddingVertical: 8, paddingHorizontal: 8 },
  sizeText: { color: colors.surface, fontWeight: 'bold', fontSize: 13 },
});
