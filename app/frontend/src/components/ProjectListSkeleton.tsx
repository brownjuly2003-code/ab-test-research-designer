import Skeleton from "./Skeleton";

export default function ProjectListSkeleton() {
  return (
    <div className="project-list-skeleton" aria-hidden="true">
      {[1, 2, 3].map((item) => (
        <div key={item} className="project-skeleton-item">
          <Skeleton height="1rem" width="70%" />
          <Skeleton height="0.75rem" width="40%" />
        </div>
      ))}
    </div>
  );
}
