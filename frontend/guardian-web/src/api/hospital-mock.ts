/**
 * 병원 / 원장 타입.
 *
 * 운영팀이 병원 등록 시 입력한 "병원 소개 / 진료시간 / 사진"과 "원장 사진·소개·전문분야"를
 * 백엔드 hospital API 로 받아올 때의 응답 형태 정의. (보호자가 작성하는 데이터가 아니다.)
 * hospital-api.ts(getHospitalDetail)·hospitals-page·checkup-reservation-modal 이 이 타입을 사용한다.
 *
 * (과거 화면 상태 확인용 MOCK_HOSPITALS 더미 데이터는 실제 API(getHospitalDetail) 연동으로
 *  미사용이 되어 제거함. 타입만 유지.)
 */

export interface HospitalDoctor {
  doctorid: number;
  name: string;
  /** 전문 진료 (예: "내과 전문 진료") */
  specialty?: string;
  /** 학력 (예: "서울대학교 수의과대학 졸업") */
  education?: string;
  /** 소개글 */
  bio?: string;
  /** 전문 분야 태그 */
  specialtyAreas?: string[];
  /** 사진 URL (없거나 로드 실패 시 이니셜 아바타로 폴백) */
  profileImage?: string;
  /** 사진 초점 (CSS object-position "x% y%"). 운영팀이 조정. */
  profileImagePosition?: string;
}

export interface Hospital {
  hospitalid: number;
  name: string;
  /** 한 줄 소개 */
  tagline?: string;
  /** 병원 소개 본문 (운영팀이 등록, 여러 단락 가능) */
  intro?: string;
  /** 오시는 길 (backend: hospital_address) */
  address?: string;
  /** 연락처 (backend: hospital_number) */
  phone?: string;
  /** 진료시간 — 여러 줄 가능. 아직 백엔드 필드 없음(목업). */
  hours?: string;
  /** 병원 배너 이미지 URL */
  bannerImage?: string;
  /** 배너 초점 (CSS object-position "x% y%"). 운영팀이 조정. */
  bannerImagePosition?: string;
  /** 병원 특징 태그 */
  features?: string[];
  doctors: HospitalDoctor[];
}
