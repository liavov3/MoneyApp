import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError, getMerchantSuggestions, getRecentMerchants, quickAdd } from '../api';
import { CategoryChip } from '../components/categories/CategoryChip';
import { MerchantSuggestionChip } from '../components/merchants/MerchantSuggestionChip';
import { AppText, Button, Input, SegmentedControl } from '../components/ui';
import { DatePicker } from '../components/ui/DatePicker';
import { formatDateLong, todayISO } from '../format';
import { colors, font, radius, spacing, weight } from '../theme';
import type { MerchantSuggestion, RecentMerchant } from '../types';
import { useCategories } from '../useCategories';

type TxnType = 'expense' | 'income';
// Common income sources — tapped into the name field (becomes merchant_input).
const INCOME_SOURCES = ['משכורת', 'החזר', 'מתנה', 'עבודה', 'בונוס'];

export function QuickAddScreen({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const insets = useSafeAreaInsets();
  const { consumer } = useCategories();
  const [txnType, setTxnType] = useState<TxnType>('expense');
  const [amount, setAmount] = useState('');
  const [merchant, setMerchant] = useState('');
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [occurredOn, setOccurredOn] = useState(todayISO());
  const [dateOpen, setDateOpen] = useState(false);
  const [recent, setRecent] = useState<RecentMerchant[]>([]);
  const [suggestions, setSuggestions] = useState<MerchantSuggestion[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isIncome = txnType === 'income';

  useEffect(() => {
    getRecentMerchants(8)
      .then((r) => setRecent(r.items))
      .catch(() => {});
  }, []);

  // Live merchant suggestions (debounced). Backend owns matching — no local fuzzy.
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    const q = merchant.trim();
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    debounce.current = setTimeout(() => {
      getMerchantSuggestions(q, 6)
        .then((r) => setSuggestions(r.items))
        .catch(() => setSuggestions([]));
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [merchant]);

  const pickMerchant = (name: string, suggestedCategoryId: string | null) => {
    setMerchant(name);
    setSuggestions([]);
    if (!isIncome && suggestedCategoryId && !categoryId) setCategoryId(suggestedCategoryId);
  };

  const amountValue = Number(amount);
  const canSave = amount !== '' && amountValue > 0 && !saving && !saved;

  const onSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      // Amount is always a non-negative magnitude; the SERVER applies the sign
      // from transaction_type (expense → negative, income → positive). §14.
      await quickAdd({
        amount,
        transaction_type: txnType,
        occurred_on: occurredOn,
        ...(merchant.trim() ? { merchant_input: merchant.trim() } : {}),
        ...(!isIncome && categoryId ? { category_id: categoryId } : {}),
      });
      setSaved(true);
      setTimeout(onAdded, 650);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : undefined;
      setErrorMsg(
        code === 'too_many_decimals'
          ? 'אפשר עד שתי ספרות אחרי הנקודה.'
          : code === 'zero_amount'
            ? 'יש להזין סכום גדול מאפס.'
            : 'השמירה נכשלה. בדוק את החיבור ונסה שוב.',
      );
      setSaving(false);
    }
  };

  const showRecent = !isIncome && merchant.trim().length < 2 && recent.length > 0;
  const showSuggest = !isIncome && merchant.trim().length >= 2 && suggestions.length > 0;
  const tint = isIncome ? colors.success : colors.accent;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      {/* [A] Header */}
      <View style={styles.header}>
        <Pressable onPress={onClose} hitSlop={10} style={styles.close}>
          <Ionicons name="close" size={26} color={colors.textSecondary} />
        </Pressable>
        <AppText size={font.title} weight={weight.semibold}>
          {isIncome ? 'הכנסה חדשה' : 'הוצאה חדשה'}
        </AppText>
        <View style={styles.close} />
      </View>

      {/* [B] KeyboardAvoidingView */}
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {/* [B1] Type toggle */}
        <View style={styles.toggle}>
          <SegmentedControl<TxnType>
            value={txnType}
            onChange={(v) => {
              setTxnType(v);
              if (v === 'income') setCategoryId(null);
            }}
            tint={tint}
            options={[
              { value: 'expense', label: 'הוצאה', icon: 'arrow-down' },
              { value: 'income', label: 'הכנסה', icon: 'arrow-up' },
            ]}
          />
        </View>

        {/* [B2] Scroll form */}
        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* [B2-1] Merchant block */}
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
              {isIncome ? 'מקור הכנסה' : 'בית עסק'}
            </AppText>
            <Input
              iconLeft={isIncome ? 'cash-outline' : 'storefront-outline'}
              placeholder={isIncome ? 'מקור ההכנסה (לא חובה)' : 'בית עסק (לא חובה)'}
              value={merchant}
              onChangeText={setMerchant}
              onClear={() => setMerchant('')}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="done"
            />
          </View>

          {/* [B2-2] Merchant chips / suggestions */}
          {isIncome ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipRow}
              keyboardShouldPersistTaps="handled"
              style={{ marginTop: -spacing.sm }}
            >
              {INCOME_SOURCES.map((s) => (
                <MerchantSuggestionChip key={s} label={s} onPress={() => pickMerchant(s, null)} />
              ))}
            </ScrollView>
          ) : showRecent || showSuggest ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipRow}
              keyboardShouldPersistTaps="handled"
              style={{ marginTop: -spacing.sm }}
            >
              {showSuggest
                ? suggestions.map((s) => (
                    <MerchantSuggestionChip
                      key={s.merchant_id}
                      label={s.display_name}
                      onPress={() => pickMerchant(s.display_name, s.suggested_category_id)}
                    />
                  ))
                : recent.map((m) => (
                    <MerchantSuggestionChip
                      key={m.merchant_id}
                      label={m.display_name}
                      recent
                      onPress={() => pickMerchant(m.display_name, m.suggested_category_id)}
                    />
                  ))}
            </ScrollView>
          ) : null}

          {/* [B2-3] Amount block */}
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
              סכום
            </AppText>
            <Input
              iconLeft="cash-outline"
              placeholder="0"
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              returnKeyType="done"
              onClear={() => setAmount('')}
            />
          </View>

          {/* [B2-4] Category block — wrap layout, expense only */}
          {!isIncome && consumer.length > 0 ? (
            <View>
              <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
                קטגוריה (לא חובה)
              </AppText>
              <View style={styles.categoryWrap}>
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

          {/* [B2-5] Date block */}
          <View>
            <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
              תאריך
            </AppText>
            <Pressable onPress={() => setDateOpen(true)} hitSlop={8} style={styles.datePressable}>
              <Ionicons name="chevron-down" size={13} color={colors.textMuted} />
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <AppText
                  size={font.body}
                  color={occurredOn === todayISO() ? colors.textSecondary : colors.textPrimary}
                >
                  {occurredOn === todayISO() ? 'היום' : formatDateLong(occurredOn)}
                </AppText>
                <Ionicons name="calendar-outline" size={15} color={colors.textMuted} />
              </View>
            </Pressable>
          </View>

          {/* [B2-6] Error box */}
          {errorMsg ? (
            <View style={styles.errorBox}>
              <Ionicons name="alert-circle" size={16} color={colors.danger} />
              <AppText color={colors.danger} size={font.caption} style={{ flex: 1 }}>
                {errorMsg}
              </AppText>
            </View>
          ) : null}
        </ScrollView>

        {/* [B3] Footer */}
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            title="הוספה"
            icon="checkmark"
            onPress={onSave}
            disabled={!canSave}
            loading={saving}
            style={isIncome ? { backgroundColor: colors.success } : undefined}
          />
        </View>
      </KeyboardAvoidingView>

      {/* [C] DatePicker */}
      <DatePicker
        visible={dateOpen}
        value={occurredOn}
        onChange={setOccurredOn}
        onClose={() => setDateOpen(false)}
      />

      {/* [D] Success overlay */}
      {saved ? (
        <View style={styles.successOverlay} pointerEvents="none">
          <View style={[styles.successCircle, { backgroundColor: tint }]}>
            <Ionicons name="checkmark" size={42} color={colors.onAccent} />
          </View>
          <AppText size={font.title} weight={weight.semibold} style={{ marginTop: spacing.md }}>
            נשמר
          </AppText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  close: { width: 32, alignItems: 'center' },
  toggle: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.lg,
  },
  chipRow: { gap: spacing.sm, paddingEnd: spacing.lg },
  categoryWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  datePressable: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
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
  footer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.bg,
  },
  successOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(11,14,19,0.92)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  successCircle: {
    width: 84,
    height: 84,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
