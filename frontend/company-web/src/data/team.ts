export interface TeamMember {
  name: string;
  role: string;
  github: string;
  contributions: string[];
}

// 각 팀원이 서비스 전반에 골고루 기여했다는 점이 드러나도록,
// 기여 항목을 2개씩 균형 있게 정리했다. github 은 개인 프로필 링크.
export const teamMembers: TeamMember[] = [
  {
    name: "김지현",
    role: "Frontend",
    github: "https://github.com/dora-ignita",
    contributions: ["보호자 웹 UI 구현", "문진·예약 플로우 화면 설계"],
  },
  {
    name: "박지현",
    role: "Frontend",
    github: "https://github.com/qkrwlgus89",
    contributions: ["수의사 웹 UI 구현", "대시보드·EMR 화면 설계"],
  },
  {
    name: "조민서",
    role: "Backend · AI",
    github: "https://github.com/mllnxeo",
    contributions: ["API·ERD/DB 스키마 설계", "모델 파인튜닝"],
  },
  {
    name: "이채림",
    role: "Backend · AI",
    github: "https://github.com/chaechae18",
    contributions: ["API·DB 설계", "AI Agent 리팩토링·모델 파인튜닝"],
  },
  {
    name: "김찬영",
    role: "AI · DevOps",
    github: "https://github.com/Chyoung812",
    contributions: ["Multi-Agent 파이프라인 설계", "보호자 웹·AWS 배포"],
  },
];
