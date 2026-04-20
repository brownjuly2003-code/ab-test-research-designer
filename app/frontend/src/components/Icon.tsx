import {
  Activity,
  AlertTriangle,
  Check,
  ChevronRight,
  Clock,
  Code2,
  Download,
  FileText,
  Info,
  Plus,
  Search,
  Trash2
} from "lucide-react";

const ICON_MAP = {
  activity: Activity,
  check: Check,
  chevron: ChevronRight,
  clock: Clock,
  code: Code2,
  download: Download,
  file: FileText,
  info: Info,
  plus: Plus,
  search: Search,
  trash: Trash2,
  warning: AlertTriangle
} as const;

type IconName = keyof typeof ICON_MAP;

type IconProps = {
  name: IconName;
  size?: number;
  className?: string;
  "aria-hidden"?: boolean;
  "aria-label"?: string;
};

export default function Icon({
  name,
  size = 16,
  className,
  "aria-hidden": ariaHidden,
  ...rest
}: IconProps) {
  const LucideIcon = ICON_MAP[name];
  const iconAriaHidden = rest["aria-label"] ? ariaHidden : ariaHidden ?? true;

  return (
    <LucideIcon
      aria-hidden={iconAriaHidden}
      className={className ?? "icon"}
      size={size}
      strokeWidth={1.5}
      {...rest}
    />
  );
}
