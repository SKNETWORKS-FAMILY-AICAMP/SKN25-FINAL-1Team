import type { TriageStatus } from "../types/emr";

export const statusStyle: Record<TriageStatus, { label: string; className: string }> = {
  emergency: {
    label: "응급",
    className: "bg-[#fcefef] text-[#e06666] border-[#f9dcdc]",
  },
  semiEmergency: {
    label: "준응급",
    className: "bg-[#faf3e1] text-[#cf9f38] border-[#f4e6bf]",
  },
  normal: {
    label: "일반",
    className: "bg-[#eef5f0] text-[#437455] border-[#d7e8dd]",
  },
};
