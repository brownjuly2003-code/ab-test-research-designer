import styles from "./StatusDot.module.css";

type StatusDotProps = {
  online: boolean;
};

export default function StatusDot({ online }: StatusDotProps) {
  return <span aria-hidden="true" className={styles["status-dot"]} data-online={String(online)} />;
}
