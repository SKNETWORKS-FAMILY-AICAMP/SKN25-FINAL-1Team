export const siteConfig = {
  // 빌드 시점 환경변수로 주입(운영 EC2 URL). 미지정 시 로컬 개발용 기본값.
  guardianWebUrl: import.meta.env.VITE_GUARDIAN_URL ?? "http://localhost:5173",
  vetWebUrl: import.meta.env.VITE_VET_URL ?? "http://localhost:5174",
  githubUrl: "https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN25-FINAL-1Team",
  companyEmail: "aoj.medipaw@gmail.com",
  contactHref: "mailto:aoj.medipaw@gmail.com?subject=MediPaw%20%ED%98%91%EC%97%85%20%EB%AC%B8%EC%9D%98",
};

export const navItems = [
  { label: "서비스", href: "#service" },
  { label: "워크플로우", href: "#workflow" },
  { label: "대시보드", href: "#dashboard" },
  { label: "팀원", href: "#team" },
  { label: "문의", href: "#contact" },
];
