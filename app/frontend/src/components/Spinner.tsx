import styles from "./Spinner.module.css";

export default function Spinner() {
  return (
    <svg aria-hidden="true" className={styles.spinner} viewBox="0 0 24 24">
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeDasharray="32"
        strokeLinecap="round"
        strokeWidth="3"
      />
    </svg>
  );
}
