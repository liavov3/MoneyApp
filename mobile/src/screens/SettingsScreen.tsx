import { Ionicons } from '@expo/vector-icons';
import React, { useSyncExternalStore } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { session } from '../session';
import { AppText, Button, Card, Screen } from '../components/ui';
import { colors, font, spacing, weight } from '../theme';
import appConfig from '../../app.json';

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
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
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
          פרטיות והתחברות
        </AppText>
        <Card>
          <Row label="החשבון האישי" value="מחובר" ok />
          <Button title="יציאה מהחשבון" variant="ghost" disabled={state.busy} loading={state.busy}
            onPress={() => { void session.disconnect(); }} style={{ marginTop: spacing.md }} />
          <AppText size={font.caption} color={colors.textMuted} style={{ marginTop: spacing.sm }}>
            היציאה מבטלת את ההתחברות במכשיר הזה. העסקאות שלך נשמרות בחשבון.
          </AppText>
          {state.error === 'logout' ? <AppText color={colors.danger} style={{ marginTop: spacing.sm }}>היציאה לא הושלמה. בדוק את החיבור לאינטרנט ונסה שוב.</AppText> : null}
        </Card>

        <AppText size={font.caption} color={colors.textMuted} style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>
          אודות
        </AppText>
        <Card>
          <Row label="גרסה" value={`MoneySaver ${appConfig.expo.version}`} />
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
