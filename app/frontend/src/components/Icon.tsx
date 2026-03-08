type IconName =
  | "activity"
  | "check"
  | "chevron"
  | "clock"
  | "code"
  | "download"
  | "file"
  | "info"
  | "plus"
  | "search"
  | "trash"
  | "warning";

type IconProps = {
  name: IconName;
  className?: string;
};

function iconPath(name: IconName) {
  switch (name) {
    case "activity":
      return (
        <path
          d="M3 12h4l2.5-5 4 10 2.5-5H21"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      );
    case "check":
      return (
        <path
          d="M5 12.5 9.5 17 19 7.5"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      );
    case "chevron":
      return (
        <path
          d="M9 6 15 12 9 18"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      );
    case "clock":
      return (
        <>
          <circle cx="12" cy="12" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="M12 7.5v5l3.5 2"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
        </>
      );
    case "code":
      return (
        <path
          d="m8 7-4 5 4 5m8-10 4 5-4 5"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      );
    case "download":
      return (
        <>
          <path
            d="M12 4v10"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.8"
          />
          <path
            d="m8.5 10.5 3.5 3.5 3.5-3.5"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
          <path
            d="M5 19h14"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.8"
          />
        </>
      );
    case "file":
      return (
        <>
          <path
            d="M8 3.5h6l4 4V20.5H8a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2Z"
            fill="none"
            stroke="currentColor"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
          <path
            d="M14 3.5v5h5"
            fill="none"
            stroke="currentColor"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
        </>
      );
    case "info":
      return (
        <>
          <circle cx="12" cy="12" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path d="M12 10v5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
          <circle cx="12" cy="7.25" r="1" fill="currentColor" />
        </>
      );
    case "plus":
      return (
        <path
          d="M12 5v14M5 12h14"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.8"
        />
      );
    case "search":
      return (
        <>
          <circle cx="11" cy="11" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="m16 16 4 4"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.8"
          />
        </>
      );
    case "trash":
      return (
        <>
          <path
            d="M5 7h14"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.8"
          />
          <path
            d="M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2m-7 0 1 11h6l1-11"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
        </>
      );
    case "warning":
      return (
        <>
          <path
            d="m12 4 8 15H4Z"
            fill="none"
            stroke="currentColor"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
          <path d="M12 9v4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
          <circle cx="12" cy="16.2" r="1" fill="currentColor" />
        </>
      );
  }
}

export default function Icon({ name, className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className={className ?? "icon"}
      viewBox="0 0 24 24"
      fill="none"
    >
      {iconPath(name)}
    </svg>
  );
}
