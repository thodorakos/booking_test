import { useEffect, useState } from 'react';
import { buildDays, DOWS, MONTHS, findNextOpening, formatTime } from '../../data/availability';
import { Icon } from './Icon';

/**
 * Small island on the home hero. The next opening depends on the current
 * date/time, which can't be known at build time — so it renders nothing on
 * the server and fills in after hydration (client:idle).
 */
export default function NextOpening() {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    const next = findNextOpening(buildDays(), new Date());
    if (!next) return;
    const word =
      next.index === 0
        ? 'today'
        : next.index === 1
          ? 'tomorrow'
          : `${DOWS[next.date.getDay()]}, ${MONTHS[next.date.getMonth()]} ${next.date.getDate()}`;
    // setState in effect is intentional: the value must stay unrendered on the
    // server (prerendered HTML has no clock), which rules out a lazy initializer.
    // Documented hydration-mismatch pattern from react.dev.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setText(`Next opening ${word} · ${formatTime(next.minutes)} · No deposit`);
  }, []);

  if (!text) return null;
  return (
    <p className="hero-next">
      <Icon name="clock" size={14} />
      <span>{text}</span>
    </p>
  );
}
