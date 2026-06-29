// Shared, module-cached category list (key -> Hebrew label + the consumer set
// for the picker). Categories are static/seeded, so fetch once per app run.
import { useEffect, useState } from 'react';

import { getCategories } from './api';
import type { CategoryOut } from './types';

let cache: CategoryOut[] | null = null;

export function useCategories() {
  const [cats, setCats] = useState<CategoryOut[] | null>(cache);

  useEffect(() => {
    if (cache) return;
    let alive = true;
    getCategories()
      .then((r) => {
        cache = r.items;
        if (alive) setCats(cache);
      })
      .catch(() => {
        /* labels just fall back to the key; not fatal for the dashboard */
      });
    return () => {
      alive = false;
    };
  }, []);

  const labelOf = (key: string | null | undefined): string =>
    (key && cats?.find((c) => c.key === key)?.label_he) || key || 'ללא קטגוריה';

  const consumer = (cats ?? []).filter((c) => c.layer === 'consumer_spending');

  return { labelOf, consumer, ready: !!cats };
}
