import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, SectionList, StyleSheet, View } from 'react-native';

import { listTransactions } from '../api';
import { TransactionListItem } from '../components/transactions/TransactionListItem';
import { MonthSwitcher } from '../components/ui/MonthSwitcher';
import { AppText, Button, EmptyState, ErrorState, LoadingState, Screen } from '../components/ui';
import { CategoryChip } from '../components/categories/CategoryChip';
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
  const { labelOf, consumer } = useCategories();
  const [filter, setFilter] = useState<string | null>(null);
  const [allMonths, setAllMonths] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pageError, setPageError] = useState(false);
  const generation = useRef(0);
  const pageBusy = useRef(false);

  const load = useCallback(async () => {
    const request = ++generation.current;
    pageBusy.current = false;
    setLoadingMore(false);
    setPageError(false);
    setCursor(null);
    setError(false);
    try {
      const res = await listTransactions({
        month: allMonths ? undefined : month, limit: 50,
        category_id: filter && filter !== 'uncategorized' ? filter : undefined,
        uncategorized: filter === 'uncategorized',
      });
      if (request !== generation.current) return;
      setItems(res.items);
      setCursor(res.next_cursor);
    } catch {
      if (request !== generation.current) return;
      setError(true);
    } finally {
      if (request === generation.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [month, allMonths, filter]);

  const loadMore = async () => {
    if (!cursor || pageBusy.current || loading || refreshing) return;
    const request = generation.current;
    pageBusy.current = true;
    setLoadingMore(true);
    setPageError(false);
    try {
      const result = await listTransactions({
        month: allMonths ? undefined : month, limit: 50, cursor,
        category_id: filter && filter !== 'uncategorized' ? filter : undefined,
        uncategorized: filter === 'uncategorized',
      });
      if (request !== generation.current) return;
      setItems((previous) => {
        const ids = new Set(previous.map((item) => item.id));
        return [...previous, ...result.items.filter((item) => !ids.has(item.id))];
      });
      setCursor(result.next_cursor);
    } catch {
      if (request === generation.current) setPageError(true);
    } finally {
      if (request === generation.current) {
        pageBusy.current = false;
        setLoadingMore(false);
      }
    }
  };

  useEffect(() => {
    setLoading(true);
    load();
    return () => { ++generation.current; };
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
      <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
        {!allMonths ? <MonthSwitcher month={month} onChange={onMonthChange} /> : null}
        <Button title={allMonths ? 'חזרה לחודש הנבחר' : 'כל החודשים'} variant="ghost" onPress={() => setAllMonths((value) => !value)} />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          <CategoryChip categoryKey={null} label="הכול" selected={filter === null} onPress={() => setFilter(null)} />
          <CategoryChip categoryKey={null} label="ללא קטגוריה" selected={filter === 'uncategorized'} onPress={() => setFilter('uncategorized')} />
          {consumer.map((category) => (
            <CategoryChip key={category.id} categoryKey={category.key} label={category.label_he ?? category.label_en}
              selected={filter === category.id} onPress={() => setFilter(category.id)} />
          ))}
        </ScrollView>
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
        title={filter ? 'אין תנועות בסינון הזה' : allMonths ? 'אין תנועות עדיין' : `אין תנועות ב${formatMonthLabel(month)}`}
        subtitle={filter ? 'אפשר לבחור קטגוריה אחרת או להציג את הכול.' : 'תנועות שתוסיף יופיעו כאן.'}
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
        onEndReached={() => { if (!pageError) void loadMore(); }}
        onEndReachedThreshold={0.3}
        ListFooterComponent={cursor ? (
          <View style={{ paddingVertical: spacing.md, gap: spacing.sm }}>
            {pageError ? <AppText color={colors.danger}>טעינת תנועות נוספות נכשלה. התנועות שכבר נטענו נשמרו.</AppText> : null}
            <Button title={pageError ? 'ניסיון נוסף' : 'טעינת תנועות נוספות'} onPress={loadMore} loading={loadingMore} variant="ghost" />
          </View>
        ) : null}
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
