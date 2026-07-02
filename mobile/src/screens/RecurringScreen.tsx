// Manage recurring commitments ("הוצאות קבועות"). List + add/edit/delete.
// Reached from Home; changes bubble up so Home's projection refreshes.
import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { listRecurring } from '../api';
import { RecurringCommitmentCard } from '../components/recurring/RecurringCommitmentCard';
import { RecurringEditor } from '../components/recurring/RecurringEditor';
import { AppText, EmptyState, ErrorState, LoadingState, Screen } from '../components/ui';
import { colors, font, radius, spacing, weight } from '../theme';
import type { TemplateOut } from '../types';
import { useCategories } from '../useCategories';

export function RecurringScreen({ onBack, onChanged }: { onBack: () => void; onChanged: () => void }) {
  const { labelOf } = useCategories();
  const [items, setItems] = useState<TemplateOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<TemplateOut | null>(null);

  const load = useCallback(async () => {
    setError(false);
    try {
      setItems((await listRecurring()).items);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openAdd = () => {
    setEditing(null);
    setEditorOpen(true);
  };
  const openEdit = (t: TemplateOut) => {
    setEditing(t);
    setEditorOpen(true);
  };
  const afterChange = () => {
    setEditorOpen(false);
    load();
    onChanged();
  };

  const header = (
    <View style={styles.header}>
      <Pressable onPress={onBack} hitSlop={10} style={styles.iconBtn}>
        <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
      </Pressable>
      <AppText size={font.h2} weight={weight.bold}>
        הוצאות קבועות
      </AppText>
      <Pressable onPress={openAdd} hitSlop={10} style={styles.iconBtn}>
        <Ionicons name="add" size={26} color={colors.accent} />
      </Pressable>
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
        icon="repeat"
        title="אין עדיין הוצאות קבועות"
        subtitle="מנויים וחיובים חודשיים שתוסיף יופיעו כאן ובתחזית של מסך הבית."
        action={{ label: 'הוספת הוצאה קבועה', onPress: openAdd }}
      />
    );
  } else {
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
        {items.map((t) => (
          <RecurringCommitmentCard
            key={t.id}
            template={t}
            categoryLabel={labelOf(t.category_key)}
            onPress={() => openEdit(t)}
          />
        ))}
      </ScrollView>
    );
  }

  return (
    <Screen>
      {header}
      {body}
      <RecurringEditor
        template={editing}
        visible={editorOpen}
        onClose={() => setEditorOpen(false)}
        onSaved={afterChange}
        onDeleted={afterChange}
      />
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
  iconBtn: { padding: spacing.xs, minWidth: 32, alignItems: 'center' },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
});
