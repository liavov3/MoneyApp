// One recurring commitment ("מנוי חודשי"). Shows the day-of-month it recurs and
// the next expected charge. Projection only — the wording says "צפוי", never
// "חויב", because the backend does not auto-create a transaction.
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { categoryMeta } from '../../categories';
import { dayOfMonth, formatAmount, formatDateLong } from '../../format';
import { colors, font, radius, spacing, weight } from '../../theme';
import type { TemplateOut } from '../../types';
import { AppText } from '../ui';

export function RecurringCommitmentCard({
  template,
  categoryLabel,
  onPress,
}: {
  template: TemplateOut;
  categoryLabel: string;
  onPress: () => void;
}) {
  const meta = categoryMeta(template.category_key);
  const day = dayOfMonth(template.next_expected_date);
  const inactive = !template.is_active;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.85 : inactive ? 0.6 : 1 }]}
    >
      <View style={[styles.icon, { backgroundColor: meta.color + '26' }]}>
        <Ionicons name={meta.icon} size={20} color={meta.color} />
      </View>
      <View style={{ flex: 1 }}>
        <View style={styles.titleRow}>
          <AppText weight={weight.semibold} numberOfLines={1} style={{ flexShrink: 1 }}>
            {template.name}
          </AppText>
          <View style={[styles.badge, inactive ? styles.badgeOff : styles.badgeOn]}>
            <AppText size={font.micro} color={inactive ? colors.textMuted : colors.success}>
              {inactive ? 'לא פעיל' : 'פעיל'}
            </AppText>
          </View>
        </View>
        <AppText size={font.caption} color={colors.textSecondary}>
          {categoryLabel} · יורד בכל חודש ב־{day}
        </AppText>
        <AppText size={font.micro} color={colors.textMuted}>
          החיוב הבא: {formatDateLong(template.next_expected_date)}
        </AppText>
      </View>
      <AppText weight={weight.semibold}>{formatAmount(template.amount_minor, template.currency)}</AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.card,
    padding: spacing.md,
  },
  icon: { width: 42, height: 42, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  badge: { borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 2 },
  badgeOn: { backgroundColor: '#163a30' },
  badgeOff: { backgroundColor: colors.surfaceAlt },
});
