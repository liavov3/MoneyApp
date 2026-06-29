import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { categoryMeta } from '../../categories';
import { formatAmount } from '../../format';
import { colors, font, radius, spacing, weight } from '../../theme';
import type { TransactionOut } from '../../types';
import { AppText } from '../ui';

// `label` is the Hebrew category label resolved by the caller (from /categories).
export function TransactionListItem({
  txn,
  label,
  onPress,
}: {
  txn: TransactionOut;
  label: string | null;
  onPress?: () => void;
}) {
  const meta = categoryMeta(txn.category_key);
  const uncategorized = txn.category_id === null;
  const title = txn.merchant_display_name ?? label ?? 'ללא קטגוריה';
  // Secondary line: category when the title is a merchant; "לא מקוטלג" hint otherwise.
  const subtitle = txn.merchant_display_name
    ? label ?? (uncategorized ? 'ללא קטגוריה' : '')
    : uncategorized
      ? 'לא מקוטלג'
      : '';
  const income = txn.transaction_type === 'income' || txn.transaction_type === 'refund';
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.row, { opacity: pressed ? 0.7 : 1 }]}
    >
      <View style={[styles.icon, { backgroundColor: meta.color + '26' }]}>
        <Ionicons name={meta.icon} size={20} color={meta.color} />
      </View>
      <View style={{ flex: 1 }}>
        <AppText weight={weight.medium} numberOfLines={1}>
          {title}
        </AppText>
        {subtitle ? (
          <AppText size={font.caption} color={colors.textMuted} numberOfLines={1}>
            {subtitle}
          </AppText>
        ) : null}
      </View>
      <AppText weight={weight.semibold} color={income ? colors.success : colors.textPrimary}>
        {income ? '+' : ''}
        {formatAmount(txn.amount_minor, txn.currency)}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  icon: { width: 42, height: 42, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
});
