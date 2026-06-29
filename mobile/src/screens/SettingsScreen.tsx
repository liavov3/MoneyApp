import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { apiBaseUrl, hasToken } from '../api';
import { AppText, Card, Screen } from '../components/ui';
import { colors, font, spacing, weight } from '../theme';

function Row({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <View style={styles.row}>
      <AppText color={colors.textSecondary}>{label}</AppText>
      <View style={styles.valueWrap}>
        {ok !== undefined ? (
          <Ionicons
            name={ok ? 'checkmark-circle' : 'alert-circle'}
            size={16}
            color={ok ? colors.success : colors.warning}
          />
        ) : null}
        <AppText weight={weight.medium} numberOfLines={1}>
          {value}
        </AppText>
      </View>
    </View>
  );
}

export function SettingsScreen({ onBack }: { onBack: () => void }) {
  return (
    <Screen>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={10} style={{ padding: spacing.xs }}>
          <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
        </Pressable>
        <AppText size={font.h1} weight={weight.bold}>
          הגדרות
        </AppText>
        <View style={{ width: 32 }} />
      </View>

      <View style={styles.content}>
        <AppText size={font.caption} color={colors.textMuted} style={{ marginBottom: spacing.sm }}>
          חיבור
        </AppText>
        <Card>
          <Row label="כתובת שרת" value={apiBaseUrl} />
          <View style={styles.divider} />
          <Row label="אימות פיתוח" value={hasToken ? 'מחובר' : 'לא מוגדר אסימון'} ok={hasToken} />
        </Card>

        <AppText size={font.caption} color={colors.textMuted} style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>
          אודות
        </AppText>
        <Card>
          <Row label="גרסה" value="MoneySaver 0.0.1" />
          <View style={styles.divider} />
          <Row label="Expo SDK" value="54" />
        </Card>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  content: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: spacing.sm },
  valueWrap: { flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 1 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.xs },
});
