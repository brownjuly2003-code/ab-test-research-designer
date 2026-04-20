import Tooltip from "./Tooltip";
import styles from "./SliderInput.module.css";

type SliderInputProps = {
  id: string;
  label: string;
  helpText?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  onBlur?: () => void;
  ariaInvalid?: boolean;
  unit?: string;
  formatValue?: (value: number) => string;
};

export default function SliderInput({
  id,
  label,
  helpText,
  value,
  min,
  max,
  step,
  onChange,
  onBlur,
  ariaInvalid,
  unit,
  formatValue
}: SliderInputProps) {
  const displayValue = formatValue ? formatValue(value) : `${String(value)}${unit ? unit : ""}`;

  return (
    <div className={styles["slider-input-group"]}>
      <div className={styles["slider-input-label-row"]}>
        <label htmlFor={id} className={styles["field-label"]}>
          <span>{label}</span>
          {helpText ? <Tooltip content={helpText} /> : null}
        </label>
        <span className={styles["slider-input-value"]}>{displayValue}</span>
      </div>
      <div className={styles["slider-input-controls"]}>
        <input
          className={styles["slider-range-input"]}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          aria-invalid={ariaInvalid ? "true" : undefined}
          onChange={(event) => onChange(Number(event.target.value))}
          onBlur={onBlur}
          aria-label={`${label} slider`}
        />
        <input
          id={id}
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          aria-invalid={ariaInvalid ? "true" : undefined}
          onChange={(event) => {
            const rawValue = event.target.value;
            const parsedValue = rawValue === "" ? Number.NaN : Number(rawValue);
            const nextValue = Number.isFinite(parsedValue)
              ? Math.min(max, Math.max(min, parsedValue))
              : min;
            onChange(nextValue);
          }}
          onBlur={onBlur}
          className={styles["slider-number-input"]}
        />
        {unit ? <span className={styles["slider-unit"]}>{unit}</span> : null}
      </div>
    </div>
  );
}
