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
import { AmountDisplay, AmountKeypad } from '../components/transactions/QuickAmountInput';
import { AppText, Button, Input } from '../components/ui';
import { formatAmount, todayISO } from '../format';
import { colors, font, radius, spacing, weight } from '../theme';
import type { MerchantSuggestion, RecentMerchant } from '../types';
import { useCategories } from '../useCategories';

export function QuickAddScreen({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const insets = useSafeAreaInsets();
  const { consumer } = useCategories();
  const [amount, setAmount] = useState('');
  const [merchant, setMerchant] = useState('');
  const [merchantFocused, setMerchantFocused] = useState(false);
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentMerchant[]>([]);
  const [suggestions, setSuggestions] = useState<MerchantSuggestion[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    setMerchantFocused(false);
    if (suggestedCategoryId && !categoryId) setCategoryId(suggestedCategoryId);
  };

  const amountValue = Number(amount);
  const canSave = amount !== '' && amountValue > 0 && !saving && !saved;

  const onSave = async () => {
    if (!canSave) return; // guards empty/zero + double-submit
    setSaving(true);
    setErrorMsg(null);
    try {
      const res = await quickAdd({
        amount,
        occurred_on: todayISO(),
        ...(merchant.trim() ? { merchant_input: merchant.trim() } : {}),
        ...(categoryId ? { category_id: categoryId } : {}),
      });
      void res;
      setSaved(true); // success overlay, then close
      setTimeout(onAdded, 650);
    } catch (e) {
      // Map the few known validation codes to friendly Hebrew; else generic.
      const code = e instanceof ApiError ? e.code : undefined;
      setErrorMsg(
        code === 'too_many_decimals'
          ? 'אפשר עד שתי ספרות אחרי הנקודה.'
          : code === 'zero_amount'
            ? 'יש להזין סכום גדול מאפס.'
            : 'שמירת ההוצאה נכשלה. בדוק את החיבור ונסה שוב.',
      );
      setSaving(false);
    }
  };

  const showRecent = merchant.trim().length < 2 && recent.length > 0;
  const showSuggest = merchant.trim().length >= 2 && suggestions.length > 0;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Pressable onPress={onClose} hitSlop={10} style={styles.close}>
          <Ionicons name="close" size={26} color={colors.textSecondary} />
        </Pressable>
        <AppText size={font.title} weight={weight.semibold}>
          הוצאה חדשה
        </AppText>
        <View style={styles.close} />
      </View>

      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <AmountDisplay value={amount} />

        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.details}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Merchant (optional) */}
          <Input
            iconLeft="storefront-outline"
            placeholder="בית עסק (לא חובה)"
            value={merchant}
            onChangeText={setMerchant}
            onFocus={() => setMerchantFocused(true)}
            onBlur={() => setMerchantFocused(false)}
            onClear={() => setMerchant('')}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="done"
          />
          {showRecent || showSuggest ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipRow}
              keyboardShouldPersistTaps="handled"
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

          {/* Category (optional) — horizontal, compact */}
          {consumer.length > 0 ? (
            <View style={styles.section}>
              <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
                קטגוריה (לא חובה)
              </AppText>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.chipRow}
                keyboardShouldPersistTaps="handled"
              >
                {consumer.map((c) => (
                  <CategoryChip
                    key={c.id}
                    categoryKey={c.key}
                    label={c.label_he ?? c.label_en}
                    selected={categoryId === c.id}
                    onPress={() => setCategoryId(categoryId === c.id ? null : c.id)}
                  />
                ))}
              </ScrollView>
            </View>
          ) : null}

          <View style={styles.dateRow}>
            <Ionicons name="calendar-outline" size={15} color={colors.textMuted} />
            <AppText size={font.caption} color={colors.textMuted}>
              היום
            </AppText>
          </View>

          {errorMsg ? (
            <View style={styles.errorBox}>
              <Ionicons name="alert-circle" size={16} color={colors.danger} />
              <AppText color={colors.danger} size={font.caption} style={{ flex: 1 }}>
                {errorMsg}
              </AppText>
            </View>
          ) : null}
        </ScrollView>

        {/* Keypad hides while the OS keyboard is up (merchant typing). */}
        {!merchantFocused ? <AmountKeypad value={amount} onChange={setAmount} /> : null}

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            title={canSave ? `שמירה · ${formatAmount(amountValue * 100)}` : 'שמירה'}
            icon="checkmark"
            onPress={onSave}
            disabled={!canSave}
            loading={saving}
          />
        </View>
      </KeyboardAvoidingView>

      {saved ? (
        <View style={styles.successOverlay} pointerEvents="none">
          <View style={styles.successCircle}>
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
  details: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  section: { marginTop: spacing.lg },
  chipRow: { gap: spacing.sm, paddingTop: spacing.md, paddingEnd: spacing.lg },
  dateRow: { flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', marginTop: spacing.lg },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: '#3a1f24',
    borderRadius: radius.input,
    padding: spacing.md,
    marginTop: spacing.lg,
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
    backgroundColor: colors.success,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
