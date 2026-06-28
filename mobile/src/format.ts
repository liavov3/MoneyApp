// Money + date display. Amounts arrive as signed integer agorot; we show the
// magnitude in shekels (sign meaning is carried by the section, not a minus).

export function formatAmount(minor: number, currency = 'ILS'): string {
  const major = Math.abs(minor) / 100;
  const num = major.toLocaleString('he-IL', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  return currency === 'ILS' ? `₪${num}` : `${num} ${currency}`;
}

// "2026-06-14" -> "14.06" (short, day-first for he-IL).
export function formatShortDate(iso: string): string {
  const [, m, d] = iso.split('-');
  return d && m ? `${d}.${m}` : iso;
}

// "2026-06" -> "06/2026".
export function formatMonth(month: string): string {
  const [y, m] = month.split('-');
  return y && m ? `${m}/${y}` : month;
}
