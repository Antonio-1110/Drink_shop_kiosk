import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/theme';
import type { PlacedOrder } from '@/lib/api';

type Mode = 'qr' | 'pin';

// What the customer shows the machine to collect: scan the QR, or key in the PIN.
export default function PickupCode({ order }: { order: PlacedOrder }) {
  const hasQr = Boolean(order.pickup_qr);
  const hasPin = Boolean(order.pickup_pin);
  const [mode, setMode] = useState<Mode>(hasQr ? 'qr' : 'pin');

  // the codes only come back when the order is placed, so a reloaded page has lost them
  if (!hasQr && !hasPin) {
    return <Text style={styles.fallback}>Your pickup code is on the screen you saw right after ordering.</Text>;
  }

  return (
    <View style={styles.box}>
      {hasQr && hasPin && (
        <View style={styles.toggle} accessibilityRole="tablist">
          <ToggleButton label="QR code" selected={mode === 'qr'} onPress={() => setMode('qr')} />
          <ToggleButton label="PIN" selected={mode === 'pin'} onPress={() => setMode('pin')} />
        </View>
      )}
      {mode === 'qr' ? (
        <>
          <Image source={{ uri: order.pickup_qr }} style={styles.qr} accessibilityLabel="Pickup QR code" />
          <Text style={styles.hint}>Hold this up to the scanner on the machine.</Text>
        </>
      ) : (
        <>
          <Text style={styles.pin} accessibilityLabel={`Pickup PIN ${order.pickup_pin?.split('').join(' ')}`}>
            {order.pickup_pin}
          </Text>
          <Text style={styles.hint}>Key this PIN in on the machine&apos;s screen.</Text>
        </>
      )}
    </View>
  );
}

function ToggleButton({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.toggleButton, selected && styles.toggleSelected]}>
      <Text style={[styles.toggleText, selected && styles.toggleTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  box: { alignItems: 'center', gap: 8, alignSelf: 'stretch' },
  toggle: { flexDirection: 'row', backgroundColor: colors.primarySoft, borderRadius: 20, padding: 3 },
  toggleButton: { paddingVertical: 8, paddingHorizontal: 22, borderRadius: 18 },
  toggleSelected: { backgroundColor: colors.primary },
  toggleText: { color: colors.primary, fontWeight: '600' },
  toggleTextSelected: { color: colors.surface },
  qr: { width: 220, height: 220, marginVertical: 8 },
  pin: { fontSize: 44, fontWeight: 'bold', letterSpacing: 10, color: colors.text, marginVertical: 24, fontVariant: ['tabular-nums'] },
  hint: { color: colors.muted, textAlign: 'center' },
  fallback: { color: colors.text, textAlign: 'center' },
});
