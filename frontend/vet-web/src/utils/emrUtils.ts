import type { TriageStatus } from "../types/emr";

export const statusStyle: Record<TriageStatus, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#fff1f2] text-[#ef4444] border-[#fecdd3]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#fff7ed] text-[#f97316] border-[#fed7aa]",
  },
  normal: {
    label: "일반",
    className: "bg-[#f6fbf8] text-[#3f7f5f] border-[#cfe3d7]",
  },
};
