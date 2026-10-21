import { SERVICE_MAP, SERVICES } from '../../../data/catalog';
import { Icon } from '../Icon';

interface ServiceStepProps {
  selected: string | null;
  onSelect: (id: string) => void;
}

export function ServiceStep({ selected, onSelect }: ServiceStepProps) {
  const cats = [...new Set(SERVICES.map((s) => s.cat))];
  const service = selected ? SERVICE_MAP.get(selected) : undefined;

  return (
    <section className="step" aria-labelledby="stepServiceTitle">
      <div className="step-head">
        <h2 id="stepServiceTitle"><span className="step-num">2</span>Service</h2>
      </div>
      <div className="service-groups" role="radiogroup" aria-labelledby="stepServiceTitle">
        {cats.map((cat) => (
          <div className="svc-group" key={cat}>
            <h3>{cat}</h3>
            <div className="svc-list">
              {SERVICES.filter((s) => s.cat === cat).map((s) => (
                <label className="svc-opt" key={s.id}>
                  <input
                    className="control-input"
                    type="radio"
                    name="service"
                    value={s.id}
                    checked={selected === s.id}
                    onChange={() => onSelect(s.id)}
                  />
                  <span className="svc-in">
                    <span className="opt-check" aria-hidden="true">
                      <Icon name="check" size={12} />
                    </span>
                    <span className="opt-name">
                      {s.name}
                      <span className="opt-dur">{s.dur} min</span>
                    </span>
                    <span className="opt-price">${s.price}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="step-note" hidden={!service}>
        <span className="swap-in" key={service?.id ?? 'none'}>
          {service ? `Includes ${service.inc.join(' · ')}.` : ''}
        </span>
      </p>
    </section>
  );
}
