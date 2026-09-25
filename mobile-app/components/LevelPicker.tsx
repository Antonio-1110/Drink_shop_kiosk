import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/theme';
import { LEVELS } from '@/lib/menu';

// A row of chips for sugar or ice, since a dropdown is fiddly on a phone.
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
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { width: 40, color: colors.muted, fontSize: 13 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, flex: 1 },
  chip: { paddingVertical: 5, paddingHorizontal: 8, borderRadius: 14, backgroundColor: colors.lightBlue },
  chipSelected: { backgroundColor: colors.navy },
  chipText: { fontSize: 12, color: colors.navy },
  chipTextSelected: { color: colors.surface, fontWeight: 'bold' },
});
