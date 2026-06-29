// Cohesive dark "calm fintech" design system. High-contrast text, one accent,
// semantic colors for money, a small category palette. Tuned for readability.
export const colors = {
  // Surfaces (near-black with a cool tint; layered)
  bg: '#0B0E13',
  surface: '#151A22',
  surfaceAlt: '#1C232E',
  border: '#28303D',
  // Text (all pass ≥4.5:1 on bg/surface)
  textPrimary: '#F5F7FA',
  textSecondary: '#AEB7C4',
  textMuted: '#727C8C',
  // Brand + semantics
  accent: '#5B8DEF',
  accentSoft: '#1E2A44',
  onAccent: '#0A0E15',
  success: '#43C59E', // income / positive
  danger: '#F2606B', // destructive / alerts
  warning: '#E0A458',
  planned: '#221F3A', // recurring commitments tint (distinct from spend)
  plannedBorder: '#34306B',
};

// Pleasant muted palette for categories (deterministic pick by key).
export const categoryPalette = [
  '#5B8DEF', '#43C59E', '#E0A458', '#C77DFF', '#EF6F8E',
  '#5AC8E0', '#9AD05B', '#E08A58', '#7C8AF0', '#E05B9A',
];

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 10, input: 14, card: 18, pill: 999 };

export const font = {
  display: 34,
  h1: 26,
  h2: 20,
  title: 17,
  body: 15,
  caption: 13,
  micro: 11,
};

export const weight = {
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
};

// Soft elevation for cards (subtle; no neon).
export const shadow = {
  shadowColor: '#000',
  shadowOpacity: 0.25,
  shadowRadius: 12,
  shadowOffset: { width: 0, height: 4 },
  elevation: 4,
};
