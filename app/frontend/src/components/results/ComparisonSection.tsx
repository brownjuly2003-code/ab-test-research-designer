import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import ComparisonDetails from "./internal/ComparisonDetails";

const ComparisonDashboard = lazy(() => import("../ComparisonDashboard"));

export default function ComparisonSection() {
  const { t } = useTranslation();
  const projectComparison = useProjectStore((state) => state.projectComparison);
  const projectMultiComparison = useProjectStore((state) => state.projectMultiComparison);
  const clearComparison = useProjectStore((state) => state.clearComparison);

  if (projectMultiComparison) {
    return (
      <Suspense fallback={<div className="status">{t("comparison.loading")}</div>}>
        <ComparisonDashboard comparison={projectMultiComparison} onClose={clearComparison} />
      </Suspense>
    );
  }

  if (!projectComparison) {
    return (
      <div className="callout">
        <Icon name="info" className="icon icon-inline" />
        <span>{t("results.comparison.empty")}</span>
      </div>
    );
  }

  return <ComparisonDetails projectComparison={projectComparison} />;
}
