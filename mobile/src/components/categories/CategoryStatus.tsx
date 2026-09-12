import React from 'react';
import { View } from 'react-native';
import { useCategories } from '../../useCategories';
import { colors, font, spacing } from '../../theme';
import { AppText, Button } from '../ui';

export function CategoryStatus() {
  const { error, loading, reload } = useCategories();
  if (!error) return null;
  return (
    <View style={{ gap: spacing.sm, paddingVertical: spacing.sm }}>
      <AppText size={font.caption} color={colors.textSecondary}>לא הצלחנו לטעון את הקטגוריות.</AppText>
      <Button title="טעינת קטגוריות מחדש" variant="ghost" loading={loading} onPress={() => { void reload(); }} />
    </View>
  );
}
