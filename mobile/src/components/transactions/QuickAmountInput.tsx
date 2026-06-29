// Amount-first input, split into a top display + a bottom custom keypad so the
// keypad sits in thumb reach and can hide while the OS keyboard is up (merchant
// typing). A custom keypad keeps tap targets large and never hides Save.
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, font, radius, spacing, weight } from '../../theme';

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', 'del'] as const;

// Append a key to the raw amount string, enforcing ≤2 decimals + one dot.
export function applyKey(value: string, key: string): string {
  if (key === 'del') return value.slice(0, -1);
  if (key === '.') return value.includes('.') ? value : value === '' ? '0.' : value + '.';
  if (value.includes('.')) {
    const [, dec] = value.split('.');
    if (dec.length >= 2) return value; // max 2 decimals
  }
  if (value === '0') return key; // no leading zero
  if (value.replace('.', '').length >= 9) return value; // sane upper bound
  return value + key;
}

export function AmountDisplay({ value }: { value: string }) {
  const empty = value === '' || value === '.';
  return (
    <View style={styles.display}>
      <Text style={styles.label}>סכום</Text>
      <View style={styles.amountWrap}>
        <Text style={styles.currency}>₪</Text>
        <Text
          style={[styles.amount, { color: empty ? colors.textMuted : colors.textPrimary }]}
          adjustsFontSizeToFit
          numberOfLines={1}
        >
          {empty ? '0' : value}
        </Text>
      </View>
    </View>
  );
}

export function AmountKeypad({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <View style={styles.pad}>
      {KEYS.map((k) => (
        <View key={k} style={styles.keyCell}>
          <Pressable
            onPress={() => onChange(applyKey(value, k))}
            style={({ pressed }) => [styles.key, pressed && styles.keyPressed]}
          >
            {k === 'del' ? (
              <Ionicons name="backspace-outline" size={26} color={colors.textPrimary} />
            ) : (
              <Text style={styles.keyText}>{k}</Text>
            )}
          </Pressable>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  display: { paddingVertical: spacing.sm },
  label: { color: colors.textSecondary, fontSize: font.caption, textAlign: 'center' },
  amountWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: spacing.sm,
  },
  currency: { color: colors.textSecondary, fontSize: font.h1, fontWeight: weight.semibold },
  amount: { fontSize: 52, fontWeight: weight.bold, textAlign: 'center', minWidth: 80 },
  pad: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: spacing.sm },
  keyCell: { width: '33.33%', padding: 4 },
  key: { height: 56, alignItems: 'center', justifyContent: 'center', borderRadius: radius.input },
  keyPressed: { backgroundColor: colors.surfaceAlt },
  keyText: { color: colors.textPrimary, fontSize: font.h1, fontWeight: weight.medium, textAlign: 'center' },
});
