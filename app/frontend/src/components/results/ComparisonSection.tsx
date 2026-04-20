import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import ComparisonDetails from "./internal/ComparisonDetails";

export default function ComparisonSection() {
  const projectComparison = useProjectStore((state) => state.projectComparison);

  if (!projectComparison) {
    return (
      <div className="callout">
        <Icon name="info" className="icon icon-inline" />
        <span>Load a saved project comparison from the Projects sidebar to review baseline versus candidate snapshots.</span>
      </div>
    );
  }

  return <ComparisonDetails projectComparison={projectComparison} />;
}
