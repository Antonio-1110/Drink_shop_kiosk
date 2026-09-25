import QRCode from 'qrcode';
import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

// Draws a QR code from plain Views, so it needs no native module or image generation.
export default function QrCode({ value, size = 220 }: { value: string; size?: number }) {
  const { count, rows } = useMemo(() => {
    const { modules } = QRCode.create(value, { errorCorrectionLevel: 'M' });
    const all = Array.from({ length: modules.size }, (_, r) =>
      Array.from({ length: modules.size }, (_, c) => Boolean(modules.get(r, c))));
    return { count: modules.size, rows: all };
  }, [value]);
  // a quiet zone of 2 modules on each side, which scanners need
  const cell = Math.floor(size / (count + 4));
  return (
    <View style={[styles.frame, { padding: cell * 2 }]} accessibilityRole="image" accessibilityLabel={`QR code for ${value}`}>
      {rows.map((row, r) => (
        <View key={r} style={styles.row}>
          {row.map((dark, c) => (
            <View key={c} style={{ width: cell, height: cell, backgroundColor: dark ? '#000' : '#fff' }} />
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { backgroundColor: '#fff', alignSelf: 'center' },
  row: { flexDirection: 'row' },
});
