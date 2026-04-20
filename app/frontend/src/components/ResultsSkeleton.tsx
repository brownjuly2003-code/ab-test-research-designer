import Skeleton from "./Skeleton";

export default function ResultsSkeleton() {
  return (
    <div className="results-skeleton" aria-hidden="true">
      <div className="metric-cards-skeleton">
        {[1, 2, 3].map((item) => (
          <div key={item} className="metric-card-skeleton">
            <Skeleton height="2.5rem" width="60%" />
            <Skeleton height="0.875rem" width="80%" />
          </div>
        ))}
      </div>
      <div className="chart-skeleton">
        <Skeleton height="220px" borderRadius="8px" />
      </div>
      <div className="table-skeleton">
        <Skeleton height="160px" borderRadius="8px" />
      </div>
    </div>
  );
}
