import { describe, expect, it } from "vitest";

import { formatBytes, formatOptionalTimestamp, formatRevisionSource, formatUptime } from "./formatters";

const revisionLabels = {
  importedWorkspaceSnapshot: "Imported workspace snapshot",
  projectUpdate: "Project update",
  initialSave: "Initial save"
};

describe("formatUptime", () => {
  it("renders sub-minute uptime with one decimal", () => {
    expect(formatUptime(0)).toBe("0.0s");
    expect(formatUptime(59.94)).toBe("59.9s");
  });

  it("renders minutes and whole seconds below an hour", () => {
    expect(formatUptime(60)).toBe("1m 0s");
    expect(formatUptime(3599.9)).toBe("59m 59s");
  });

  it("renders hours and minutes from an hour up", () => {
    expect(formatUptime(3600)).toBe("1h 0m");
    expect(formatUptime(90061)).toBe("25h 1m");
  });

  it("treats negative and non-numeric input as zero", () => {
    expect(formatUptime(-1)).toBe("0s");
    expect(formatUptime(Number.NaN)).toBe("0s");
  });
});

describe("formatBytes", () => {
  it("keeps bytes whole and scales larger units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1.00 KB");
    expect(formatBytes(1536)).toBe("1.50 KB");
  });

  it("drops to one decimal at ten units and up", () => {
    expect(formatBytes(10 * 1024)).toBe("10.0 KB");
    expect(formatBytes(5 * 1024 ** 3)).toBe("5.00 GB");
  });

  it("stops scaling at terabytes", () => {
    expect(formatBytes(2048 * 1024 ** 4)).toBe("2048.0 TB");
  });

  it("reports unusable input as n/a", () => {
    expect(formatBytes(-1)).toBe("n/a");
    expect(formatBytes(Number.NaN)).toBe("n/a");
  });
});

describe("formatOptionalTimestamp", () => {
  it("falls back to the empty label when there is no timestamp", () => {
    expect(formatOptionalTimestamp(null, "Not recorded yet")).toBe("Not recorded yet");
    expect(formatOptionalTimestamp(undefined, "Not recorded yet")).toBe("Not recorded yet");
    expect(formatOptionalTimestamp("", "Not recorded yet")).toBe("Not recorded yet");
  });

  it("formats a present timestamp", () => {
    expect(formatOptionalTimestamp("2026-03-07T12:00:00Z", "Not recorded yet")).not.toBe("Not recorded yet");
  });
});

describe("formatRevisionSource", () => {
  it("maps the three known sources", () => {
    expect(formatRevisionSource("workspace_import", revisionLabels)).toBe("Imported workspace snapshot");
    expect(formatRevisionSource("update", revisionLabels)).toBe("Project update");
    expect(formatRevisionSource("create", revisionLabels)).toBe("Initial save");
  });

  it("treats an unknown source as the initial save", () => {
    expect(formatRevisionSource("something_else", revisionLabels)).toBe("Initial save");
  });
});
