type ProgressBarProps = {
  currentStep: number;
  totalSteps: number;
};

export default function ProgressBar({ currentStep, totalSteps }: ProgressBarProps) {
  const safeTotal = Math.max(totalSteps, 1);
  const progress = Math.min(100, Math.max(0, (currentStep / safeTotal) * 100));

  return (
    <div aria-hidden="true" className="progress-track">
      <div className="progress-fill" style={{ width: `${progress}%` }} />
    </div>
  );
}
