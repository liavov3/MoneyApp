// Local PRESENTATION mapping only (icon + color) for category keys. The backend
// owns category data/labels (label_he); this just decorates them in the UI.
// Unknown keys get a deterministic color + a generic icon, so nothing looks broken.
import { Ionicons } from '@expo/vector-icons';

import { categoryPalette } from './theme';

type IconName = keyof typeof Ionicons.glyphMap;

const META: Record<string, { icon: IconName; color: string }> = {
  groceries: { icon: 'cart', color: '#43C59E' },
  eating_out: { icon: 'restaurant', color: '#E0A458' },
  transport: { icon: 'bus', color: '#5B8DEF' },
  car: { icon: 'car-sport', color: '#7C8AF0' },
  fuel: { icon: 'car', color: '#7C8AF0' },
  subscriptions: { icon: 'repeat', color: '#C77DFF' },
  health: { icon: 'fitness', color: '#EF6F8E' },
  personal_care: { icon: 'cut', color: '#E05B9A' },
  home: { icon: 'home', color: '#5AC8E0' },
  shopping: { icon: 'bag-handle', color: '#9AD05B' },
  entertainment: { icon: 'game-controller', color: '#C77DFF' },
  education: { icon: 'school', color: '#5B8DEF' },
  travel: { icon: 'airplane', color: '#5AC8E0' },
  gifts: { icon: 'gift', color: '#EF6F8E' },
  kids: { icon: 'happy', color: '#E0A458' },
  pets: { icon: 'paw', color: '#9AD05B' },
  other: { icon: 'pricetags', color: '#727C8C' },
};

function hashColor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return categoryPalette[h % categoryPalette.length];
}

export function categoryMeta(key: string | null | undefined): {
  icon: IconName;
  color: string;
} {
  if (key && META[key]) return META[key];
  return { icon: 'pricetag', color: key ? hashColor(key) : '#727C8C' };
}
