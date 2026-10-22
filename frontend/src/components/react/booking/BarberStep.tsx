import type { Barber } from '../../../data/catalog';

export function BarberStep({ barbers, selected, onSelect }: { barbers: Barber[]; selected: string; onSelect: (id: string) => void }) {
  return <section className="step" aria-labelledby="stepBarberTitle">
    <div className="step-head"><h2 id="stepBarberTitle"><span className="step-num">1</span>Barber</h2></div>
    <div className="barber-choices" role="radiogroup" aria-labelledby="stepBarberTitle">
      {[{ id: '', name: 'First available' }, ...barbers].map((barber) => <label className="bc-opt" key={barber.id}>
        <input className="control-input" type="radio" name="barber" value={barber.id} checked={selected === barber.id} onChange={() => onSelect(barber.id)} />
        <span className="bc-in"><span className="bc-avatar first" aria-hidden="true">{barber.id ? barber.name.split(' ').map((part) => part[0]).slice(0, 2).join('') : 'Any'}</span><span className="bc-name">{barber.name}</span></span>
      </label>)}
    </div>
    <p className="step-note">Choose your barber, or we’ll match you with an available chair.</p>
  </section>;
}
