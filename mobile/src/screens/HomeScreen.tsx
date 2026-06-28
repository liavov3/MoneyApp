// Home Dashboard (read-only). Renders real GET /home data. Actual spend
// (transactions) and planned commitments (recurring templates) are rendered as
// separate, differently-tinted sections — never summed (API_CONTRACT §13).
// Hebrew category labels come from GET /categories (label_he); /home only
// carries label_en / category_key.
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError, getCategories, getHome } from '../api';
import { AppText, Button, Card, Loading, SectionTitle } from '../components/ui';
import { formatAmount, formatMonth, formatShortDate } from '../format';
import { colors, font, spacing } from '../theme';
import type { CategoryTotal, HomeResponse, RecentTxn, UpcomingCommitment } from '../types';

type LabelMap = Record<string, string>;

export default function HomeScreen({ onAuthExpired }: { onAuthExpired: () => void }) {
  const [data, setData] = useState<HomeResponse | null>(null);
  const [labels, setLabels] = useState<LabelMap>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setError(false);
    try {
      const [home, cats] = await Promise.all([getHome(), getCategories()]);
      const map: LabelMap = {};
      for (const c of cats.items) {
        if (c.key) map[c.key] = c.label_he ?? c.label_en;
      }
      setData(home);
      setLabels(map);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        onAuthExpired();
        return;
      }
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [onAuthExpired]);

  useEffect(() => {
    load();
  }, [load]);

  const catLabel = (key: string | null, fallback?: string) =>
    (key && labels[key]) || fallback || 'ללא קטגוריה';

  if (loading) return <Loading label="טוען…" />;

  if (error || !data) {
    return (
      <View style={styles.center}>
        <AppText size={font.title} style={{ marginBottom: spacing.lg, textAlign: 'center' }}>
          לא הצלחנו לטעון את הנתונים
        </AppText>
        <Button title="נסה שוב" onPress={load} />
      </View>
    );
  }

  const isEmpty =
    data.spent_so_far_minor === 0 &&
    data.recent_transactions.length === 0 &&
    data.upcoming_commitments.length === 0;
  const maxCat = Math.max(1, ...data.category_totals.map((c) => c.total_minor));

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={styles.content}
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
      {/* Actual spend headline */}
      <Card>
        <SectionTitle>הוצאות החודש · {formatMonth(data.month)}</SectionTitle>
        <AppText size={font.display} weight="700">
          {formatAmount(data.spent_so_far_minor, data.currency)}
        </AppText>
        {data.uncategorized_count > 0 ? (
          <AppText color={colors.textSecondary} size={font.caption} style={{ marginTop: spacing.sm }}>
            {data.uncategorized_count} ללא קטגוריה
          </AppText>
        ) : null}
      </Card>

      {isEmpty ? (
        <Card>
          <AppText color={colors.textSecondary} style={{ textAlign: 'center' }}>
            עדיין לא נרשמו הוצאות החודש
          </AppText>
        </Card>
      ) : null}

      {/* Top category */}
      {data.top_category ? (
        <Card>
          <SectionTitle>קטגוריה מובילה</SectionTitle>
          <View style={styles.row}>
            <AppText weight="600">
              {catLabel(data.top_category.category_key, data.top_category.label_en)}
            </AppText>
            <AppText weight="600">{formatAmount(data.top_category.total_minor, data.currency)}</AppText>
          </View>
        </Card>
      ) : null}

      {/* Category breakdown (actual only) */}
      {data.category_totals.length > 0 ? (
        <Card>
          <SectionTitle>לפי קטגוריות</SectionTitle>
          {data.category_totals.map((c: CategoryTotal) => (
            <View key={c.category_id} style={{ marginBottom: spacing.md }}>
              <View style={styles.row}>
                <AppText>{catLabel(c.category_key, c.label_en)}</AppText>
                <AppText>{formatAmount(c.total_minor, data.currency)}</AppText>
              </View>
              <View style={styles.track}>
                <View style={[styles.bar, { width: `${(c.total_minor / maxCat) * 100}%` }]} />
              </View>
            </View>
          ))}
        </Card>
      ) : null}

      {/* Planned commitments — DISTINCT tinted card, never blended with spend */}
      <Card planned>
        <SectionTitle>הוצאות קבועות · מתוכנן</SectionTitle>
        <AppText size={font.heading} weight="700">
          {formatAmount(data.committed_amount_minor, data.currency)}
        </AppText>
        {data.upcoming_commitments.length > 0 ? (
          <View style={{ marginTop: spacing.lg }}>
            <SectionTitle>חיובים קרובים</SectionTitle>
            {data.upcoming_commitments.map((u: UpcomingCommitment) => (
              <View key={u.template_id} style={[styles.row, { marginBottom: spacing.sm }]}>
                <AppText color={colors.textSecondary}>
                  {catLabel(u.category_key)} · {formatShortDate(u.next_expected_date)}
                </AppText>
                <AppText>{formatAmount(u.amount_minor, data.currency)}</AppText>
              </View>
            ))}
          </View>
        ) : null}
      </Card>

      {/* Recent transactions */}
      {data.recent_transactions.length > 0 ? (
        <Card>
          <SectionTitle>עסקאות אחרונות</SectionTitle>
          {data.recent_transactions.map((t: RecentTxn) => (
            <View key={t.id} style={[styles.row, { marginBottom: spacing.md }]}>
              <View style={{ flex: 1 }}>
                <AppText>
                  {t.merchant_display_name ??
                    (t.is_uncategorized ? 'ללא קטגוריה' : catLabel(t.category_key))}
                </AppText>
                <AppText color={colors.muted} size={font.caption}>
                  {formatShortDate(t.occurred_on)}
                  {t.is_uncategorized ? ' · לא מקוטלג' : ''}
                </AppText>
              </View>
              <AppText weight="600">{formatAmount(t.amount_minor, t.currency)}</AppText>
            </View>
          ))}
        </Card>
      ) : null}

      {/* Quick Add placeholder (next slice) */}
      <Button
        title="הוספת הוצאה"
        onPress={() => Alert.alert('הוספת הוצאה', 'זמין בקרוב')}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, paddingBottom: spacing.xl },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.bg,
  },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  track: {
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.elevated,
    marginTop: spacing.sm,
    overflow: 'hidden',
  },
  bar: { height: 6, borderRadius: 999, backgroundColor: colors.accent },
});
