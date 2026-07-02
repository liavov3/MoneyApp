// Hamburger menu — four destinations surfaced via BottomSheet. RTL: chevron-back
// sits on the leading (right) end, pointing left = "navigate there".
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { colors, font, spacing, weight } from '../../theme';
import { AppText, BottomSheet } from './index';

type Row = {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
};

export function MenuSheet({
  visible,
  onClose,
  onHome,
  onRecurring,
  onGoal,
  onSettings,
}: {
  visible: boolean;
  onClose: () => void;
  onHome: () => void;
  onRecurring: () => void;
  onGoal: () => void;
  onSettings: () => void;
}) {
  const rows: Row[] = [
    { label: 'בית', icon: 'home-outline', onPress: onHome },
    { label: 'הגדרת הוצאה קבועה', icon: 'repeat', onPress: onRecurring },
    { label: 'יעד חודשי', icon: 'flag-outline', onPress: onGoal },
    { label: 'הגדרות', icon: 'settings-outline', onPress: onSettings },
  ];

  return (
    <BottomSheet visible={visible} onClose={onClose} title="תפריט">
      <View style={styles.list}>
        {rows.map((row, i) => (
          <View key={row.label}>
            {i > 0 ? <View style={styles.divider} /> : null}
            <Pressable
              onPress={() => { onClose(); row.onPress(); }}
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
              hitSlop={4}
            >
              <View style={styles.rowStart}>
                <Ionicons name={row.icon} size={20} color={colors.textSecondary} />
                <AppText size={font.body} weight={weight.medium}>
                  {row.label}
                </AppText>
              </View>
              <Ionicons name="chevron-back" size={16} color={colors.textMuted} />
            </Pressable>
          </View>
        ))}
      </View>
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: spacing.md },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
  },
  rowPressed: { opacity: 0.6 },
  rowStart: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  divider: { height: 1, backgroundColor: colors.border },
});
