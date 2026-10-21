import {
  BARBER_MAP,
  SERVICE_MAP,
  type Service,
} from '../../data/catalog';
import {
  buildDays,
  dayEnabled,
  dayLabel,
  firstOpenDay,
  formatTime,
  getSlots,
  type DayInfo,
} from '../../data/availability';

export interface BookingState {
  serviceId: string | null;
  /** null means "first available barber" */
  barberId: string | null;
  /** null until the client hydrates — dates can't be known at build time */
  days: DayInfo[] | null;
  /** single client-side clock snapshot, captured once at hydrate */
  now: Date | null;
  dayIdx: number | null;
  time: number | null;
  name: string;
  phone: string;
}

export type BookingAction =
  | { type: 'hydrate'; now: Date; service?: string | null; barber?: string | null }
  | { type: 'pickService'; id: string; now: Date }
  | { type: 'pickBarber'; id: string; now: Date }
  | { type: 'pickDay'; index: number }
  | { type: 'pickTime'; minutes: number; now: Date }
  | { type: 'setDetails'; name?: string; phone?: string };

export const INITIAL_BOOKING_STATE: BookingState = {
  serviceId: null,
  barberId: null,
  days: null,
  now: null,
  dayIdx: null,
  time: null,
  name: '',
  phone: '',
};

export function announceFor(state: BookingState): string {
  if (!state.days) return '';
  const service = state.serviceId ? SERVICE_MAP.get(state.serviceId) : undefined;
  const barber = state.barberId ? BARBER_MAP.get(state.barberId) : undefined;
  let when = '—';
  if (state.dayIdx != null) {
    when = dayLabel(state.dayIdx, state.days);
    when += state.time != null ? ` · ${formatTime(state.time)}` : ' · pick a time';
  }
  const ready = !!service && state.time != null && state.dayIdx != null;
  return `${service ? service.name : 'No service yet'}. ${barber ? barber.name : 'First available'}. ${when}. ${
    ready ? `Total $${service!.price}. Ready to book.` : 'Not ready to book yet.'
  }`;
}

function serviceOf(id: string): Service | undefined {
  return SERVICE_MAP.get(id);
}

function barberOrDefault(id: string): string | null {
  return id !== 'first' && BARBER_MAP.has(id) ? id : null;
}

export function bookingReducer(state: BookingState, action: BookingAction): BookingState {
  switch (action.type) {
    case 'hydrate': {
      const days = buildDays();
      let serviceId: string | null = null;
      let barberId: string | null = null;
      if (action.service && SERVICE_MAP.has(action.service)) serviceId = action.service;
      if (action.barber && BARBER_MAP.has(action.barber)) barberId = action.barber;
      const duration = serviceId ? SERVICE_MAP.get(serviceId)!.dur : 45;
      const dayIdx = firstOpenDay(days, duration, barberId, action.now);
      return { ...state, days, now: action.now, serviceId, barberId, dayIdx, time: null };
    }

    case 'pickService': {
      if (!state.days) return state;
      const service = serviceOf(action.id);
      if (!service) return state;
      const { days, barberId, now } = state;
      let { time, dayIdx } = state;
      if (dayIdx != null) {
        const slots = getSlots(days, dayIdx, service.dur, barberId, now!);
        if (time != null && !slots.some((x) => x.minutes === time && x.free)) time = null;
        if (!slots.some((x) => x.free)) {
          dayIdx = firstOpenDay(days, service.dur, barberId, now!);
          time = null;
        }
      }
      return { ...state, serviceId: service.id, time, dayIdx };
    }

    case 'pickBarber': {
      if (!state.days) return state;
      const { days, now } = state;
      const barberId = barberOrDefault(action.id);
      const duration = state.serviceId ? SERVICE_MAP.get(state.serviceId)!.dur : 45;
      const keep =
        state.dayIdx != null &&
        dayEnabled(days, state.dayIdx, barberId) &&
        getSlots(days, state.dayIdx, duration, barberId, now!).some((x) => x.free);
      const dayIdx = keep ? state.dayIdx : firstOpenDay(days, duration, barberId, now!);
      return { ...state, barberId, time: null, dayIdx };
    }

    case 'pickDay': {
      if (!state.days) return state;
      if (!dayEnabled(state.days, action.index, state.barberId)) return state;
      return { ...state, dayIdx: action.index, time: null };
    }

    case 'pickTime': {
      if (!state.days || state.dayIdx == null) return state;
      const duration = state.serviceId ? SERVICE_MAP.get(state.serviceId)!.dur : 45;
      const slots = getSlots(state.days, state.dayIdx, duration, state.barberId, action.now);
      if (!slots.some((x) => x.minutes === action.minutes && x.free)) return state;
      return { ...state, time: action.minutes };
    }

    case 'setDetails': {
      return {
        ...state,
        name: action.name ?? state.name,
        phone: action.phone ?? state.phone,
      };
    }
  }
}
