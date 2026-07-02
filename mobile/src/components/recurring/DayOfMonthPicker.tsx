// Day-of-month chooser for a monthly recurring commitment (1–31). A simple wrap
// grid of tappable numbers — clearer than a full calendar for "יורד בכל חודש ב־X".
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { colors, font, radius, weight } from '../../theme';
import { AppText } from '../ui';

export function DayOfMonthPicker({
  value,
  onChange,
}: {
  value: number;
  onChange: (day: number) => void;
}) {
  return (
    <View style={styles.grid}>
      {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => {
        const selected = d === value;
        return (
          <Pressable key={d} onPress={() => onChange(d)} style={styles.cell}>
            <View style={[styles.day, selected && styles.daySelected]}>
              <AppText
                align="center"
                size={font.caption}
                color={selected ? colors.onAccent : colors.textPrimary}
                weight={selected ? weight.semibold : weight.regular}
              >
                {d}
              </AppText>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: { width: `${100 / 7}%`, alignItems: 'center', paddingVertical: 4 },
  day: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceAlt,
  },
  daySelected: { backgroundColor: colors.accent },
});
