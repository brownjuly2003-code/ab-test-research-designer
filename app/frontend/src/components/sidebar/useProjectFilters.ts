import { useEffect, useState } from "react";

import type { SavedProject } from "../../lib/types";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";

export type ProjectStatusFilter = "active" | "archived" | "all";
export type ProjectMetricTypeFilter = "all" | "binary" | "continuous" | "ratio";
export type ProjectSortBy = "updated_desc" | "name_asc" | "duration_asc";

const MAX_COMPARISON_PROJECTS = 5;
const MIN_COMPARISON_PROJECTS = 2;

/**
 * Saved-project list filtering plus the multi-comparison selection.
 *
 * Lives in the sidebar shell rather than in ProjectsTab: the tab unmounts whenever the
 * operator visits System or API keys, and a search query must survive that round trip.
 */
export function useProjectFilters() {
  const allSavedProjects = useProjectStore((state) => state.savedProjects);
  const compareProjects = useProjectStore((state) => state.compareProjects);
  const showStatus = useAnalysisStore((state) => state.showStatus);

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ProjectStatusFilter>("active");
  const [metricType, setMetricType] = useState<ProjectMetricTypeFilter>("all");
  const [sortBy, setSortBy] = useState<ProjectSortBy>("updated_desc");
  const [selectedComparisonProjectIds, setSelectedComparisonProjectIds] = useState<string[]>([]);

  const normalizedQuery = query.trim().toLowerCase();

  const filteredProjects: SavedProject[] = allSavedProjects
    .filter((project) => {
      if (status === "archived") {
        return project.is_archived;
      }
      if (status === "all") {
        return true;
      }
      return !project.is_archived;
    })
    .filter((project) => (
      metricType === "all" ? true : project.metric_type === metricType
    ))
    .filter((project) => {
      if (normalizedQuery.length === 0) {
        return true;
      }
      const hypothesis = String(project.hypothesis ?? "").toLowerCase();
      return project.project_name.toLowerCase().includes(normalizedQuery) || hypothesis.includes(normalizedQuery);
    })
    .sort((left, right) => {
      if (sortBy === "name_asc") {
        return left.project_name.localeCompare(right.project_name);
      }
      if (sortBy === "duration_asc") {
        return (left.duration_days ?? Number.MAX_SAFE_INTEGER) - (right.duration_days ?? Number.MAX_SAFE_INTEGER);
      }
      return right.updated_at.localeCompare(left.updated_at);
    });

  const compareCandidates = filteredProjects.filter(
    (savedProject) => savedProject.has_analysis_snapshot && !savedProject.is_archived
  );
  const compareCandidateIdsKey = compareCandidates.map((savedProject) => savedProject.id).join("|");
  const canCompareSelected =
    selectedComparisonProjectIds.length >= MIN_COMPARISON_PROJECTS &&
    selectedComparisonProjectIds.length <= MAX_COMPARISON_PROJECTS;
  const showArchivedSection = status === "active" && normalizedQuery.length === 0 && metricType === "all";

  useEffect(() => {
    setSelectedComparisonProjectIds((current) => {
      const next = current.filter((projectId) => compareCandidates.some((projectItem) => projectItem.id === projectId));
      return next.length === current.length ? current : next;
    });
  }, [compareCandidateIdsKey]);

  function resetFilters() {
    setQuery("");
    setStatus("active");
    setMetricType("all");
    setSortBy("updated_desc");
  }

  function toggleComparisonSelection(projectId: string, selected: boolean) {
    setSelectedComparisonProjectIds((current) => {
      if (selected) {
        return current.includes(projectId) || current.length >= MAX_COMPARISON_PROJECTS
          ? current
          : [...current, projectId];
      }
      return current.filter((candidateId) => candidateId !== projectId);
    });
  }

  async function onCompareSelectedProjects() {
    if (!canCompareSelected) {
      return;
    }
    const message = await compareProjects(selectedComparisonProjectIds);
    if (message) {
      showStatus(message, "info");
    }
  }

  return {
    query,
    status,
    metricType,
    sortBy,
    setQuery,
    setStatus,
    setMetricType,
    setSortBy,
    resetFilters,
    filteredProjects,
    compareCandidates,
    canCompareSelected,
    showArchivedSection,
    selectedComparisonProjectIds,
    toggleComparisonSelection,
    onCompareSelectedProjects
  };
}

export type ProjectFilters = ReturnType<typeof useProjectFilters>;
