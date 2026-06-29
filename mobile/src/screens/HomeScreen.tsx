import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { getHome } from '../api';
import { categoryMeta } from '../categories';
import { AppText, Card, EmptyState, ErrorState, Screen, Skeleton } from '../components/ui';
import { formatAmount, formatMonthLabel } from '../format';
import { colors, font, radius, spacing, weight } from '../theme';
import type { HomeResponse } from '../types';
import { useCategories } from '../useCategories';

export function HomeScreen({
  dataVersion,
  onQuickAdd,
  onOpenSettings,
}: {
  dataVersion: number;
  onQuickAdd: () => void;
  onOpenSettings: () => void;
}) {
  const [data, setData] = useState<HomeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const { labelOf } = useCategories();

  const load = useCallback(async () => {
    setError(false);
    try {
      setData(await getHome());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, dataVersion]);

  const header = (
    <View style={styles.header}>
      <View>
        <AppText size={font.h1} weight={weight.bold}>
          בית
        </AppText>
        {data ? (
          <AppText size={font.caption} color={colors.textMuted}>
            {formatMonthLabel(data.month)}
          </AppText>
        ) : null}
      </View>
      <Pressable onPress={onOpenSettings} hitSlop={10} style={styles.gear}>
        <Ionicons name="settings-outline" size={22} color={colors.textSecondary} />
      </Pressable>
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
      data.recent_transactions.length === 0 &&
      data.upcoming_commitments.length === 0;
    const topCats = data.category_totals.slice(0, 4);
    const maxCat = Math.max(1, ...topCats.map((c) => c.total_minor));

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
            <AppText size={font.caption} color={colors.textMuted}>
              אין יעד חודשי מוגדר
            </AppText>
          </View>
        </Card>

        {isEmpty ? (
          <View style={{ marginTop: spacing.xxl }}>
            <EmptyState
              icon="wallet-outline"
              title="עדיין לא נרשמו הוצאות החודש"
              subtitle="הוסף את ההוצאה הראשונה שלך — לוקח פחות מחמש שניות."
              action={{ label: 'הוספת הוצאה', onPress: onQuickAdd }}
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

        {data.committed_amount_minor > 0 || data.upcoming_commitments.length > 0 ? (
          <Card variant="planned" style={{ marginTop: spacing.md }}>
            <View style={styles.rowBetween}>
              <AppText size={font.caption} color={colors.textSecondary}>
                הוצאות קבועות · מתוכנן
              </AppText>
              <Ionicons name="repeat" size={16} color={colors.textSecondary} />
            </View>
            <AppText size={font.h1} weight={weight.bold} style={{ marginTop: spacing.xs }}>
              {formatAmount(data.committed_amount_minor, data.currency)}
            </AppText>
            {data.upcoming_commitments.slice(0, 3).map((u) => (
              <View key={u.template_id} style={[styles.rowBetween, { marginTop: spacing.sm }]}>
                <AppText size={font.caption} color={colors.textSecondary}>
                  {labelOf(u.category_key)}
                </AppText>
                <AppText size={font.caption}>{formatAmount(u.amount_minor, data.currency)}</AppText>
              </View>
            ))}
          </Card>
        ) : null}

        {data.recent_transactions.length > 0 ? (
          <Card style={{ marginTop: spacing.md, paddingVertical: spacing.sm }}>
            <AppText size={font.caption} color={colors.textSecondary} style={{ marginVertical: spacing.sm }}>
              עסקאות אחרונות
            </AppText>
            {data.recent_transactions.map((t, i) => {
              const meta = categoryMeta(t.category_key);
              const title = t.merchant_display_name ?? labelOf(t.category_key);
              return (
                <View key={t.id}>
                  {i > 0 ? <View style={styles.divider} /> : null}
                  <View style={styles.recentRow}>
                    <View style={[styles.recentIcon, { backgroundColor: meta.color + '26' }]}>
                      <Ionicons name={meta.icon} size={18} color={meta.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <AppText weight={weight.medium} numberOfLines={1}>
                        {title}
                      </AppText>
                      {t.is_uncategorized ? (
                        <AppText size={font.caption} color={colors.textMuted}>
                          לא מקוטלג
                        </AppText>
                      ) : null}
                    </View>
                    <AppText weight={weight.semibold}>{formatAmount(t.amount_minor, t.currency)}</AppText>
                  </View>
                </View>
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

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
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
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rowStart: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  track: { height: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, marginTop: spacing.sm, overflow: 'hidden' },
  bar: { height: 6, borderRadius: radius.pill },
  divider: { height: 1, backgroundColor: colors.border, marginStart: 54 },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  recentIcon: { width: 38, height: 38, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
});
