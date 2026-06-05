import type { TriageStatus } from "../types/emr";

export const statusStyle: Record<TriageStatus, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#fef2f2] text-[#ef4444] border-[#fee2e2]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#fffbeb] text-[#d97706] border-[#fef3c7]",
  },
  normal: {
    label: "일반",
    className: "bg-[#f0fdf4] text-[#15803d] border-[#dcfce7]",
  },
};
