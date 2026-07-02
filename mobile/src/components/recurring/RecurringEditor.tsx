// Add / edit a monthly recurring commitment in a bottom sheet. Cadence is fixed
// to monthly in this slice (weekly/yearly are backend-supported but not yet
// exposed). The chosen day-of-month becomes next_expected_date via nextDateForDay.
import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { Alert, StyleSheet, View } from 'react-native';

import { ApiError, createRecurring, deleteRecurring, patchRecurring } from '../../api';
import { dayOfMonth, nextDateForDay } from '../../format';
import { colors, font, spacing, weight } from '../../theme';
import type { TemplateOut } from '../../types';
import { useCategories } from '../../useCategories';
import { CategoryChip } from '../categories/CategoryChip';
import { AppText, BottomSheet, Button, Input, SegmentedControl } from '../ui';
import { DayOfMonthPicker } from './DayOfMonthPicker';

export function RecurringEditor({
  template,
  visible,
  onClose,
  onSaved,
  onDeleted,
}: {
  template: TemplateOut | null; // null = create
  visible: boolean;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const { consumer } = useCategories();
  const editing = !!template;
  const [name, setName] = useState('');
  const [amount, setAmount] = useState('');
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [day, setDay] = useState(1);
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setErrorMsg(null);
    setSaving(false);
    if (template) {
      setName(template.name);
      setAmount(String(Math.abs(template.amount_minor) / 100));
      setCategoryId(template.category_id);
      setDay(dayOfMonth(template.next_expected_date));
      setActive(template.is_active);
    } else {
      setName('');
      setAmount('');
      setCategoryId(null);
      setDay(new Date().getDate());
      setActive(true);
    }
  }, [visible, template]);

  const amountValue = Number(amount);
  const canSave = name.trim() !== '' && amount !== '' && amountValue > 0 && !!categoryId && !saving;

  const onSave = async () => {
    if (!canSave || !categoryId) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      if (template) {
        await patchRecurring(template.id, {
          name: name.trim(),
          amount,
          category_id: categoryId,
          next_expected_date: nextDateForDay(day),
          is_active: active,
        });
      } else {
        await createRecurring({
          name: name.trim(),
          amount,
          category_id: categoryId,
          cadence: 'monthly',
          next_expected_date: nextDateForDay(day),
          counts_in_projection: true,
        });
      }
      onSaved();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : undefined;
      setErrorMsg(
        code === 'too_many_decimals'
          ? 'אפשר עד שתי ספרות אחרי הנקודה.'
          : 'השמירה נכשלה. בדוק את החיבור ונסה שוב.',
      );
      setSaving(false);
    }
  };

  const onDelete = () => {
    if (!template) return;
    Alert.alert('מחיקת הוצאה קבועה', 'למחוק את ההתחייבות החודשית?', [
      { text: 'ביטול', style: 'cancel' },
      {
        text: 'מחיקה',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteRecurring(template.id);
            onDeleted();
          } catch {
            Alert.alert('שגיאה', 'המחיקה נכשלה. נסה שוב.');
          }
        },
      },
    ]);
  };

  return (
    <BottomSheet visible={visible} onClose={onClose} title={editing ? 'עריכת הוצאה קבועה' : 'הוצאה קבועה חדשה'}>
      <View style={{ gap: spacing.lg, paddingBottom: spacing.md }}>
        <View>
          <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
            שם המנוי
          </AppText>
          <Input
            iconLeft="repeat"
            value={name}
            onChangeText={setName}
            placeholder="לדוגמה: Netflix, חדר כושר"
            onClear={() => setName('')}
          />
        </View>

        <View>
          <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
            סכום חודשי
          </AppText>
          <Input
            iconLeft="cash-outline"
            value={amount}
            onChangeText={setAmount}
            keyboardType="decimal-pad"
            placeholder="0"
            onClear={() => setAmount('')}
          />
        </View>

        <View>
          <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
            קטגוריה
          </AppText>
          <View style={styles.chipWrap}>
            {consumer.map((c) => (
              <CategoryChip
                key={c.id}
                categoryKey={c.key}
                label={c.label_he ?? c.label_en}
                selected={categoryId === c.id}
                onPress={() => setCategoryId(c.id)}
              />
            ))}
          </View>
        </View>

        <View>
          <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
            יורד בכל חודש ביום
          </AppText>
          <DayOfMonthPicker value={day} onChange={setDay} />
        </View>

        {editing ? (
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
              סטטוס
            </AppText>
            <SegmentedControl<'on' | 'off'>
              value={active ? 'on' : 'off'}
              onChange={(v) => setActive(v === 'on')}
              options={[
                { value: 'on', label: 'פעיל' },
                { value: 'off', label: 'לא פעיל' },
              ]}
            />
          </View>
        ) : null}

        {errorMsg ? (
          <AppText color={colors.danger} size={font.caption}>
            {errorMsg}
          </AppText>
        ) : null}

        <Button
          title={editing ? 'שמירת שינויים' : 'הוספת הוצאה קבועה'}
          icon="checkmark"
          onPress={onSave}
          disabled={!canSave}
          loading={saving}
        />
        {editing ? (
          <Button title="מחיקה" icon="trash-outline" variant="destructive" onPress={onDelete} />
        ) : null}
      </View>
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  label: { marginBottom: spacing.sm },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
