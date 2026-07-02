import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { getHome, getMonthlyGoals, listTransactions } from '../api';
import { categoryMeta } from '../categories';
import { MonthSwitcher } from '../components/ui/MonthSwitcher';
import { AppText, Card, EmptyState, ErrorState, Screen, Skeleton } from '../components/ui';
import { dayOfMonth, formatAmount, formatDateLong } from '../format';
import { colors, font, radius, spacing, weight } from '../theme';
import type { HomeResponse, MonthlyGoalsResponse } from '../types';
import { useCategories } from '../useCategories';

export function HomeScreen({
  dataVersion,
  month,
  onMonthChange,
  onQuickAdd,
  onOpenMenu,
  onOpenRecurring,
  onOpenGoal,
  onEditTransaction,
}: {
  dataVersion: number;
  month: string;
  onMonthChange: (month: string) => void;
  onQuickAdd: () => void;
  onOpenMenu: () => void;
  onOpenRecurring: () => void;
  onOpenGoal: () => void;
  onEditTransaction: (id: string) => void;
}) {
  const [data, setData] = useState<HomeResponse | null>(null);
  const [goal, setGoal] = useState<MonthlyGoalsResponse | null>(null);
  // Income/net are not in the /home contract, so we derive them from the month's
  // transactions (signed amount_minor) — real data, not a fabricated total.
  // ponytail: single page (limit 100); add cursor paging if a month exceeds it.
  const [incomeMinor, setIncomeMinor] = useState(0);
  const [netMinor, setNetMinor] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const { labelOf } = useCategories();

  const load = useCallback(async () => {
    setError(false);
    try {
      const [home, txns, g] = await Promise.all([
        getHome(month),
        listTransactions({ month, limit: 100 }),
        getMonthlyGoals(month).catch(() => null), // goal failure is non-fatal
      ]);
      setData(home);
      setGoal(g);
      let income = 0;
      let net = 0;
      for (const t of txns.items) {
        net += t.amount_minor;
        if (t.amount_minor > 0) income += t.amount_minor;
      }
      setIncomeMinor(income);
      setNetMinor(net);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [month]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load, dataVersion]);

  const header = (
    <View style={styles.header}>
      <View style={styles.titleRow}>
        <AppText size={font.h1} weight={weight.bold}>
          בית
        </AppText>
        <Pressable onPress={onOpenMenu} hitSlop={10} style={styles.gear}>
          <Ionicons name="menu" size={24} color={colors.textSecondary} />
        </Pressable>
      </View>
      <View style={{ marginTop: spacing.sm }}>
        <MonthSwitcher month={month} onChange={onMonthChange} />
      </View>
    </View>
  );

  let body: React.ReactNode;
  if (loading) {
    body = (
      <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
        <Skeleton height={140} style={{ borderRadius: radius.card }} />
        <Skeleton height={90} style={{ borderRadius: radius.card }} />
        <Skeleton height={200} style={{ borderRadius: radius.card }} />
      </View>
    );
  } else if (error || !data) {
    body = <ErrorState onRetry={load} />;
  } else {
    const isEmpty =
      data.spent_so_far_minor === 0 &&
      incomeMinor === 0 &&
      data.recent_transactions.length === 0 &&
      data.upcoming_commitments.length === 0;
    const topCats = data.category_totals.slice(0, 4);
    const maxCat = Math.max(1, ...topCats.map((c) => c.total_minor));
    const netPositive = netMinor >= 0;

    body = (
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load();
            }}
            tintColor={colors.accent}
          />
        }
      >
        {/* Hero: actual spend this month */}
        <Card style={styles.hero}>
          <AppText size={font.caption} color={colors.textSecondary}>
            הוצאות החודש
          </AppText>
          <AppText size={font.display} weight={weight.bold} style={{ marginTop: spacing.xs }}>
            {formatAmount(data.spent_so_far_minor, data.currency)}
          </AppText>
          <View style={styles.heroMetaRow}>
            <View style={styles.metaPill}>
              <Ionicons name="pricetags-outline" size={13} color={colors.textSecondary} />
              <AppText size={font.caption} color={colors.textSecondary}>
                {data.uncategorized_count > 0
                  ? `${data.uncategorized_count} ללא קטגוריה`
                  : 'הכול מקוטלג'}
              </AppText>
            </View>
          </View>
        </Card>

        {/* Monthly goal card — expense goal with source badge */}
        <GoalCard
          goalsData={goal}
          spentMinor={data.spent_so_far_minor}
          currency={data.currency}
          onPress={onOpenGoal}
        />

        {/* Compact income + savings goals (only when at least one is set) */}
        <SecondaryGoalsCard
          goalsData={goal}
          incomeMinor={incomeMinor}
          netMinor={netMinor}
          currency={data.currency}
          onPress={onOpenGoal}
        />

        {/* Income + net cashflow (only when there is income this month) */}
        {incomeMinor > 0 ? (
          <View style={[styles.dualRow, { marginTop: spacing.md }]}>
            <Card style={styles.dualCard}>
              <AppText size={font.caption} color={colors.textSecondary}>
                הכנסות החודש
              </AppText>
              <AppText size={font.h1} weight={weight.bold} color={colors.success} style={{ marginTop: spacing.xs }}>
                {formatAmount(incomeMinor, data.currency)}
              </AppText>
            </Card>
            <Card style={styles.dualCard}>
              <AppText size={font.caption} color={colors.textSecondary}>
                תזרים נטו
              </AppText>
              <AppText
                size={font.h1}
                weight={weight.bold}
                color={netPositive ? colors.success : colors.danger}
                style={{ marginTop: spacing.xs }}
              >
                {netPositive ? '+' : '−'}
                {formatAmount(netMinor, data.currency)}
              </AppText>
            </Card>
          </View>
        ) : null}

        {isEmpty ? (
          <View style={{ marginTop: spacing.xxl }}>
            <EmptyState
              icon="wallet-outline"
              title="עדיין לא נרשמו תנועות החודש"
              subtitle="הוסף את התנועה הראשונה שלך — לוקח פחות מחמש שניות."
              action={{ label: 'הוספת תנועה', onPress: onQuickAdd }}
            />
          </View>
        ) : null}

        {topCats.length > 0 ? (
          <Card style={{ marginTop: spacing.md }}>
            <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
              לפי קטגוריות
            </AppText>
            {topCats.map((c) => {
              const meta = categoryMeta(c.category_key);
              return (
                <View key={c.category_id} style={{ marginBottom: spacing.md }}>
                  <View style={styles.rowBetween}>
                    <View style={styles.rowStart}>
                      <Ionicons name={meta.icon} size={16} color={meta.color} />
                      <AppText>{labelOf(c.category_key)}</AppText>
                    </View>
                    <AppText weight={weight.medium}>{formatAmount(c.total_minor, data.currency)}</AppText>
                  </View>
                  <View style={styles.track}>
                    <View
                      style={[
                        styles.bar,
                        { width: `${(c.total_minor / maxCat) * 100}%`, backgroundColor: meta.color },
                      ]}
                    />
                  </View>
                </View>
              );
            })}
          </Card>
        ) : null}

        {/* Recurring commitments — tappable to manage. Projection only. */}
        <Pressable onPress={onOpenRecurring}>
          <Card variant="planned" style={{ marginTop: spacing.md }}>
            <View style={styles.rowBetween}>
              <AppText size={font.caption} color={colors.textSecondary}>
                הוצאות קבועות · מתוכנן
              </AppText>
              <View style={styles.rowStart}>
                <Ionicons name="repeat" size={16} color={colors.textSecondary} />
                <Ionicons name="chevron-back" size={16} color={colors.textMuted} />
              </View>
            </View>
            {data.upcoming_commitments.length > 0 ? (
              <>
                <AppText size={font.h1} weight={weight.bold} style={{ marginTop: spacing.xs }}>
                  {formatAmount(data.committed_amount_minor, data.currency)}
                </AppText>
                {data.upcoming_commitments.slice(0, 3).map((u) => (
                  <View key={u.template_id} style={[styles.rowBetween, { marginTop: spacing.sm }]}>
                    <AppText size={font.caption} color={colors.textSecondary}>
                      {labelOf(u.category_key)} · ב־{dayOfMonth(u.next_expected_date)} ({formatDateLong(u.next_expected_date)})
                    </AppText>
                    <AppText size={font.caption}>{formatAmount(u.amount_minor, data.currency)}</AppText>
                  </View>
                ))}
              </>
            ) : (
              <AppText size={font.caption} color={colors.textMuted} style={{ marginTop: spacing.sm }}>
                הוסף מנויים וחיובים חודשיים כדי לראות תחזית כאן.
              </AppText>
            )}
          </Card>
        </Pressable>

        {data.recent_transactions.length > 0 ? (
          <Card style={{ marginTop: spacing.md, paddingVertical: spacing.sm }}>
            <AppText size={font.caption} color={colors.textSecondary} style={{ marginVertical: spacing.sm }}>
              עסקאות אחרונות
            </AppText>
            {data.recent_transactions.map((t, i) => {
              const meta = categoryMeta(t.category_key);
              const title = t.merchant_display_name ?? labelOf(t.category_key);
              const income = t.amount_minor > 0; // signed agorot: income is positive
              return (
                <Pressable key={t.id} onPress={() => onEditTransaction(t.id)}>
                  {i > 0 ? <View style={styles.divider} /> : null}
                  <View style={styles.recentRow}>
                    <View style={[styles.recentIcon, { backgroundColor: meta.color + '26' }]}>
                      <Ionicons name={meta.icon} size={18} color={meta.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <AppText weight={weight.medium} numberOfLines={1}>
                        {title}
                      </AppText>
                      {t.is_uncategorized && !income ? (
                        <AppText size={font.caption} color={colors.textMuted}>
                          לא מקוטלג
                        </AppText>
                      ) : null}
                    </View>
                    <AppText weight={weight.semibold} color={income ? colors.success : colors.textPrimary}>
                      {income ? '+' : ''}
                      {formatAmount(t.amount_minor, t.currency)}
                    </AppText>
                  </View>
                </Pressable>
              );
            })}
          </Card>
        ) : null}
      </ScrollView>
    );
  }

  return (
    <Screen>
      {header}
      {body}
    </Screen>
  );
}

// --- Goal cards (inline sub-components — no extra file needed) ---------------

function GoalCard({
  goalsData,
  spentMinor,
  currency,
  onPress,
}: {
  goalsData: MonthlyGoalsResponse | null;
  spentMinor: number;
  currency: string;
  onPress: () => void;
}) {
  const expItem = goalsData?.items.find(i => i.goal_type === 'expense') ?? null;
  const goalMinor = expItem?.effective_amount_minor ?? null;
  const source = expItem?.effective_source ?? null;

  if (goalMinor === null) {
    return (
      <Pressable onPress={onPress} style={{ marginTop: spacing.md }}>
        <Card style={goalStyles.noGoalCard}>
          <View style={goalStyles.noGoalRow}>
            <Ionicons name="flag-outline" size={15} color={colors.textMuted} />
            <AppText size={font.caption} color={colors.textMuted}>
              הגדר יעד חודשי
            </AppText>
            <Ionicons name="add-circle-outline" size={14} color={colors.textMuted} />
          </View>
        </Card>
      </Pressable>
    );
  }

  const exceeded = spentMinor > goalMinor;
  const remaining = goalMinor - spentMinor;
  const pct = goalMinor > 0 ? Math.min(1, spentMinor / goalMinor) : 0;

  return (
    <Pressable onPress={onPress} style={{ marginTop: spacing.md }}>
      <Card>
        <View style={goalStyles.rowBetween}>
          <View style={goalStyles.rowStart}>
            <Ionicons name="flag-outline" size={14} color={colors.textSecondary} />
            <AppText size={font.caption} color={colors.textSecondary}>
              יעד חודשי · הוצאות
            </AppText>
          </View>
          <View style={goalStyles.rowStart}>
            {source ? (
              <AppText
                size={font.micro}
                color={source === 'month_override' ? colors.accent : colors.textMuted}
              >
                {source === 'month_override' ? 'מותאם לחודש זה' : 'ברירת מחדל'}
              </AppText>
            ) : null}
            <Ionicons name="chevron-back" size={14} color={colors.textMuted} />
          </View>
        </View>

        <AppText size={font.h2} weight={weight.bold} style={{ marginTop: spacing.xs }}>
          {formatAmount(goalMinor, currency)}
        </AppText>

        <View style={goalStyles.track}>
          <View
            style={[
              goalStyles.bar,
              { width: `${Math.round(pct * 100)}%`, backgroundColor: exceeded ? colors.danger : colors.accent },
            ]}
          />
        </View>

        <View style={[goalStyles.rowBetween, { marginTop: spacing.sm }]}>
          <AppText size={font.caption} color={colors.textSecondary}>
            {`נוצל ${formatAmount(spentMinor, currency)}`}
          </AppText>
          {exceeded ? (
            <AppText size={font.caption} color={colors.danger}>
              {`חריגה מהיעד ב־${formatAmount(spentMinor - goalMinor, currency)}`}
            </AppText>
          ) : (
            <AppText size={font.caption} color={colors.textSecondary}>
              {`נשאר ${formatAmount(remaining, currency)}`}
            </AppText>
          )}
        </View>
      </Card>
    </Pressable>
  );
}

function SecondaryGoalsCard({
  goalsData,
  incomeMinor,
  netMinor,
  currency,
  onPress,
}: {
  goalsData: MonthlyGoalsResponse | null;
  incomeMinor: number;
  netMinor: number;
  currency: string;
  onPress: () => void;
}) {
  const incomeGoal = goalsData?.items.find(i => i.goal_type === 'income')?.effective_amount_minor ?? null;
  const savingsGoal = goalsData?.items.find(i => i.goal_type === 'savings')?.effective_amount_minor ?? null;
  if (incomeGoal === null && savingsGoal === null) return null;

  return (
    <Pressable onPress={onPress} style={{ marginTop: spacing.md }}>
      <Card>
        {incomeGoal !== null ? (
          <View style={[goalStyles.rowBetween, savingsGoal !== null ? { marginBottom: spacing.sm } : null]}>
            <AppText size={font.caption} color={colors.textSecondary}>יעד הכנסה</AppText>
            <View style={goalStyles.rowStart}>
              <AppText size={font.caption} color={colors.success}>{formatAmount(incomeMinor, currency)}</AppText>
              <AppText size={font.caption} color={colors.textMuted}>{` / ${formatAmount(incomeGoal, currency)}`}</AppText>
            </View>
          </View>
        ) : null}
        {savingsGoal !== null ? (
          <View style={goalStyles.rowBetween}>
            <AppText size={font.caption} color={colors.textSecondary}>יעד חיסכון</AppText>
            <View style={goalStyles.rowStart}>
              <AppText
                size={font.caption}
                color={netMinor >= savingsGoal ? colors.success : colors.textSecondary}
              >
                {formatAmount(Math.max(0, netMinor), currency)}
              </AppText>
              <AppText size={font.caption} color={colors.textMuted}>{` / ${formatAmount(savingsGoal, currency)}`}</AppText>
            </View>
          </View>
        ) : null}
      </Card>
    </Pressable>
  );
}

const goalStyles = StyleSheet.create({
  noGoalCard: { paddingVertical: spacing.sm },
  noGoalRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, justifyContent: 'center' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowStart: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  track: { height: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, marginTop: spacing.md, overflow: 'hidden' },
  bar: { height: 6, borderRadius: radius.pill },
});

// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  gear: { padding: spacing.xs },
  content: { padding: spacing.lg, paddingBottom: spacing.xxl },
  hero: { paddingVertical: spacing.xl },
  heroMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.lg,
  },
  metaPill: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dualRow: { flexDirection: 'row', gap: spacing.md },
  dualCard: { flex: 1 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowStart: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  track: { height: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, marginTop: spacing.sm, overflow: 'hidden' },
  bar: { height: 6, borderRadius: radius.pill },
  divider: { height: 1, backgroundColor: colors.border, marginStart: 54 },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  recentIcon: { width: 38, height: 38, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
});
