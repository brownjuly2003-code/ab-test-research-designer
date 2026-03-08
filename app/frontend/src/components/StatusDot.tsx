type StatusDotProps = {
  online: boolean;
};

export default function StatusDot({ online }: StatusDotProps) {
  return <span aria-hidden="true" className="status-dot" data-online={String(online)} />;
}
