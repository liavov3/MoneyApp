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

// Shift a "YYYY-MM" by delta months (e.g. -1 / +1 for the month switcher).
export function addMonths(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

// Day-of-month (1–31) from a "YYYY-MM-DD".
export function dayOfMonth(iso: string): number {
  return Number(iso.split('-')[2]);
}

// Next calendar date (YYYY-MM-DD) that lands on `day` (1–31): this month if the
// day hasn't passed, else next month; clamped to the target month's length.
// Used to turn a recurring "יורד בכל חודש ב־X" choice into next_expected_date.
export function nextDateForDay(day: number): string {
  const now = new Date();
  const target = day < now.getDate() ? new Date(now.getFullYear(), now.getMonth() + 1, 1) : now;
  const y = target.getFullYear();
  const m = target.getMonth();
  const lastDay = new Date(y, m + 1, 0).getDate();
  const d = Math.min(day, lastDay);
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

// Today as "YYYY-MM-DD".
export function todayISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(
    now.getDate(),
  ).padStart(2, '0')}`;
}

// User-typed shekel string -> integer agorot, or null if malformed/zero.
// ponytail: integer-only math (whole*100 + padded-frac) — no float, no rounding error.
export function shekelToMinor(input: string): number | null {
  const s = input.trim().replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null;
  const [whole, frac = ''] = s.split('.');
  const minor = Number(whole) * 100 + Number((frac + '00').slice(0, 2));
  return minor > 0 ? minor : null;
}

// Integer agorot -> clean shekel input string for prefilling (e.g. 300050 -> "3000.50").
export function minorToInput(minor: number): string {
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100);
  const frac = abs % 100;
  return frac === 0 ? String(whole) : `${whole}.${String(frac).padStart(2, '0')}`;
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
