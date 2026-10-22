export interface Barber { id: string; name: string }
export interface Service { id: string; name: string; duration_minutes: number; price_cents: number | null }
export interface AdminBarber extends Barber { is_active: boolean }
export interface AdminService extends Service { is_active: boolean }
export interface Shop {
  timezone: string;
  currency: string;
  open_time: string;
  close_time: string;
  closed_weekdays: number[];
  booking_horizon_days: number;
  booking_lead_minutes: number;
  cancel_cutoff_hours: number;
}
export interface Slot { starts_at: string; starts_at_local: string }
export interface AvailableSlot extends Slot { barber_id: string; barber_name: string }
export interface Availability {
  barber_id: string; barber_name: string; closed: boolean; available: Slot[];
}
export interface Booking {
  id: string; status: string; barber_id: string; barber_name: string;
  service_id: string; service_name: string; duration_minutes: number; price_cents: number | null;
  starts_at: string; ends_at: string; starts_at_local: string; ends_at_local: string;
  customer_name: string; customer_phone: string; notes: string | null;
  cancellation_reason: string | null;
}
export interface BookingInput {
  barber_id: string; service_id: string; starts_at: string;
  customer_name: string; customer_phone: string;
}
export function formatPrice(cents: number | null, currency = 'EUR'): string {
  return cents == null ? 'Ask in shop' : new Intl.NumberFormat('en-IE', { style: 'currency', currency }).format(cents / 100);
}
