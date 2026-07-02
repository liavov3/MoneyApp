// Pure-JS month-grid date picker (no native module → works in Expo Go). Used
// for a transaction's occurred_on. Future days are disabled (the backend rejects
// a future occurred_on). RTL: weekday columns read right-to-left naturally.
import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { formatMonthLabel, todayISO } from '../../format';
import { colors, font, radius, spacing, weight } from '../../theme';
import { AppText, BottomSheet } from './index';

const WEEKDAYS = ['א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ש'];

function iso(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export function DatePicker({
  visible,
  value,
  onChange,
  onClose,
  allowFuture = false,
}: {
  visible: boolean;
  value: string; // YYYY-MM-DD
  onChange: (iso: string) => void;
  onClose: () => void;
  allowFuture?: boolean;
}) {
  const [vy, vm] = value.split('-').map(Number);
  const [view, setView] = useState({ y: vy, m: vm - 1 });
  const today = todayISO();

  const first = new Date(view.y, view.m, 1).getDay();
  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(first).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <BottomSheet visible={visible} onClose={onClose} title="בחירת תאריך">
      <View style={styles.nav}>
        <Pressable onPress={() => setView((v) => ({ ...v, ...shift(v, -1) }))} hitSlop={10}>
          <Ionicons name="chevron-forward" size={22} color={colors.textSecondary} />
        </Pressable>
        <AppText weight={weight.semibold}>{formatMonthLabel(iso(view.y, view.m, 1).slice(0, 7))}</AppText>
        <Pressable onPress={() => setView((v) => ({ ...v, ...shift(v, 1) }))} hitSlop={10}>
          <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
        </Pressable>
      </View>

      <View style={styles.grid}>
        {WEEKDAYS.map((w) => (
          <View key={w} style={styles.cell}>
            <AppText size={font.micro} color={colors.textMuted} align="center">
              {w}
            </AppText>
          </View>
        ))}
        {cells.map((d, i) => {
          if (d === null) return <View key={`e${i}`} style={styles.cell} />;
          const cellIso = iso(view.y, view.m, d);
          const selected = cellIso === value;
          const disabled = !allowFuture && cellIso > today;
          return (
            <Pressable
              key={cellIso}
              style={styles.cell}
              disabled={disabled}
              onPress={() => {
                onChange(cellIso);
                onClose();
              }}
            >
              <View style={[styles.day, selected && styles.daySelected]}>
                <AppText
                  align="center"
                  color={selected ? colors.onAccent : disabled ? colors.textMuted : colors.textPrimary}
                  weight={selected ? weight.semibold : weight.regular}
                >
                  {d}
                </AppText>
              </View>
            </Pressable>
          );
        })}
      </View>
    </BottomSheet>
  );
}

function shift(v: { y: number; m: number }, delta: number): { y: number; m: number } {
  const d = new Date(v.y, v.m + delta, 1);
  return { y: d.getFullYear(), m: d.getMonth() };
}

const styles = StyleSheet.create({
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', paddingBottom: spacing.md },
  cell: { width: `${100 / 7}%`, alignItems: 'center', paddingVertical: 4 },
  day: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  daySelected: { backgroundColor: colors.accent },
});
