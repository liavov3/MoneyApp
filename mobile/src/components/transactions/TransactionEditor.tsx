// Edit / delete a transaction in a bottom sheet. Loads the row by id, edits
// amount, type, category, date, note, and saves via PATCH. Merchant is shown
// read-only — the backend's PATCH does not accept merchant changes (§9).
import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';

import {
  ApiError,
  deleteTransaction,
  getTransaction,
  patchTransaction,
} from '../../api';
import { formatDateLong, todayISO } from '../../format';
import { colors, font, radius, spacing, weight } from '../../theme';
import type { PatchTransactionInput, TransactionOut } from '../../types';
import { useCategories } from '../../useCategories';
import { CategoryChip } from '../categories/CategoryChip';
import {
  AppText,
  BottomSheet,
  Button,
  Input,
  LoadingState,
  SegmentedControl,
} from '../ui';
import { DatePicker } from '../ui/DatePicker';

type Bucket = 'expense' | 'income';
const bucketOf = (t: string): Bucket => (t === 'income' || t === 'refund' ? 'income' : 'expense');
const magnitude = (minor: number): string => String(Math.abs(minor) / 100);

export function TransactionEditor({
  txnId,
  visible,
  onClose,
  onSaved,
  onDeleted,
}: {
  txnId: string | null;
  visible: boolean;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const { consumer } = useCategories();
  const [txn, setTxn] = useState<TransactionOut | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [amount, setAmount] = useState('');
  const [bucket, setBucket] = useState<Bucket>('expense');
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [occurredOn, setOccurredOn] = useState(todayISO());
  const [note, setNote] = useState('');
  const [dateOpen, setDateOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || !txnId) return;
    setTxn(null);
    setLoadError(false);
    setErrorMsg(null);
    getTransaction(txnId)
      .then((t) => {
        setTxn(t);
        setAmount(magnitude(t.amount_minor));
        setBucket(bucketOf(t.transaction_type));
        setCategoryId(t.category_id);
        setOccurredOn(t.occurred_on);
        setNote(t.note ?? '');
      })
      .catch(() => setLoadError(true));
  }, [visible, txnId]);

  const isIncome = bucket === 'income';
  const amountValue = Number(amount);
  const canSave = !!txn && amount !== '' && amountValue > 0 && !saving;

  const onSave = async () => {
    if (!canSave || !txn) return; // guards empty/zero + double-submit
    setSaving(true);
    setErrorMsg(null);
    const patch: PatchTransactionInput = {
      amount,
      occurred_on: occurredOn,
      note: note.trim() ? note.trim() : null,
      // Income carries no spending category; expense keeps/clears its own.
      category_id: isIncome ? null : categoryId,
    };
    // Only re-sign when the user actually flipped the type bucket (keeps an
    // original refund/adjustment intact if untouched).
    if (bucket !== bucketOf(txn.transaction_type)) patch.transaction_type = bucket;
    try {
      await patchTransaction(txn.id, patch);
      onSaved();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : undefined;
      setErrorMsg(
        code === 'too_many_decimals'
          ? 'אפשר עד שתי ספרות אחרי הנקודה.'
          : code === 'zero_amount'
            ? 'יש להזין סכום גדול מאפס.'
            : 'העדכון נכשל. בדוק את החיבור ונסה שוב.',
      );
      setSaving(false);
    }
  };

  const onDelete = () => {
    if (!txn) return;
    Alert.alert('מחיקת עסקה', 'למחוק את העסקה? פעולה זו אינה הפיכה.', [
      { text: 'ביטול', style: 'cancel' },
      {
        text: 'מחיקה',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteTransaction(txn.id);
            onDeleted();
          } catch {
            Alert.alert('שגיאה', 'מחיקת העסקה נכשלה. נסה שוב.');
          }
        },
      },
    ]);
  };

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title="עריכת עסקה"
      dismissOnBackdropPress={false}
    >
      {loadError ? (
        <View style={styles.center}>
          <AppText color={colors.textSecondary}>לא הצלחנו לטעון את העסקה.</AppText>
        </View>
      ) : !txn ? (
        <View style={styles.center}>
          <LoadingState />
        </View>
      ) : (
        <View style={{ gap: spacing.lg, paddingBottom: spacing.md }}>
          <SegmentedControl<Bucket>
            value={bucket}
            onChange={setBucket}
            tint={isIncome ? colors.success : colors.accent}
            options={[
              { value: 'expense', label: 'הוצאה', icon: 'arrow-down' },
              { value: 'income', label: 'הכנסה', icon: 'arrow-up' },
            ]}
          />

          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
              סכום
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

          {/* Merchant is read-only: PATCH does not change it (§9). */}
          {txn.merchant_display_name ? (
            <View style={styles.readonlyRow}>
              <Ionicons name="storefront-outline" size={16} color={colors.textMuted} />
              <AppText color={colors.textSecondary} style={{ flex: 1 }} numberOfLines={1}>
                {txn.merchant_display_name}
              </AppText>
              <AppText size={font.micro} color={colors.textMuted}>
                בית עסק קבוע
              </AppText>
            </View>
          ) : null}

          {!isIncome && consumer.length > 0 ? (
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
                    onPress={() => setCategoryId(categoryId === c.id ? null : c.id)}
                  />
                ))}
              </View>
            </View>
          ) : null}

          <Pressable style={styles.dateRow} onPress={() => setDateOpen(true)}>
            <Ionicons name="calendar-outline" size={16} color={colors.textMuted} />
            <AppText color={colors.textSecondary} style={{ flex: 1 }}>
              {occurredOn === todayISO() ? 'היום' : formatDateLong(occurredOn)}
            </AppText>
            <Ionicons name="chevron-down" size={14} color={colors.textMuted} />
          </Pressable>

          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={styles.label}>
              הערה (לא חובה)
            </AppText>
            <Input
              iconLeft="create-outline"
              value={note}
              onChangeText={setNote}
              placeholder="הוסף הערה"
              onClear={() => setNote('')}
            />
          </View>

          {errorMsg ? (
            <View style={styles.errorBox}>
              <Ionicons name="alert-circle" size={16} color={colors.danger} />
              <AppText color={colors.danger} size={font.caption} style={{ flex: 1 }}>
                {errorMsg}
              </AppText>
            </View>
          ) : null}

          <Button
            title="שמירת שינויים"
            icon="checkmark"
            onPress={onSave}
            disabled={!canSave}
            loading={saving}
            style={isIncome ? { backgroundColor: colors.success } : undefined}
          />
          <Button title="מחיקת עסקה" icon="trash-outline" variant="destructive" onPress={onDelete} />
        </View>
      )}

      <DatePicker
        visible={dateOpen}
        value={occurredOn}
        onChange={setOccurredOn}
        onClose={() => setDateOpen(false)}
      />
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  center: { paddingVertical: spacing.xxl, alignItems: 'center', minHeight: 160, justifyContent: 'center' },
  label: { marginBottom: spacing.sm },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  readonlyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.input,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  dateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.input,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
  },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: '#3a1f24',
    borderRadius: radius.input,
    padding: spacing.md,
  },
});
