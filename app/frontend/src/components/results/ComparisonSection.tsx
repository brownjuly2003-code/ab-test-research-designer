import { useTranslation } from "react-i18next";

import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import ComparisonDetails from "./internal/ComparisonDetails";

export default function ComparisonSection() {
  const { t } = useTranslation();
  const projectComparison = useProjectStore((state) => state.projectComparison);

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
