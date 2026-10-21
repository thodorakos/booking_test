interface DetailsStepProps {
  visible: boolean;
  name: string;
  phone: string;
  onNameChange: (name: string) => void;
  onPhoneChange: (phone: string) => void;
}

export function DetailsStep({ visible, name, phone, onNameChange, onPhoneChange }: DetailsStepProps) {
  return (
    <section className="step" id="stepDetails" aria-labelledby="stepDetailsTitle" hidden={!visible}>
      <div className="step-head">
        <h2 id="stepDetailsTitle">
          <span className="step-num">4</span>Details <span className="opt-tag">Optional</span>
        </h2>
      </div>
      <div className="fields">
        <div className="field">
          <label htmlFor="fName">Name</label>
          <input
            id="fName"
            type="text"
            placeholder="Who’s in the chair?"
            autoComplete="name"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="fPhone">Mobile</label>
          <input
            id="fPhone"
            type="tel"
            inputMode="tel"
            placeholder="For a reminder text"
            autoComplete="tel"
            value={phone}
            onChange={(e) => onPhoneChange(e.target.value)}
          />
        </div>
      </div>
    </section>
  );
}
