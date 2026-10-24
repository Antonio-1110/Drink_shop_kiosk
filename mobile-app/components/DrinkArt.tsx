import { Image, StyleSheet, View } from 'react-native';

import { drinkLook } from '@/lib/drinkLook';

type ArtDrink = { name: string; category?: string; image_url?: string };

// A drawn cup for the drink (tinted by drinkLook), or its photo when it has one.
// Built from plain Views so it needs no SVG library; `size` is the square's side in points.
export default function DrinkArt({ drink, size = 84, rounded = 14 }: { drink: ArtDrink; size?: number; rounded?: number }) {
  if (drink.image_url) {
    return <Image source={{ uri: drink.image_url }} style={{ width: size, height: size, borderRadius: rounded }} resizeMode="cover" />;
  }
  const look = drinkLook(drink);
  const s = size / 100; // drawn on a 100 x 100 grid
  const cupW = 46 * s;
  const cupH = 58 * s;
  const taper = 6 * s;
  return (
    <View
      style={[styles.backdrop, { width: size, height: size, borderRadius: rounded, backgroundColor: look.backdrop }]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants">
      {/* straw */}
      <View style={[styles.straw, {
        width: 5 * s, height: 34 * s, borderRadius: 3 * s, left: 52 * s, top: 8 * s,
      }]} />
      <View style={{ width: cupW, height: cupH, marginTop: 14 * s }}>
        {/* liquid: foam on top, then the drink, then a darker base for brown sugar */}
        <View style={[styles.cup, { borderBottomLeftRadius: 6 * s, borderBottomRightRadius: 6 * s, backgroundColor: look.liquid }]}>
          <View style={{ height: '22%', backgroundColor: look.top }} />
          {look.base && <View style={[styles.base, { height: '38%', backgroundColor: look.base }]} />}
          {look.pearls && (
            <View style={[styles.pearls, { bottom: 3 * s, gap: 1.5 * s }]}>
              {Array.from({ length: 10 }, (_, i) => (
                <View key={i} style={{ width: 6 * s, height: 6 * s, borderRadius: 3 * s, backgroundColor: '#3a2418' }} />
              ))}
            </View>
          )}
          {look.seeds && Array.from({ length: 7 }, (_, i) => (
            <View key={i} style={[styles.dot, {
              width: 2.6 * s, height: 2.6 * s, borderRadius: 2 * s,
              left: (8 + i * 5) * s, top: (20 + ((i * 17) % 30)) * s,
            }]} />
          ))}
          {look.slice && (
            <View style={[styles.slice, { width: 16 * s, height: 16 * s, borderRadius: 8 * s, left: 8 * s, top: 20 * s, borderWidth: 1.5 * s }]} />
          )}
          {/* shine */}
          <View style={[styles.shine, { width: 3 * s, left: 6 * s, top: 10 * s, bottom: 8 * s, borderRadius: 2 * s }]} />
        </View>
        {/* the sides taper: triangles in the backdrop colour cut the corners */}
        <View style={[styles.cut, { left: 0, borderBottomWidth: cupH, borderRightWidth: taper, borderBottomColor: look.backdrop }]} />
        <View style={[styles.cut, { right: 0, borderBottomWidth: cupH, borderLeftWidth: taper, borderBottomColor: look.backdrop }]} />
        {/* lid rim */}
        <View style={[styles.rim, { height: 6 * s, borderRadius: 3 * s, left: -3 * s, right: -3 * s, top: -3 * s }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  straw: { position: 'absolute', backgroundColor: '#2b2320', opacity: 0.85, transform: [{ rotate: '12deg' }] },
  cup: { flex: 1, overflow: 'hidden' },
  base: { position: 'absolute', left: 0, right: 0, bottom: 0, opacity: 0.85 },
  pearls: { position: 'absolute', left: '18%', right: '18%', flexDirection: 'row', flexWrap: 'wrap-reverse', justifyContent: 'center' },
  dot: { position: 'absolute', backgroundColor: '#4b2e14', opacity: 0.6 },
  slice: { position: 'absolute', backgroundColor: '#f6e48b', borderColor: '#fff6c9' },
  shine: { position: 'absolute', backgroundColor: 'rgba(255,255,255,0.45)' },
  cut: { position: 'absolute', top: 0, width: 0, height: 0, borderLeftColor: 'transparent', borderRightColor: 'transparent' },
  rim: { position: 'absolute', backgroundColor: '#ffffff', borderWidth: 1, borderColor: 'rgba(43,35,32,0.15)' },
});
