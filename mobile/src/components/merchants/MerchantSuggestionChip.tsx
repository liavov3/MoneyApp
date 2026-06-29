import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet } from 'react-native';

import { colors, font, radius, spacing } from '../../theme';
import { AppText } from '../ui';

export function MerchantSuggestionChip({
  label,
  onPress,
  recent,
}: {
  label: string;
  onPress: () => void;
  recent?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.chip, { opacity: pressed ? 0.85 : 1 }]}
    >
      {recent ? <Ionicons name="time-outline" size={14} color={colors.textMuted} /> : null}
      <AppText size={font.body} numberOfLines={1}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
});
