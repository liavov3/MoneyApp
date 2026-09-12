import type { CategoryOut } from './types';

type Snapshot = { items: CategoryOut[] | null; loading: boolean; error: boolean };

// All mounted screens share one request and receive the same recovered data.
export function createCategoryStore(fetchCategories: () => Promise<CategoryOut[]>) {
  let snapshot: Snapshot = { items: null, loading: false, error: false };
  let pending: Promise<void> | null = null;
  let generation = 0;
  const listeners = new Set<() => void>();
  const publish = (next: Snapshot) => {
    snapshot = next;
    listeners.forEach((listener) => listener());
  };
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    reset: () => {
      generation++;
      pending = null;
      publish({ items: null, loading: false, error: false });
    },
    reload: () => {
      if (pending) return pending;
      const request = generation;
      pending = Promise.resolve().then(fetchCategories).then(
        (items) => { if (request === generation) publish({ items, loading: false, error: false }); },
        () => { if (request === generation) publish({ items: snapshot.items, loading: false, error: true }); },
      ).finally(() => { if (request === generation) pending = null; });
      publish({ items: snapshot.items, loading: true, error: false });
      return pending;
    },
  };
}
