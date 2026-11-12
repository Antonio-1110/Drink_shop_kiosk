import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '@/constants/theme';
import type { NutriGradeLabel } from '@/lib/menu';
import { GRADE_COLORS } from '@/lib/nutrigrade';

// HPB Nutri-Grade mark: the grade and the sugar per 100 mL. Menus must show it next to every C or D
// drink (the backend's `label_required`); A and B are optional, so they stay off to keep the menu calm.
export default function NutriGradeMark({ grade, large = false }: { grade?: NutriGradeLabel | null; large?: boolean }) {
  if (!grade?.label_required) return null;
  return (
    <View style={styles.mark} accessible accessibilityLabel={`Nutri-Grade ${grade.grade}, ${grade.sugar_percent}% sugar`}>
      <View style={[styles.letterBox, large && styles.letterBoxLarge, { backgroundColor: GRADE_COLORS[grade.grade] }]}>
        <Text style={[styles.letter, large && styles.letterLarge]}>{grade.grade}</Text>
      </View>
      <View style={styles.text}>
        <Text style={styles.small}>Nutri-Grade</Text>
        <Text style={[styles.sugar, large && styles.sugarLarge]}>{grade.sugar_percent}% sugar</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  mark: {
    flexDirection: 'row',
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 7,
    overflow: 'hidden',
    backgroundColor: colors.surface,
  },
  letterBox: { minWidth: 26, alignItems: 'center', justifyContent: 'center' },
  letterBoxLarge: { minWidth: 34 },
  letter: { fontFamily: fonts.sansBold, fontSize: 15, color: colors.surface },
  letterLarge: { fontSize: 20 },
  text: { paddingVertical: 3, paddingHorizontal: 7, justifyContent: 'center' },
  small: { fontFamily: fonts.sans, fontSize: 9, color: colors.muted },
  sugar: { fontFamily: fonts.sansBold, fontSize: 11, color: colors.text },
  sugarLarge: { fontSize: 13 },
});
