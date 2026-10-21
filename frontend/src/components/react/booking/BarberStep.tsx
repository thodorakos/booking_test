import { BARBERS, type Barber } from '../../../data/catalog';

interface BarberStepProps {
  /** null means "first available" */
  selected: string | null;
  onSelect: (id: string) => void;
}

export function BarberStep({ selected, onSelect }: BarberStepProps) {
  const barber: Barber | undefined = selected ? BARBERS.find((b) => b.id === selected) : undefined;

  return (
    <section className="step" aria-labelledby="stepBarberTitle">
      <div className="step-head">
        <h2 id="stepBarberTitle"><span className="step-num">1</span>Barber</h2>
      </div>
      <div className="barber-choices" role="radiogroup" aria-labelledby="stepBarberTitle">
        <label className="bc-opt">
          <input
            className="control-input"
            type="radio"
            name="barber"
            value="first"
            aria-label="First available barber"
            checked={!selected}
            onChange={() => onSelect('first')}
          />
          <span className="bc-in">
            <span className="bc-avatar first" aria-hidden="true">
              Any
            </span>
            <span className="bc-name">First available</span>
          </span>
        </label>
        {BARBERS.map((b) => (
          <label className="bc-opt" key={b.id}>
            <input
              className="control-input"
              type="radio"
              name="barber"
              value={b.id}
              aria-label={b.name}
              checked={selected === b.id}
              onChange={() => onSelect(b.id)}
            />
            <span className="bc-in">
              <span className="bc-avatar">
                <img src={b.thumb} alt="" width="160" height="160" loading="lazy" decoding="async" />
              </span>
              <span className="bc-name">{b.name.split(' ')[0]}</span>
            </span>
          </label>
        ))}
      </div>
      <p className="step-note">
        <span className="swap-in" key={barber?.id ?? 'first'}>
          {barber ? `${barber.spec}. In the shop ${barber.days}.` : 'We’ll match you with the first open chair.'}
        </span>
      </p>
    </section>
  );
}
