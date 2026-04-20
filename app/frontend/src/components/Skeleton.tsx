import styles from "./Skeleton.module.css";

type SkeletonProps = {
  width?: string | number;
  height?: string | number;
  borderRadius?: string;
  className?: string;
};

export default function Skeleton({
  width = "100%",
  height = "1rem",
  borderRadius = "4px",
  className
}: SkeletonProps) {
  return (
    <div
      className={[styles.skeleton, className].filter(Boolean).join(" ")}
      style={{ width, height, borderRadius }}
      aria-hidden="true"
    />
  );
}
