import { DOWS, SHOP_HOURS } from '../../../data/availability';

interface ShopNoteProps {
  now: Date | null;
}

function hourLabel(mins: number): string {
  const h24 = Math.floor(mins / 60);
  const m = mins % 60;
  const ap = h24 >= 12 ? 'PM' : 'AM';
  const h = h24 % 12 || 12;
  return m ? `${h}:${String(m).padStart(2, '0')} ${ap}` : `${h} ${ap}`;
}

function dayRangeLabel(a: number, b: number): string {
  return a === b ? DOWS[a] : `${DOWS[a]}–${DOWS[b]}`;
}

function mergeRanges(days: number[]): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (const d of days) {
    const last = out[out.length - 1];
    if (last && last[1] === d - 1) last[1] = d;
    else out.push([d, d]);
  }
  return out;
}

const openDays = Object.keys(SHOP_HOURS)
  .map(Number)
  .sort((a, b) => a - b);
const closedDays = [0, 1, 2, 3, 4, 5, 6].filter((d) => !(d in SHOP_HOURS));

const WEEK_LINE = [
  ...mergeRanges(openDays).map(([a, b]) => `${dayRangeLabel(a, b)} ${hourLabel(SHOP_HOURS[a][0])} – ${hourLabel(SHOP_HOURS[a][1])}`),
  ...mergeRanges(closedDays).map(([a, b]) => `${dayRangeLabel(a, b)} closed`),
].join(' · ');

export function ShopNote({ now }: ShopNoteProps) {
  let todayLine: string | null = null;
  if (now) {
    const today = SHOP_HOURS[now.getDay()];
    if (today) {
      todayLine = `Open today ${hourLabel(today[0])} – ${hourLabel(today[1])}`;
    } else {
      for (let add = 1; add <= 7; add++) {
        const d = new Date(now);
        d.setDate(now.getDate() + add);
        const hours = SHOP_HOURS[d.getDay()];
        if (hours) {
          todayLine = `Closed today · opens ${DOWS[d.getDay()]} ${hourLabel(hours[0])}`;
          break;
        }
      }
    }
  }

  return (
    <div className="book-facts">
      {todayLine && <p>{todayLine}</p>}
      <p>{WEEK_LINE}</p>
    </div>
  );
}
