/**
 * 병원 / 원장 목업 데이터.
 *
 * ⚠️ 임시: 실제 서비스에서는 운영팀이 병원을 등록(아이디·비번 발급)할 때 함께
 * 입력받은 "병원 소개 / 진료시간 / 사진"과 "원장 사진·소개·전문분야"를 백엔드
 * API로 받아온다. 보호자가 작성하는 데이터가 아니다. 백엔드 API가 확정되면 이
 * 파일을 hospital-api 호출로 교체한다. (구조는 향후 API 응답과 동일하게 맞춰 둠)
 *
 * 이미지는 public/assets 아래에 둔다(운영팀이 업로드한 파일이라고 가정):
 *   /assets/hospitals/medipaw-reception.png   ← 병원 배너
 *   /assets/doctors/kim-minji.png             ← 김민지 원장
 *   /assets/doctors/park-seojun.png           ← 박서준 원장
 * 파일이 아직 없으면 화면에서 자동으로 폴백(이니셜)로 표시된다.
 *
 * 화면이 처리해야 하는 상태:
 *  ④ 풀 데이터 + 원장 여러 명               → hospitalid 1 (메디포 동물병원)
 *  ③ 소개 + 원장 1명                        → hospitalid 2
 *  ② 소개만, 원장 정보 없음                 → hospitalid 3
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

export const MOCK_HOSPITALS: Hospital[] = [
  // ④ 풀 데이터 + 원장 2명 (운영팀이 받은 실제 형태 가정)
  {
    hospitalid: 1,
    name: "메디포 동물병원",
    tagline:
      "반려동물과 보호자가 안심하고 방문할 수 있는 따뜻한 진료 환경을 제공합니다.",
    intro:
      "메디포 동물병원은 내과, 외과, 예방의학을 중심으로 반려동물의 건강을 종합적으로 관리하는 동물병원입니다. " +
      "정확한 진단과 충분한 상담을 바탕으로 보호자와 함께 최선의 치료 방향을 고민하며, 예방부터 치료, 사후 관리까지 책임 있는 진료를 제공합니다.\n\n" +
      "소중한 가족인 반려동물이 건강하고 행복한 삶을 이어갈 수 있도록 언제나 최선을 다하겠습니다.",
    address: "서울특별시 강남구 테헤란로 123, 2층",
    phone: "02-1234-5678",
    hours: "평일 09:00 ~ 20:00\n토요일 09:00 ~ 18:00\n일요일·공휴일 휴진",
    bannerImage: "/assets/hospitals/medipaw-reception.png",
    features: ["정확한 진단", "맞춤 진료", "친절한 상담", "예방 중심 의료"],
    doctors: [
      {
        doctorid: 11,
        name: "김민지 원장",
        specialty: "내과 전문 진료",
        education: "서울대학교 수의과대학 졸업",
        bio:
          "10년 이상의 임상 경험을 바탕으로 반려동물의 만성질환, 소화기 질환, 피부질환 및 노령동물 건강관리를 전문적으로 진료하고 있습니다. " +
          "보호자가 충분히 이해할 수 있도록 자세히 설명하고, 반려동물의 삶의 질 향상을 최우선으로 생각합니다.",
        specialtyAreas: ["내과 진료", "노령동물 건강관리", "소화기 질환", "예방의학"],
        profileImage: "/assets/doctors/kim-minji.png",
      },
      {
        doctorid: 12,
        name: "박서준 원장",
        specialty: "외과 전문 진료",
        education: "서울대학교 수의과대학 졸업",
        bio:
          "다양한 외과 수술 및 응급 진료 경험을 바탕으로 안전하고 정확한 수술을 제공하고 있습니다. " +
          "수술 전후 보호자와 충분히 소통하며 반려동물의 빠른 회복을 위해 체계적인 관리 프로그램을 운영하고 있습니다.",
        specialtyAreas: ["일반 외과 수술", "정형외과", "응급 진료", "외상 치료"],
        profileImage: "/assets/doctors/park-seojun.png",
      },
    ],
  },
  // ③ 소개 + 원장 1명(사진·소개 있음)
  {
    hospitalid: 2,
    name: "튼튼 동물메디컬센터",
    tagline: "분당 판교의 야간 응급 진료 전문 동물병원입니다.",
    intro:
      "예방접종부터 응급처치까지 신속하고 따뜻한 진료를 제공합니다. 24시간 응급 대응 체계를 운영합니다.",
    address: "경기도 성남시 분당구 판교역로 45",
    phone: "031-987-6543",
    hours: "평일 10:00 ~ 22:00\n24시간 응급 진료 운영",
    features: ["야간 응급", "신속 대응"],
    doctors: [
      {
        doctorid: 21,
        name: "최유진 원장",
        specialty: "내과 · 응급",
        education: "건국대학교 수의과대학 졸업",
        bio: "응급의학 세부전공. 중증 환자 케어와 24시간 응급 대응에 집중합니다.",
        specialtyAreas: ["응급 진료", "내과", "중환자 관리"],
      },
    ],
  },
  // ② 병원 소개만, 등록된 원장 정보 없음
  {
    hospitalid: 3,
    name: "초록발자국 동물병원",
    tagline: "해운대 센텀시티의 반려동물 전문 병원입니다.",
    intro:
      "편안한 환경에서 정기 건강검진과 예방 진료를 받아보세요.",
    address: "부산광역시 해운대구 센텀중앙로 90",
    phone: "051-222-3333",
    hours: "평일 09:30 ~ 19:00\n일요일 휴진",
    doctors: [],
  },
];
