import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '@/constants/theme';
import { useT } from '@/lib/i18n';

// A problem the customer should know about. With `onRetry` it gets a Try again button, for things
// that usually come right on their own (a dropped connection, a busy server).
export default function ErrorBanner({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  const t = useT();
  if (!message) return null;
  return (
    <View style={styles.banner} accessibilityRole="alert">
      <Text style={styles.text}>{message}</Text>
      {onRetry && (
        <Pressable accessibilityRole="button" onPress={onRetry} hitSlop={6}
          style={({ pressed }) => [styles.retry, pressed && { opacity: 0.7 }]}>
          <Text style={styles.retryText}>{t('menu.retry')}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.errorBg,
    padding: 14,
    borderRadius: 14,
    margin: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  text: { flex: 1, color: colors.errorText, fontFamily: fonts.sans },
  retry: {
    minHeight: 40, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 20,
    borderWidth: 1, borderColor: colors.errorText,
  },
  retryText: { fontFamily: fonts.sansBold, color: colors.errorText },
});
