import { StyleSheet, Text } from 'react-native';

import { colors } from '@/constants/theme';

export default function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return <Text style={styles.banner} accessibilityRole="alert">{message}</Text>;
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.errorBg,
    color: colors.errorText,
    padding: 12,
    borderRadius: 8,
    margin: 12,
  },
});
