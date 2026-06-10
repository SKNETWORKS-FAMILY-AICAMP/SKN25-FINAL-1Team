// 회사 소개(랜딩) 사이트 URL. 빌드 시 VITE_COMPANY_URL 로 주입, 미지정 시 로컬 기본값.
export const companyWebUrl =
  import.meta.env.VITE_COMPANY_URL ?? "http://localhost:5175";
