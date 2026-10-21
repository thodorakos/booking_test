import { SERVICE_MAP, type Barber } from '../../../data/catalog';
import { dayLabel, formatTime, type DayInfo } from '../../../data/availability';

interface SummaryPanelProps {
  serviceId: string | null;
  barber: Barber | null;
  days: DayInfo[] | null;
  dayIdx: number | null;
  time: number | null;
  onConfirm: () => void;
  confirmRef: React.RefObject<HTMLButtonElement | null>;
}

export function SummaryPanel({ serviceId, barber, days, dayIdx, time, onConfirm, confirmRef }: SummaryPanelProps) {
  const service = serviceId ? SERVICE_MAP.get(serviceId) : undefined;

  let when = '—';
  if (days && dayIdx != null) {
    when = dayLabel(dayIdx, days);
    when += time != null ? ` · ${formatTime(time)}` : ' · pick a time';
  }

  const ready = !!service && time != null && dayIdx != null;
  const label = ready
    ? 'Confirm booking'
    : days === null
      ? 'Choose a service and a time'
      : dayIdx == null
        ? 'No times available'
        : !service && time == null
          ? 'Choose a service and a time'
          : !service
            ? 'Choose a service'
            : 'Choose a time';

  return (
    <aside className="summary" aria-labelledby="summaryTitle">
      <h2 id="summaryTitle">Your visit</h2>
      <dl>
        <div>
          <dt>Service</dt>
          <dd>
            <span className="swap-in" key={serviceId ?? 'none'}>
              {service ? service.name : '—'}
            </span>
          </dd>
        </div>
        <div>
          <dt>Barber</dt>
          <dd>
            <span className="swap-in" key={barber?.id ?? 'first-available'}>{barber ? barber.name : 'First available'}</span>
          </dd>
        </div>
        <div>
          <dt>When</dt>
          <dd>
            <span className="swap-in" key={when}>{when}</span>
          </dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>
            <span className="swap-in" key={service ? `${service.dur}` : 'none'}>
              {service ? `${service.dur} min` : '—'}
            </span>
          </dd>
        </div>
      </dl>
      <div className="sum-total">
        <span>Total</span>
        <strong>
          <span className="swap-in" key={serviceId ?? 'none'}>{service ? `$${service.price}` : '—'}</span>
        </strong>
      </div>
      <p className="pay-note">Pay in the shop by card or cash.</p>
      <button className="btn btn-block" type="button" ref={confirmRef} disabled={!ready} onClick={onConfirm}>
        <span className="swap-in" key={label}>{label}</span>
      </button>
      <p className="cancel-note">
        Free cancellation up to 4 hours before. <a href="tel:+12125550184">Call the shop</a> to change.
      </p>
    </aside>
  );
}
