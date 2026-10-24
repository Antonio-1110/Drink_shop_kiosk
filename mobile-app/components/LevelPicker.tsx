import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '@/constants/theme';
import { LEVELS } from '@/lib/menu';

// A row of equal-width chips for sugar or ice, since a dropdown is fiddly on a phone.
export default function LevelPicker({ label, value, onChange }: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.chips}>
        {LEVELS.map((level) => {
          const selected = level.value === value;
          return (
            <Pressable
              key={level.value}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={`${label} ${level.label}`}
              onPress={() => onChange(level.value)}
              style={[styles.chip, selected && styles.chipSelected]}>
              <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{level.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { gap: 8 },
  label: { fontFamily: fonts.sansMedium, color: colors.muted, fontSize: 13 },
  chips: { flexDirection: 'row', gap: 6 },
  chip: {
    flex: 1, minHeight: 42, borderRadius: 21, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center',
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontFamily: fonts.sansMedium, fontSize: 13, color: colors.text },
  chipTextSelected: { color: colors.surface },
});
