import type { TriageStatus } from "../types/emr";

export const statusStyle: Record<TriageStatus, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-red-50 text-red-500 border-red-100",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-amber-50 text-amber-600 border-amber-100",
  },
  normal: {
    label: "일반",
    className: "bg-green-50 text-green-700 border-green-100",
  },
};
