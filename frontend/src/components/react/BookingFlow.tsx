import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { BARBER_MAP } from '../../data/catalog';
import { INITIAL_BOOKING_STATE, announceFor, bookingReducer } from './bookingReducer';
import { ServiceStep } from './booking/ServiceStep';
import { BarberStep } from './booking/BarberStep';
import { WhenStep } from './booking/WhenStep';
import { DetailsStep } from './booking/DetailsStep';
import { SummaryPanel } from './booking/SummaryPanel';
import { ShopNote } from './booking/ShopNote';
import { ConfirmSheet } from './booking/ConfirmSheet';

/**
 * The booking island on /book. Services and barbers render statically (no
 * dates involved); day/time UI waits for a client-only "hydrate" step because
 * the next 7 days and slot cutoffs depend on the visitor's clock.
 */
export default function BookingFlow() {
  const [state, dispatch] = useReducer(bookingReducer, INITIAL_BOOKING_STATE);
  const [sheetOpen, setSheetOpen] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    dispatch({
      type: 'hydrate',
      now: new Date(),
      service: params.get('service'),
      barber: params.get('barber'),
    });
  }, []);

  const closeSheet = useCallback(() => {
    setSheetOpen(false);
    confirmRef.current?.focus({ preventScroll: true });
  }, []);

  return (
    <div className="wrap book-grid">
      <div className="steps">
        <BarberStep selected={state.barberId} onSelect={(id) => dispatch({ type: 'pickBarber', id, now: state.now! })} />
        <ServiceStep selected={state.serviceId} onSelect={(id) => dispatch({ type: 'pickService', id, now: state.now! })} />
        <WhenStep
          days={state.days}
          now={state.now}
          dayIdx={state.dayIdx}
          time={state.time}
          barberId={state.barberId}
          serviceId={state.serviceId}
          onSelectDay={(index) => dispatch({ type: 'pickDay', index })}
          onSelectTime={(minutes) => dispatch({ type: 'pickTime', minutes, now: state.now! })}
        />
        <DetailsStep
          visible={state.time != null}
          name={state.name}
          phone={state.phone}
          onNameChange={(name) => dispatch({ type: 'setDetails', name })}
          onPhoneChange={(phone) => dispatch({ type: 'setDetails', phone })}
        />
      </div>

      <div className="book-rail">
        <SummaryPanel
          serviceId={state.serviceId}
          barber={state.barberId ? BARBER_MAP.get(state.barberId) ?? null : null}
          days={state.days}
          dayIdx={state.dayIdx}
          time={state.time}
          onConfirm={() => setSheetOpen(true)}
          confirmRef={confirmRef}
        />
        <ShopNote now={state.now} />
      </div>

      <ConfirmSheet
        open={sheetOpen}
        onClose={closeSheet}
        serviceId={state.serviceId}
        barberId={state.barberId}
        days={state.days}
        dayIdx={state.dayIdx}
        time={state.time}
        name={state.name}
      />

      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announceFor(state)}
      </div>
    </div>
  );
}
