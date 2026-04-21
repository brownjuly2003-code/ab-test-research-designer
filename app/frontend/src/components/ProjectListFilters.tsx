import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type ProjectListFiltersProps = {
  query: string;
  status: "active" | "archived" | "all";
  metricType: "all" | "binary" | "continuous";
  sortBy: "updated_desc" | "name_asc" | "duration_asc";
  onQueryChange: (value: string) => void;
  onStatusChange: (value: "active" | "archived" | "all") => void;
  onMetricTypeChange: (value: "all" | "binary" | "continuous") => void;
  onSortByChange: (value: "updated_desc" | "name_asc" | "duration_asc") => void;
  onClearFilters: () => void;
};

export default function ProjectListFilters({
  query,
  status,
  metricType,
  sortBy,
  onQueryChange,
  onStatusChange,
  onMetricTypeChange,
  onSortByChange,
  onClearFilters,
}: ProjectListFiltersProps) {
  const { t } = useTranslation();
  const [draftQuery, setDraftQuery] = useState(query);
  const hasActiveFilters = query.trim().length > 0 || status !== "active" || metricType !== "all" || sortBy !== "updated_desc";

  useEffect(() => {
    setDraftQuery(query);
  }, [query]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (draftQuery !== query) {
        onQueryChange(draftQuery);
      }
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [draftQuery, onQueryChange, query]);

  return (
    <fieldset
      style={{
        border: 0,
        padding: 0,
        margin: "12px 0 0",
        minInlineSize: 0,
        display: "grid",
        gap: 12
      }}
    >
      <legend
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0, 0, 0, 0)",
          whiteSpace: "nowrap",
          border: 0
        }}
      >
        {t("projectListFilters.legend")}
      </legend>
      <div className="field">
        <label htmlFor="saved-projects-search">{t("projectListFilters.searchLabel")}</label>
        <input
          id="saved-projects-search"
          type="text"
          placeholder={t("projectListFilters.searchPlaceholder")}
          value={draftQuery}
          onChange={(event) => setDraftQuery(event.target.value)}
        />
      </div>
      <div
        style={{
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
          alignItems: "end",
        }}
      >
        <div className="field">
          <label htmlFor="saved-projects-status">{t("projectListFilters.statusLabel")}</label>
          <select
            id="saved-projects-status"
            value={status}
            onChange={(event) => onStatusChange(event.target.value as "active" | "archived" | "all")}
          >
            <option value="active">{t("projectListFilters.status.active")}</option>
            <option value="archived">{t("projectListFilters.status.archived")}</option>
            <option value="all">{t("projectListFilters.status.all")}</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="saved-projects-metric-type">{t("projectListFilters.metricTypeLabel")}</label>
          <select
            id="saved-projects-metric-type"
            value={metricType}
            onChange={(event) => onMetricTypeChange(event.target.value as "all" | "binary" | "continuous")}
          >
            <option value="all">{t("projectListFilters.metricType.all")}</option>
            <option value="binary">{t("projectListFilters.metricType.binary")}</option>
            <option value="continuous">{t("projectListFilters.metricType.continuous")}</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="saved-projects-sort">{t("projectListFilters.sortLabel")}</label>
          <select
            id="saved-projects-sort"
            value={sortBy}
            onChange={(event) => onSortByChange(event.target.value as "updated_desc" | "name_asc" | "duration_asc")}
          >
            <option value="updated_desc">{t("projectListFilters.sort.updated")}</option>
            <option value="name_asc">{t("projectListFilters.sort.name")}</option>
            <option value="duration_asc">{t("projectListFilters.sort.duration")}</option>
          </select>
        </div>
        <div className="actions" style={{ justifyContent: "flex-start" }}>
          <button className="btn ghost" type="button" disabled={!hasActiveFilters} onClick={onClearFilters}>
            {t("projectListFilters.clear")}
          </button>
        </div>
      </div>
    </fieldset>
  );
}
