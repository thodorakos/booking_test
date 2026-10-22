import { useEffect, useRef, useState } from 'react';
import type { Shop } from '../../../data/catalog';
import { shopDate } from '../../../data/availability';
import { Icon } from '../Icon';

interface Props {
  shop: Shop;
  id: string;
  value: string;
  min: string;
  max: string;
  onSelect: (date: string) => void;
}

const DOWS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function monthIndex(iso: string): number {
  return Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1;
}
function monthIso(index: number, day: number): string {
  const year = Math.floor(index / 12);
  const month = index % 12 + 1;
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}
function monthTitle(index: number): string {
  return new Date(Date.UTC(Math.floor(index / 12), index % 12, 1)).toLocaleDateString('en-GB', { timeZone: 'UTC', month: 'long', year: 'numeric' });
}
function dayLabel(iso: string, style: Intl.DateTimeFormatOptions): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { timeZone: 'UTC', ...style });
}

export function DatePicker({ shop, id, value, min, max, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => monthIndex(min));
  const root = useRef<HTMLDivElement>(null);
  const minMonth = monthIndex(min);
  const maxMonth = monthIndex(max);
  const daysInMonth = new Date(Date.UTC(Math.floor(view / 12), view % 12 + 1, 0)).getUTCDate();
  const offset = (new Date(`${monthIso(view, 1)}T12:00:00Z`).getUTCDay() + 6) % 7;
  const today = shopDate(shop.timezone);

  function openPanel() {
    setView(Math.min(Math.max(monthIndex(value || min), minMonth), maxMonth));
    setOpen(true);
  }
  function choose(iso: string) {
    setOpen(false);
    onSelect(iso);
    root.current?.querySelector<HTMLButtonElement>('button')?.focus();
  }

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') { setOpen(false); root.current?.querySelector<HTMLButtonElement>('button')?.focus(); }
    }
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    requestAnimationFrame(() => {
      root.current?.querySelector<HTMLButtonElement>(`.cal-day[aria-pressed="true"], .cal-day:not(:disabled)`)?.focus();
    });
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const disabledDay = (iso: string) => {
    const dow = (new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7;
    return iso < min || iso > max || shop.closed_weekdays.includes(dow);
  };

  return <div ref={root} className="date-wrap">
    <button className="date-toggle" id={id} type="button" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? `${id}-panel` : undefined} onClick={() => (open ? setOpen(false) : openPanel())}>
      <span className={value ? '' : 'date-toggle-ph'}>{value ? dayLabel(value, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : 'Choose a date'}</span>
      <Icon name="calendar" size={16} />
    </button>
    {open && <div className="date-picker" role="dialog" id={`${id}-panel`} aria-label="Choose appointment date">
      <div className="cal-head">
        <button type="button" className="cal-nav" onClick={() => setView(view - 1)} disabled={view <= minMonth} aria-label="Previous month"><Icon name="chevron-left" size={16} /></button>
        <span className="cal-title">{monthTitle(view)}</span>
        <button type="button" className="cal-nav" onClick={() => setView(view + 1)} disabled={view >= maxMonth} aria-label="Next month"><Icon name="chevron-right" size={16} /></button>
      </div>
      <div className="cal-grid" role="group" aria-labelledby={id}>
        {DOWS.map((dow) => <span className="cal-dow" key={dow}>{dow}</span>)}
        {Array.from({ length: offset }, (_, cell) => <span key={`pad-${cell}`} />)}
        {Array.from({ length: daysInMonth }, (_, day) => {
          const iso = monthIso(view, day + 1);
          const isBlocked = disabledDay(iso);
          return <button type="button" className={`cal-day${iso === today ? ' is-today' : ''}`} key={iso} disabled={isBlocked} aria-pressed={value === iso} aria-label={dayLabel(iso, { weekday: 'long', day: 'numeric', month: 'long' })} onClick={() => choose(iso)}>{day + 1}</button>;
        })}
      </div>
    </div>}
  </div>;
}
