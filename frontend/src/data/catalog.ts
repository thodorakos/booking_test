export interface Service {
  id: string;
  cat: 'Cuts' | 'Shave & Beard' | 'Treatments';
  name: string;
  dur: number;
  price: number;
  inc: string[];
}

export const SERVICES: Service[] = [
  { id: 'signature', cat: 'Cuts', name: 'Signature Cut', dur: 45, price: 65, inc: ['Consultation & wash', 'Precision cut', 'Hot-towel finish', 'Styled to go'] },
  { id: 'skinfade', cat: 'Cuts', name: 'Skin Fade', dur: 40, price: 58, inc: ['Foil & scissor work', 'Razor line-up', 'Style & product'] },
  { id: 'scissor', cat: 'Cuts', name: 'Classic Scissor Cut', dur: 50, price: 70, inc: ['Wash & condition', 'Full scissor cut', 'Blow-dry finish'] },
  { id: 'buzz', cat: 'Cuts', name: 'Buzz & Shape', dur: 20, price: 35, inc: ['Clipper cut', 'Edge-up', 'Neck shave'] },
  { id: 'kids', cat: 'Cuts', name: 'Kid’s Cut', dur: 30, price: 40, inc: ['Patient barber', 'Cut & style', 'One lollipop'] },
  { id: 'shave', cat: 'Shave & Beard', name: 'Hot Towel Shave', dur: 30, price: 50, inc: ['Three hot towels', 'Straight-razor shave', 'Cold towel & balm'] },
  { id: 'beard', cat: 'Shave & Beard', name: 'Beard Sculpt', dur: 25, price: 38, inc: ['Shape & line', 'Razor edges', 'Oil finish'] },
  { id: 'cutbeard', cat: 'Shave & Beard', name: 'Cut + Beard', dur: 70, price: 92, inc: ['Full signature cut', 'Beard sculpt', 'Hot-towel finish'] },
  { id: 'grey', cat: 'Treatments', name: 'Grey Blend', dur: 30, price: 30, inc: ['Colour match', 'Low-maintenance blend', 'Five-minute rinse'] },
  { id: 'scalp', cat: 'Treatments', name: 'Scalp Therapy', dur: 30, price: 42, inc: ['Deep cleanse', 'Ten-minute massage', 'Tonic finish'] },
];

export const SERVICE_MAP = new Map(SERVICES.map((s) => [s.id, s]));

export interface Barber {
  id: string;
  name: string;
  spec: string;
  days: string;
  photo: string;
  thumb: string;
  photoAlt: string;
}

export const BARBERS: Barber[] = [
  {
    id: 'marcus', name: 'Marcus Bell', spec: 'Skin fades · Classic cuts · Beard work', days: 'Tue – Sat',
    photo: 'https://images.unsplash.com/photo-1682989356229-a244c8903492?q=80&w=560&h=700&fit=crop&auto=format',
    thumb: 'https://images.unsplash.com/photo-1682989356229-a244c8903492?q=80&w=160&h=160&fit=crop&auto=format',
    photoAlt: 'A skin fade being shaped with clippers',
  },
  {
    id: 'dario', name: 'Dario Ferretti', spec: 'Scissor work · Texture · Long styles', days: 'Wed – Sat',
    photo: 'https://images.pexels.com/photos/4862662/pexels-photo-4862662.jpeg?auto=compress&cs=tinysrgb&w=560&h=700&fit=crop',
    thumb: 'https://images.pexels.com/photos/4862662/pexels-photo-4862662.jpeg?auto=compress&cs=tinysrgb&w=160&h=160&fit=crop',
    photoAlt: 'Scissor-over-comb work in progress',
  },
  {
    id: 'june', name: 'June Park', spec: 'Skin fades · Crops · Kid’s cuts', days: 'Tue – Sat',
    photo: 'https://images.pexels.com/photos/6599031/pexels-photo-6599031.jpeg?auto=compress&cs=tinysrgb&w=560&h=700&fit=crop',
    thumb: 'https://images.pexels.com/photos/6599031/pexels-photo-6599031.jpeg?auto=compress&cs=tinysrgb&w=160&h=160&fit=crop',
    photoAlt: 'A barber talking through a cut with a client',
  },
  {
    id: 'elias', name: 'Elias Ward', spec: 'Straight razor · Beard · Grey blend', days: 'Thu – Sat',
    photo: 'https://images.unsplash.com/photo-1717089256239-dc2ed4d9dfc6?q=80&w=560&h=700&fit=crop&auto=format',
    thumb: 'https://images.unsplash.com/photo-1717089256239-dc2ed4d9dfc6?q=80&w=160&h=160&fit=crop&auto=format',
    photoAlt: 'A straight-razor shave in the chair',
  },
];

export const BARBER_MAP = new Map(BARBERS.map((b) => [b.id, b]));
