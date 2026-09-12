// Shared, module-cached category list (key -> Hebrew label + the consumer set
// for the picker). Categories are static/seeded, so fetch once per app run.
import { useEffect, useSyncExternalStore } from 'react';

import { getCategories } from './api';
import { createCategoryStore } from './categoryStore';
import { session } from './session';

const store = createCategoryStore(async () => (await getCategories()).items);
let lastConnection = session.getConnection();
session.subscribe(() => {
  const next = session.getConnection();
  if (next === lastConnection) return;
  lastConnection = next;
  store.reset();
  if (next) void store.reload();
});

export function useCategories() {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const cats = state.items;

  useEffect(() => {
    if (session.getConnection() && !store.getSnapshot().items && !store.getSnapshot().error) void store.reload();
  }, []);

  const labelOf = (key: string | null | undefined): string =>
    (key && cats?.find((c) => c.key === key)?.label_he) || key || 'ללא קטגוריה';

  const consumer = (cats ?? []).filter((c) => c.layer === 'consumer_spending');

  return { labelOf, consumer, ready: !!cats, loading: state.loading, error: state.error, reload: store.reload };
}
