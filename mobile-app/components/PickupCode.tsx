import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '@/constants/theme';
import type { PlacedOrder } from '@/lib/api';
import { useT } from '@/lib/i18n';

type Mode = 'qr' | 'pin';

// What the customer shows the machine to collect: scan the QR, or key in the PIN.
export default function PickupCode({ order }: { order: PlacedOrder }) {
  const t = useT();
  const hasQr = Boolean(order.pickup_qr);
  const hasPin = Boolean(order.pickup_pin);
  const [mode, setMode] = useState<Mode>(hasQr ? 'qr' : 'pin');

  // the codes only come back when the order is placed, so a reloaded page has lost them
  if (!hasQr && !hasPin) {
    return <Text style={styles.fallback}>{t('pickup.missing')}</Text>;
  }

  return (
    <View style={styles.box}>
      {hasQr && hasPin && (
        <View style={styles.toggle} accessibilityRole="tablist">
          <ToggleButton label={t('pickup.qr')} selected={mode === 'qr'} onPress={() => setMode('qr')} />
          <ToggleButton label={t('pickup.pin')} selected={mode === 'pin'} onPress={() => setMode('pin')} />
        </View>
      )}
      {mode === 'qr' ? (
        <>
          <Image source={{ uri: order.pickup_qr }} style={styles.qr} accessibilityLabel={t('pickup.qrAlt')} />
          <Text style={styles.hint}>{t('pickup.qrHint')}</Text>
        </>
      ) : (
        <>
          <Text style={styles.pin} accessibilityLabel={t('pickup.pinLabel', { digits: order.pickup_pin?.split('').join(' ') ?? '' })}>
            {order.pickup_pin}
          </Text>
          <Text style={styles.hint}>{t('pickup.pinHint')}</Text>
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
  toggleButton: { minHeight: 44, justifyContent: 'center', paddingVertical: 8, paddingHorizontal: 22, borderRadius: 18 },
  toggleSelected: { backgroundColor: colors.primary },
  toggleText: { fontFamily: fonts.sansBold, color: colors.primary },
  toggleTextSelected: { color: colors.surface },
  qr: { width: 220, height: 220, marginVertical: 8 },
  pin: { fontFamily: fonts.serif, fontSize: 48, letterSpacing: 10, color: colors.text, marginVertical: 24, fontVariant: ['tabular-nums'] },
  hint: { fontFamily: fonts.sans, color: colors.muted, textAlign: 'center' },
  fallback: { color: colors.text, textAlign: 'center' },
});
