// Month context control shared by Home + Transactions. Under forced RTL the
// first row child renders on the RIGHT, so the "previous" arrow (right-pointing)
// sits on the right — the Hebrew-natural "older is to the right" direction.
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { addMonths, currentMonth, formatMonthLabel } from '../../format';
import { colors, font, radius, spacing, weight } from '../../theme';
import { AppText } from './index';

export function MonthSwitcher({
  month,
  onChange,
}: {
  month: string;
  onChange: (next: string) => void;
}) {
  const isCurrent = month === currentMonth();
  return (
    <View style={styles.row}>
      <Pressable
        onPress={() => onChange(addMonths(month, -1))}
        hitSlop={10}
        style={styles.arrow}
      >
        <Ionicons name="chevron-forward" size={22} color={colors.textSecondary} />
      </Pressable>

      <Pressable
        onPress={() => !isCurrent && onChange(currentMonth())}
        style={styles.label}
        disabled={isCurrent}
      >
        <AppText size={font.title} weight={weight.semibold}>
          {formatMonthLabel(month)}
        </AppText>
        {!isCurrent ? (
          <AppText size={font.micro} color={colors.accent}>
            חזרה לחודש הנוכחי
          </AppText>
        ) : null}
      </Pressable>

      <Pressable
        onPress={() => onChange(addMonths(month, 1))}
        hitSlop={10}
        style={styles.arrow}
      >
        <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.input,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  arrow: { padding: spacing.sm },
  label: { flex: 1, alignItems: 'center' },
});
