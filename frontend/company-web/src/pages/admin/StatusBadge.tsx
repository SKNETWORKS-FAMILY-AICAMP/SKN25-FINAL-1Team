import type { ApplicationStatus } from "../../onboarding/types";

const styles: Record<ApplicationStatus, string> = {
  접수: "bg-sky-50 text-sky-700",
  검토중: "bg-amber-50 text-amber-700",
  승인발행: "bg-green-50 text-green-700",
  반려: "bg-rose-50 text-rose-600",
};

export default function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-black ${styles[status]}`}>
      {status}
    </span>
  );
}
