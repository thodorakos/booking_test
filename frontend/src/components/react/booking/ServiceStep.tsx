import { formatPrice, type Service } from '../../../data/catalog';
import { Icon } from '../Icon';

export function ServiceStep({ services, selected, onSelect }: { services: Service[]; selected: string; onSelect: (id: string) => void }) {
  return <section className="step" aria-labelledby="stepServiceTitle">
    <div className="step-head"><h2 id="stepServiceTitle"><span className="step-num">2</span>Service</h2></div>
    <div className="svc-list" role="radiogroup" aria-labelledby="stepServiceTitle">
      {services.map((service) => <label className="svc-opt" key={service.id}>
        <input className="control-input" type="radio" name="service" value={service.id} checked={selected === service.id} onChange={() => onSelect(service.id)} />
        <span className="svc-in"><span className="opt-check" aria-hidden="true"><Icon name="check" size={12} /></span><span className="opt-name">{service.name}<span className="opt-dur">{service.duration_minutes} min</span></span><span className="opt-price">{formatPrice(service.price_cents)}</span></span>
      </label>)}
    </div>
  </section>;
}
