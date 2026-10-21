import { useEffect, useRef } from 'react';
import { BARBER_MAP, SERVICE_MAP } from '../../../data/catalog';
import { formatTime, fullDayLabel, type DayInfo } from '../../../data/availability';
import { Icon } from '../Icon';

interface ConfirmSheetProps {
  open: boolean;
  onClose: () => void;
  serviceId: string | null;
  barberId: string | null;
  days: DayInfo[] | null;
  dayIdx: number | null;
  time: number | null;
  name: string;
}

export function ConfirmSheet({ open, onClose, serviceId, barberId, days, dayIdx, time, name }: ConfirmSheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
      navigator.vibrate?.(12);
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    el.addEventListener('close', onClose);
    return () => el.removeEventListener('close', onClose);
  }, [onClose]);

  useEffect(() => {
    document.body.classList.toggle('modal-open', open);
    return () => document.body.classList.remove('modal-open');
  }, [open]);

  const service = serviceId ? SERVICE_MAP.get(serviceId) : undefined;
  const barber = barberId ? BARBER_MAP.get(barberId) : undefined;
  const first = name.trim() ? name.trim().split(/\s+/)[0] : '';

  const handleClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    const el = dialogRef.current;
    if (!el) return;
    const target = e.target as HTMLElement;
    if (target.closest('[data-close]')) {
      el.close();
      return;
    }
    if (e.target === el) {
      const r = el.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) el.close();
    }
  };

  return (
    <dialog ref={dialogRef} className="sheet" aria-labelledby="sheetTitle" onClick={handleClick}>
      {service && days && dayIdx != null && time != null && (
        <>
          <button className="sheet-x" type="button" data-close aria-label="Close booking summary">
            <Icon name="x" size={18} />
          </button>
          <div className="sheet-mark" aria-hidden="true">
            <Icon name="check" size={24} className="sheet-check" />
          </div>
          <h2 id="sheetTitle">{first ? `See you soon, ${first}.` : 'See you soon.'}</h2>
          <p className="sheet-sub">
            {barber ? `${barber.name.split(' ')[0]} will have the chair ready.` : 'Your barber will have the chair ready.'}{' '}
            Here’s the plan:
          </p>
          <dl className="recap">
            <div>
              <dt>Service</dt>
              <dd>
                {service.name} · {service.dur} min
              </dd>
            </div>
            <div>
              <dt>Barber</dt>
              <dd>{barber ? barber.name : 'First available'}</dd>
            </div>
            <div>
              <dt>When</dt>
              <dd>
                {fullDayLabel(dayIdx, days)} · {formatTime(time)}
              </dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>${service.price} · pay in shop</dd>
            </div>
          </dl>
          <p className="sheet-fine">
            Free cancellation up to 4 hours before. To change it, call <a href="tel:+12125550184">(212) 555-0184</a>.
          </p>
          <button className="btn btn-block" type="button" data-close>
            Done
          </button>
          <p className="sheet-demo">Design prototype. No real booking was made.</p>
        </>
      )}
    </dialog>
  );
}
