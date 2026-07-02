// Full-screen goal editor. Keyboard-safe: KAV wraps ScrollView (content) +
// a pinned footer View (Save button), so the button is always reachable above
// the keyboard. Explicit back button — no accidental tap-outside close.
import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError, deleteMonthlyGoal, getMonthlyGoals, putMonthlyGoal } from '../api';
import { AppText, Button, Input, Screen, SegmentedControl } from '../components/ui';
import { formatAmount, formatMonthLabel, minorToInput, shekelToMinor } from '../format';
import { colors, font, spacing, weight } from '../theme';
import type { GoalScope, GoalType, MonthlyGoalsResponse } from '../types';

export function GoalsScreen({
  month,
  onBack,
  onChanged,
}: {
  month: string;
  onBack: () => void;
  onChanged: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<MonthlyGoalsResponse | null>(null);
  const [goalType, setGoalType] = useState<GoalType>('expense');
  const [scope, setScope] = useState<GoalScope>('default');
  const [input, setInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try { setData(await getMonthlyGoals(month)); } catch {}
  }, [month]);

  useEffect(() => { load(); }, [load]);

  // Clear status flags when the user changes a selector (not on data refresh)
  useEffect(() => {
    setErrorMsg(null);
    setSaved(false);
  }, [goalType, scope]);

  // Prefill input from stored value whenever selector or fetched data changes
  useEffect(() => {
    const item = data?.items.find(i => i.goal_type === goalType) ?? null;
    if (!item) { setInput(''); return; }
    const v = scope === 'default' ? item.default_amount_minor : item.override_amount_minor;
    setInput(v != null ? minorToInput(v) : '');
  }, [goalType, scope, data]);

  const currentItem = data?.items.find(i => i.goal_type === goalType) ?? null;
  const hasOverride = currentItem?.override_amount_minor != null;
  const eff = currentItem?.effective_amount_minor ?? null;
  const effSrc = currentItem?.effective_source ?? null;
  const canSave = shekelToMinor(input) !== null && !saving;

  const onSave = async () => {
    const minor = shekelToMinor(input);
    if (minor === null) {
      setErrorMsg('הזן סכום חוקי (גדול מאפס).');
      return;
    }
    setSaving(true);
    setErrorMsg(null);
    try {
      await putMonthlyGoal({
        goal_type: goalType,
        scope,
        ...(scope === 'month_override' ? { month } : {}),
        amount_minor: minor,
      });
      await load(); // refresh so effective hint + prefill update
      setSaved(true);
      onChanged();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : undefined;
      setErrorMsg(
        code === 'invalid_amount'
          ? 'יש להזין סכום חוקי.'
          : 'השמירה נכשלה. בדוק את החיבור ונסה שוב.',
      );
    } finally {
      setSaving(false);
    }
  };

  const onRemoveOverride = async () => {
    try {
      await deleteMonthlyGoal({ goal_type: goalType, scope: 'month_override', month });
      await load();
      onChanged();
    } catch {
      setErrorMsg('לא ניתן היה להסיר את ההתאמה.');
    }
  };

  return (
    <Screen>
      {/* Header — mirrors SettingsScreen / RecurringScreen header */}
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={10} style={styles.iconBtn}>
          <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
        </Pressable>
        <AppText size={font.h1} weight={weight.bold}>
          יעדים חודשיים
        </AppText>
        <View style={styles.iconBtn} />
      </View>

      {/* KAV: pushes footer above the keyboard on iOS */}
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Month context + hint */}
          <AppText size={font.caption} color={colors.textSecondary}>
            {`החודש הנבחר: ${formatMonthLabel(month)}`}
          </AppText>
          <AppText size={font.caption} color={colors.textMuted} style={{ marginTop: -spacing.sm }}>
            ברירת מחדל חלה על כל החודשים. התאמה לחודש חלה רק על החודש שנבחר.
          </AppText>

          {/* Goal type */}
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
              סוג יעד
            </AppText>
            <SegmentedControl<GoalType>
              value={goalType}
              onChange={setGoalType}
              options={[
                { value: 'expense', label: 'הוצאות' },
                { value: 'income', label: 'הכנסה' },
                { value: 'savings', label: 'חיסכון' },
              ]}
            />
          </View>

          {/* Scope */}
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
              תחולה
            </AppText>
            <SegmentedControl<GoalScope>
              value={scope}
              onChange={setScope}
              options={[
                { value: 'default', label: 'לכל החודשים' },
                { value: 'month_override', label: 'רק לחודש זה' },
              ]}
            />
          </View>

          {/* Amount input */}
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
              סכום היעד (₪)
            </AppText>
            <Input
              iconLeft="flag-outline"
              keyboardType="decimal-pad"
              placeholder="0"
              value={input}
              onChangeText={setInput}
              onClear={() => setInput('')}
            />
          </View>

          {/* Effective hint for this month */}
          <AppText size={font.caption} color={colors.textSecondary}>
            {eff != null
              ? `בתוקף לחודש זה: ${formatAmount(eff)} · ${effSrc === 'month_override' ? 'מותאם לחודש' : 'ברירת מחדל'}`
              : 'לא הוגדר יעד לחודש זה'}
          </AppText>

          {/* Feedback */}
          {errorMsg ? (
            <AppText size={font.caption} color={colors.danger}>
              {errorMsg}
            </AppText>
          ) : null}
          {saved && !errorMsg ? (
            <AppText size={font.caption} color={colors.success}>
              נשמר
            </AppText>
          ) : null}

          {/* Remove override — only when scope is month_override and one exists */}
          {scope === 'month_override' && hasOverride ? (
            <Button
              title="הסר התאמה לחודש זה"
              variant="ghost"
              onPress={onRemoveOverride}
            />
          ) : null}
        </ScrollView>

        {/* Footer — pinned above keyboard, always reachable */}
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            title="שמירה"
            icon="checkmark"
            onPress={onSave}
            disabled={!canSave}
            loading={saving}
          />
        </View>
      </KeyboardAvoidingView>
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
  iconBtn: { padding: spacing.xs, minWidth: 32, alignItems: 'center' },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.lg,
  },
  label: { marginBottom: spacing.sm },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.bg,
  },
});
