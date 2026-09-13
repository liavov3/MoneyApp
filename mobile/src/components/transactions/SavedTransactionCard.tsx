import { Ionicons } from '@expo/vector-icons';
import React, { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError, categorizeTransaction, deleteTransaction } from '../../api';
import { formatAmount } from '../../format';
import { rememberSavedCategory, undoSavedEntry, type SavedEntry } from '../../savedEntry';
import { colors, font, radius, spacing, weight } from '../../theme';
import type { TransactionOut } from '../../types';
import { useCategories } from '../../useCategories';
import { CategoryChip } from '../categories/CategoryChip';
import { CategoryStatus } from '../categories/CategoryStatus';
import { AppText } from '../ui';

export function SavedTransactionCard({ entry, onDismiss, onAddAnother, onEdit, onUndone, onRemembered }: {
  entry: SavedEntry; onDismiss: () => void; onAddAnother: () => void;
  onEdit: () => void; onUndone: (id: string) => void;
  onRemembered: (transaction: TransactionOut) => void;
}) {
  const { consumer } = useCategories();
  const [pending, setPending] = useState<'undo' | 'remember' | null>(null);
  const [ruleDismissed, setRuleDismissed] = useState(false);
  const [remembered, setRemembered] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const repeatedOther = entry.rulePrompt?.suggested_category_key === 'other_spending';
  const [choice, setChoice] = useState<string | null>(repeatedOther ? null : entry.rulePrompt?.suggested_category_id ?? null);
  const selectedCategory = consumer.find((category) => category.id === choice);
  const working = pending !== null;
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const undo = async () => {
    if (busy.current) return;
    busy.current = true;
    setPending('undo');
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
      setPending(null);
    }
  };
  const remember = async () => {
    if (busy.current || !selectedCategory || !entry.rulePrompt) return;
    busy.current = true;
    setPending('remember');
    setError(null);
    try {
      const result = await rememberSavedCategory(entry, selectedCategory.id, categorizeTransaction);
      setRemembered(true);
      onRemembered(result.transaction);
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 401 ? null
        : failure instanceof ApiError && failure.status === 0
          ? 'לא התקבל אישור לזכירת הקטגוריה. העסקה נשמרה; אפשר לנסות שוב.'
          : 'לא הצלחנו לזכור את הקטגוריה. העסקה נשמרה; אפשר לנסות שוב.');
    } finally {
      busy.current = false;
      setPending(null);
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
        <Pressable accessibilityRole="button" accessibilityLabel="סגירת הודעת השמירה" disabled={working}
          onPress={onDismiss} style={styles.close}>
          <Ionicons name="close" size={22} color={colors.textSecondary} />
        </Pressable>
      </View>
      {entry.duplicateLooking ? <AppText size={font.caption} color={colors.textSecondary}>נמצאה עסקה דומה מאותו יום. אפשר להשאיר את שתיהן או לבטל את השמירה האחרונה.</AppText> : null}
      {entry.largeAmount ? <AppText size={font.caption} color={colors.textSecondary}>הסכום גבוה — כדאי לבדוק שלא נפלה טעות בהקלדה. העסקה כבר נשמרה.</AppText> : null}
      {entry.rulePrompt && !ruleDismissed && !remembered ? <View style={styles.rule}>
        <AppText size={font.caption}>
          {repeatedOther && !choice
            ? `כבר שמרת את ${entry.transaction.merchant_display_name} בהוצאות אחרות. לבחור קטגוריה מדויקת יותר ולזכור אותה להבא?`
            : `לזכור את ${entry.transaction.merchant_display_name} בקטגוריית ${selectedCategory?.label_he ?? selectedCategory?.label_en ?? 'הקטגוריה שנבחרה'} גם בפעם הבאה?`}
        </AppText>
        {choosing ? <ScrollView style={styles.categoryPicker} keyboardShouldPersistTaps="handled">
          <View style={styles.categoryChoices}>{consumer.filter((category) => category.key !== 'other_spending').map((category) =>
            <CategoryChip key={category.id} categoryKey={category.key} label={category.label_he ?? category.label_en}
              selected={choice === category.id} onPress={() => { if (!working) { setChoice(category.id); setChoosing(false); } }} />
          )}</View>
          <CategoryStatus />
        </ScrollView> : null}
        <View style={styles.actions}>
          {repeatedOther ? <Action label={choice ? 'שינוי קטגוריה' : 'בחירת קטגוריה'} icon="pricetag-outline"
            onPress={() => setChoosing((current) => !current)} disabled={working} /> : null}
          {selectedCategory ? <Action label="כן, לזכור" icon="checkmark" onPress={() => { void remember(); }} disabled={working} /> : null}
          <Action label="לא עכשיו" icon="close" onPress={() => { setRuleDismissed(true); setError(null); }} disabled={working} />
        </View>
      </View> : null}
      {remembered ? <AppText size={font.caption} color={colors.success}>הקטגוריה תוצע גם בפעם הבאה. עסקאות קודמות נשארו כפי שהיו.</AppText> : null}
      {error ? <AppText size={font.caption} color={colors.danger}>{error}</AppText> : null}
      <View style={styles.actions}>
        {entry.largeAmount ? <Action label="הסכום נכון" icon="checkmark" onPress={onDismiss} disabled={working} /> : null}
        <Action label="עוד עסקה" icon="add" onPress={onAddAnother} disabled={working} />
        <Action label="עריכת העסקה שנשמרה" shortLabel="עריכה" icon="create-outline" onPress={onEdit} disabled={working} />
        <Action label="ביטול השמירה האחרונה" shortLabel="ביטול שמירה" icon="arrow-undo-outline" onPress={() => { void undo(); }} disabled={working} />
        {working ? <ActivityIndicator color={colors.accent} /> : null}
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
  rule: { gap: spacing.xs, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
  categoryPicker: { maxHeight: 160 },
  categoryChoices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: spacing.xs },
  action: { minHeight: 44, paddingHorizontal: spacing.sm, flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  disabled: { opacity: 0.45 },
});
