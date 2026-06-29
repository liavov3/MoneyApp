import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { categoryMeta } from '../../categories';
import { colors, font, radius, spacing, weight } from '../../theme';
import { AppText } from '../ui';

export function CategoryChip({
  categoryKey,
  label,
  selected,
  onPress,
}: {
  categoryKey: string | null;
  label: string;
  selected?: boolean;
  onPress: () => void;
}) {
  const meta = categoryMeta(categoryKey);
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        {
          backgroundColor: selected ? colors.accentSoft : colors.surface,
          borderColor: selected ? colors.accent : colors.border,
          opacity: pressed ? 0.85 : 1,
        },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: meta.color + '33' }]}>
        <Ionicons name={meta.icon} size={16} color={meta.color} />
      </View>
      <AppText size={font.body} weight={selected ? weight.semibold : weight.regular}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  dot: { width: 26, height: 26, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
});
