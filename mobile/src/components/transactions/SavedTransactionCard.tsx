import { Ionicons } from '@expo/vector-icons';
import React, { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { ApiError, deleteTransaction } from '../../api';
import { formatAmount } from '../../format';
import { undoSavedEntry, type SavedEntry } from '../../savedEntry';
import { colors, font, radius, spacing, weight } from '../../theme';
import { AppText } from '../ui';

export function SavedTransactionCard({ entry, onDismiss, onAddAnother, onEdit, onUndone }: {
  entry: SavedEntry; onDismiss: () => void; onAddAnother: () => void;
  onEdit: () => void; onUndone: (id: string) => void;
}) {
  const [undoing, setUndoing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const undo = async () => {
    if (busy.current) return;
    busy.current = true;
    setUndoing(true);
    setError(null);
    try {
      await undoSavedEntry(entry, deleteTransaction);
      onUndone(entry.transaction.id);
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 401 ? null
        : failure instanceof ApiError && failure.status === 0
          ? 'לא התקבל אישור ביטול. בדוק את העסקאות; אפשר לנסות לבטל שוב את אותה שמירה.'
          : 'לא הצלחנו לבטל את השמירה. אפשר לנסות שוב.');
    } finally {
      busy.current = false;
      setUndoing(false);
    }
  };
  return (
    <View style={styles.card} accessibilityLiveRegion="polite">
      <View style={styles.heading}>
        <Ionicons name="checkmark-circle" size={22} color={colors.success} />
        <View style={styles.title}>
          <AppText weight={weight.semibold}>נשמרה עסקה · {formatAmount(entry.transaction.amount_minor, entry.transaction.currency)}</AppText>
          {entry.transaction.merchant_display_name ? <AppText size={font.caption} color={colors.textSecondary} numberOfLines={1}>{entry.transaction.merchant_display_name}</AppText> : null}
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="סגירת הודעת השמירה" disabled={undoing}
          onPress={onDismiss} style={styles.close}>
          <Ionicons name="close" size={22} color={colors.textSecondary} />
        </Pressable>
      </View>
      {entry.duplicateLooking ? <AppText size={font.caption} color={colors.textSecondary}>נמצאה עסקה דומה מאותו יום. אפשר להשאיר את שתיהן או לבטל את השמירה האחרונה.</AppText> : null}
      {entry.largeAmount ? <AppText size={font.caption} color={colors.textSecondary}>הסכום גבוה — כדאי לבדוק שלא נפלה טעות בהקלדה. העסקה כבר נשמרה.</AppText> : null}
      {error ? <AppText size={font.caption} color={colors.danger}>{error}</AppText> : null}
      <View style={styles.actions}>
        {entry.largeAmount ? <Action label="הסכום נכון" icon="checkmark" onPress={onDismiss} disabled={undoing} /> : null}
        <Action label="עוד עסקה" icon="add" onPress={onAddAnother} disabled={undoing} />
        <Action label="עריכת העסקה שנשמרה" shortLabel="עריכה" icon="create-outline" onPress={onEdit} disabled={undoing} />
        <Action label="ביטול השמירה האחרונה" shortLabel="ביטול שמירה" icon="arrow-undo-outline" onPress={() => { void undo(); }} disabled={undoing} />
        {undoing ? <ActivityIndicator color={colors.accent} /> : null}
      </View>
    </View>
  );
}

function Action({ label, shortLabel, icon, onPress, disabled }: {
  label: string; shortLabel?: string; icon: keyof typeof Ionicons.glyphMap; onPress: () => void; disabled: boolean;
}) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress} style={[styles.action, disabled && styles.disabled]}>
    <Ionicons name={icon} size={16} color={colors.accent} />
    <AppText size={font.caption} color={colors.accent} weight={weight.semibold}>{shortLabel ?? label}</AppText>
  </Pressable>;
}

const styles = StyleSheet.create({
  card: { marginHorizontal: spacing.lg, marginBottom: spacing.md, padding: spacing.md, gap: spacing.sm,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.card },
  heading: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  title: { flex: 1, gap: 2 },
  close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: spacing.xs },
  action: { minHeight: 44, paddingHorizontal: spacing.sm, flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  disabled: { opacity: 0.45 },
});
