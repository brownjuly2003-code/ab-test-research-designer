export default function Spinner() {
  return (
    <svg aria-hidden="true" className="spinner" viewBox="0 0 24 24">
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
