import { formatLocalizedTimestamp } from "../../lib/formatDate";

export function formatProjectTimestamp(timestamp: string): string {
  return formatLocalizedTimestamp(timestamp);
}

export function formatOptionalTimestamp(timestamp: string | null | undefined, emptyLabel: string): string {
  return timestamp ? formatProjectTimestamp(timestamp) : emptyLabel;
}

export function formatUptime(seconds: number): string {
  if (!(seconds >= 0)) {
    return "0s";
  }

  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

export function formatBytes(bytes: number): string {
  if (!(bytes >= 0)) {
    return "n/a";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const digits = unitIndex === 0 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

export function formatRevisionSource(
  source: string,
  labels: {
    importedWorkspaceSnapshot: string;
    projectUpdate: string;
    initialSave: string;
  }
): string {
  if (source === "workspace_import") {
    return labels.importedWorkspaceSnapshot;
  }
  return source === "update" ? labels.projectUpdate : labels.initialSave;
}

export function downloadBlob(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(objectUrl);
}
