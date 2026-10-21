import { SERVICE_MAP } from '../../../data/catalog';
import { DOWS, dayEnabled, fullDayLabel, getSlots, type DayInfo } from '../../../data/availability';

interface WhenStepProps {
  days: DayInfo[] | null;
  now: Date | null;
  dayIdx: number | null;
  time: number | null;
  barberId: string | null;
  serviceId: string | null;
  onSelectDay: (index: number) => void;
  onSelectTime: (minutes: number) => void;
}

export function WhenStep({ days, now, dayIdx, time, barberId, serviceId, onSelectDay, onSelectTime }: WhenStepProps) {
  const duration = serviceId ? SERVICE_MAP.get(serviceId)!.dur : 45;
  const slots = days && dayIdx != null && now ? getSlots(days, dayIdx, duration, barberId, now) : [];

  let slotsBody;
  if (dayIdx == null) {
    slotsBody = <p className="slots-empty">Pick a day above to see open times.</p>;
  } else if (!slots.length) {
    slotsBody = <p className="slots-empty">No times on this day. Pick another one.</p>;
  } else if (!slots.some((x) => x.free)) {
    slotsBody = <p className="slots-empty">Fully booked this day. Try another one.</p>;
  } else {
    slotsBody = slots.map((x) => (
      <label className={x.free ? 'slot-opt' : 'slot-opt is-off'} key={x.minutes}>
        <input
          className="control-input"
          type="radio"
          name="time"
          value={x.minutes}
          aria-label={x.free ? x.label : `${x.label}, not available`}
          disabled={!x.free}
          checked={time === x.minutes}
          onChange={() => onSelectTime(x.minutes)}
        />
        <span className="slot-in">{x.label}</span>
      </label>
    ));
  }

  return (
    <section className="step" aria-labelledby="stepWhenTitle">
      <div className="step-head">
        <h2 id="stepWhenTitle"><span className="step-num">3</span>Day &amp; time</h2>
      </div>
      <div className="day-strip" key={days ? 'days-ready' : 'days-pending'} role="radiogroup" aria-label="Choose a day">
        {days?.map((d, i) => {
          const enabled = dayEnabled(days, i, barberId);
          const label = i === 0 ? 'Today' : i === 1 ? 'Tomorrow' : DOWS[d.date.getDay()];
          return (
            <label className={enabled ? 'day-opt' : 'day-opt is-off'} key={d.date.toISOString()}>
              <input
                className="control-input"
                type="radio"
                name="day"
                value={i}
                aria-label={`${fullDayLabel(i, days)}${enabled ? '' : ', not available'}`}
                disabled={!enabled}
                checked={dayIdx === i}
                onChange={() => onSelectDay(i)}
              />
              <span className="day-in">
                <span className="day-dow">{label}</span>
                <span className="day-num">{d.date.getDate()}</span>
              </span>
            </label>
          );
        })}
      </div>
      <div className="slot-grid" key={dayIdx == null ? 'slots-idle' : `${dayIdx}:${duration}:${barberId ?? 'any'}`} role="radiogroup" aria-label="Choose a time">
        {slotsBody}
      </div>
    </section>
  );
}
