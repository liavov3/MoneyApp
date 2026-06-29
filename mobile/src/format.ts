// Money + date display. Amounts arrive as signed integer agorot; we show the
// magnitude in shekels (sign meaning is carried by context, not a minus).

export function formatAmount(minor: number, currency = 'ILS'): string {
  const major = Math.abs(minor) / 100;
  const num = major.toLocaleString('he-IL', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  return currency === 'ILS' ? `₪${num}` : `${num} ${currency}`;
}

const HE_MONTHS = [
  'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
  'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
];

// "2026-06" -> "יוני 2026".
export function formatMonthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number);
  return m >= 1 && m <= 12 ? `${HE_MONTHS[m - 1]} ${y}` : month;
}

// "2026-06-14" -> "14 ביוני".
export function formatDateLong(iso: string): string {
  const [, m, d] = iso.split('-').map(Number);
  return m >= 1 && m <= 12 ? `${d} ב${HE_MONTHS[m - 1]}` : iso;
}

// Current month as "YYYY-MM" (device local time).
export function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

// Today as "YYYY-MM-DD".
export function todayISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(
    now.getDate(),
  ).padStart(2, '0')}`;
}

// Friendly date header for grouped lists: היום / אתמול / "14 ביוני".
export function dateHeader(iso: string): string {
  if (iso === todayISO()) return 'היום';
  const d = new Date(iso + 'T00:00:00');
  const yest = new Date();
  yest.setDate(yest.getDate() - 1);
  const yIso = `${yest.getFullYear()}-${String(yest.getMonth() + 1).padStart(2, '0')}-${String(
    yest.getDate(),
  ).padStart(2, '0')}`;
  if (iso === yIso) return 'אתמול';
  return formatDateLong(iso);
}
