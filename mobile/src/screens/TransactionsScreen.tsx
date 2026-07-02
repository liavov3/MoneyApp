import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, SectionList, StyleSheet, View } from 'react-native';

import { listTransactions } from '../api';
import { TransactionListItem } from '../components/transactions/TransactionListItem';
import { MonthSwitcher } from '../components/ui/MonthSwitcher';
import { AppText, EmptyState, ErrorState, LoadingState, Screen } from '../components/ui';
import { dateHeader, formatMonthLabel } from '../format';
import { colors, font, spacing, weight } from '../theme';
import type { TransactionOut } from '../types';
import { useCategories } from '../useCategories';

type Section = { title: string; data: TransactionOut[] };

function groupByDate(items: TransactionOut[]): Section[] {
  const map = new Map<string, TransactionOut[]>();
  for (const t of items) {
    const arr = map.get(t.occurred_on) ?? [];
    arr.push(t);
    map.set(t.occurred_on, arr);
  }
  // items already arrive newest-first (occurred_on DESC) from the API.
  return [...map.entries()].map(([date, data]) => ({ title: dateHeader(date), data }));
}

export function TransactionsScreen({
  dataVersion,
  month,
  onMonthChange,
  onOpenMenu,
  onEditTransaction,
}: {
  dataVersion: number;
  month: string;
  onMonthChange: (month: string) => void;
  onOpenMenu: () => void;
  onEditTransaction: (id: string) => void;
}) {
  const [items, setItems] = useState<TransactionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const { labelOf } = useCategories();

  const load = useCallback(async () => {
    setError(false);
    try {
      const res = await listTransactions({ month, limit: 100 });
      setItems(res.items);
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
          עסקאות
        </AppText>
        <Pressable onPress={onOpenMenu} hitSlop={10} style={{ padding: spacing.xs }}>
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
    body = <LoadingState />;
  } else if (error) {
    body = <ErrorState onRetry={load} />;
  } else if (items.length === 0) {
    body = (
      <EmptyState
        icon="receipt-outline"
        title={`אין תנועות ב${formatMonthLabel(month)}`}
        subtitle="תנועות שתוסיף בחודש זה יופיעו כאן."
      />
    );
  } else {
    body = (
      <SectionList
        sections={groupByDate(items)}
        keyExtractor={(t) => t.id}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        stickySectionHeadersEnabled={false}
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
        renderSectionHeader={({ section }) => (
          <AppText size={font.caption} color={colors.textMuted} style={styles.sectionHeader}>
            {section.title}
          </AppText>
        )}
        renderItem={({ item }) => (
          <TransactionListItem
            txn={item}
            label={labelOf(item.category_key)}
            onPress={() => onEditTransaction(item.id)}
          />
        )}
      />
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
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl },
  sectionHeader: { marginTop: spacing.lg, marginBottom: spacing.xs },
});
