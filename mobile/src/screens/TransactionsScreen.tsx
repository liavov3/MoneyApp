import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Pressable, RefreshControl, SectionList, StyleSheet, View } from 'react-native';

import { deleteTransaction, listTransactions } from '../api';
import { TransactionListItem } from '../components/transactions/TransactionListItem';
import { AppText, EmptyState, ErrorState, LoadingState, Screen } from '../components/ui';
import { currentMonth, dateHeader, formatMonthLabel } from '../format';
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
  onDataChanged,
  onOpenSettings,
}: {
  dataVersion: number;
  onDataChanged: () => void;
  onOpenSettings: () => void;
}) {
  const month = currentMonth();
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
    load();
  }, [load, dataVersion]);

  const confirmDelete = (t: TransactionOut) => {
    Alert.alert('מחיקת עסקה', 'למחוק את העסקה? פעולה זו אינה הפיכה.', [
      { text: 'ביטול', style: 'cancel' },
      {
        text: 'מחיקה',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteTransaction(t.id);
            setItems((prev) => prev.filter((x) => x.id !== t.id));
            onDataChanged();
          } catch {
            Alert.alert('שגיאה', 'מחיקת העסקה נכשלה. נסה שוב.');
          }
        },
      },
    ]);
  };

  const header = (
    <View style={styles.header}>
      <View>
        <AppText size={font.h1} weight={weight.bold}>
          עסקאות
        </AppText>
        <AppText size={font.caption} color={colors.textMuted}>
          {formatMonthLabel(month)}
        </AppText>
      </View>
      <Pressable onPress={onOpenSettings} hitSlop={10} style={{ padding: spacing.xs }}>
        <Ionicons name="settings-outline" size={22} color={colors.textSecondary} />
      </Pressable>
    </View>
  );

  let body: React.ReactNode;
  if (loading) {
    body = <LoadingState />;
  } else if (error) {
    body = <ErrorState onRetry={load} />;
  } else if (items.length === 0) {
    body = <EmptyState icon="receipt-outline" title="אין עסקאות בחודש זה" subtitle="הוצאות שתוסיף יופיעו כאן." />;
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
          <TransactionListItem txn={item} label={labelOf(item.category_key)} onPress={() => confirmDelete(item)} />
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
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl },
  sectionHeader: { marginTop: spacing.lg, marginBottom: spacing.xs },
});
