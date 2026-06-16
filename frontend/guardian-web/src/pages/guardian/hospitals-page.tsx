import { useEffect, useRef, useState, type CSSProperties } from "react";

import PageHeader from "../../components/common/page-header";
import SectionCard from "../../components/common/section-card";
import GuardianLayout from "../../layouts/guardian-layout";
import { useTranslation } from "../../i18n/language-context";
import {
  type Hospital,
  type HospitalDoctor,
} from "../../api/hospital-mock";
import { getHospitalDetail } from "../../api/hospital-api";
import { useHospitalStore } from "../../stores/hospital-store";

const ChevronDownIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M6 9l6 6 6-6"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

/** 병원 전환 드롭다운 — 보호자가 다니는 병원을 쉽게 바꿀 수 있게. */
const HospitalSwitcher = ({
  hospitals,
  selectedId,
  onSelect,
}: {
  hospitals: { hospitalid: number; name: string }[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = hospitals.find((h) => h.hospitalid === selectedId) ?? null;

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={t("hospitalsPage.selectLabel")}
        className="flex h-11 min-w-[220px] items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 transition hover:border-slate-300"
      >
        <span className="truncate">
          {selected ? selected.name : t("hospitalsPage.selectPlaceholder")}
        </span>
        <span className="text-slate-400">
          <ChevronDownIcon />
        </span>
      </button>
      {isOpen ? (
        <div
          role="listbox"
          className="absolute right-0 z-10 mt-2 max-h-72 w-full min-w-[220px] overflow-auto rounded-2xl border border-slate-100 bg-white p-2 text-sm font-semibold shadow-xl shadow-slate-200/80"
        >
          {hospitals.map((hospital) => {
            const isActive = hospital.hospitalid === selectedId;
            return (
              <button
                key={hospital.hospitalid}
                type="button"
                role="option"
                aria-selected={isActive}
                onClick={() => {
                  onSelect(hospital.hospitalid);
                  setIsOpen(false);
                }}
                className={[
                  "flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left transition",
                  isActive
                    ? "bg-blue-50 text-blue-600"
                    : "text-slate-700 hover:bg-blue-50 hover:text-blue-600",
                ].join(" ")}
              >
                <span className="truncate">{hospital.name}</span>
                {isActive ? <span aria-hidden="true">✓</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};

/** 이미지 + 로드 실패/없음 폴백(이니셜). 배너·인물 사진 공용. */
const ImageWithFallback = ({
  src,
  alt,
  fallbackText,
  className,
  fallbackClassName,
  style,
}: {
  src?: string;
  alt: string;
  fallbackText: string;
  className: string;
  fallbackClassName: string;
  style?: CSSProperties;
}) => {
  const [errored, setErrored] = useState(false);

  if (src && !errored) {
    return (
      <img
        src={src}
        alt={alt}
        onError={() => setErrored(true)}
        className={className}
        style={style}
      />
    );
  }
  return (
    <div className={fallbackClassName} aria-label={alt}>
      {fallbackText}
    </div>
  );
};

const Tag = ({ label }: { label: string }) => (
  <span className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">
    {label}
  </span>
);

/** 병원 소개의 진료시간 / 오시는 길 / 연락처 한 칸. */
const InfoItem = ({ label, value }: { label: string; value?: string }) => {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-4">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-1.5 whitespace-pre-line text-sm font-semibold leading-6 text-slate-700">
        {value || t("hospitalsPage.infoEmpty")}
      </p>
    </div>
  );
};

const DoctorCard = ({ doctor }: { doctor: HospitalDoctor }) => {
  const { t } = useTranslation();
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <ImageWithFallback
        src={doctor.profileImage}
        alt={doctor.name}
        fallbackText={doctor.name.trim().charAt(0)}
        className="h-64 w-full object-cover"
        style={{ objectPosition: doctor.profileImagePosition || "50% 20%" }}
        fallbackClassName="flex h-64 w-full items-center justify-center bg-blue-50 text-5xl font-extrabold text-blue-600"
      />
      <div className="flex flex-1 flex-col p-6">
        <h3 className="text-lg font-extrabold text-slate-950">{doctor.name}</h3>
        {doctor.specialty ? (
          <p className="mt-1 text-sm font-bold text-blue-600">
            {doctor.specialty}
          </p>
        ) : null}
        {doctor.education ? (
          <p className="mt-1 text-xs font-semibold text-slate-400">
            {doctor.education}
          </p>
        ) : null}
        <p
          className={[
            "mt-4 text-sm font-medium leading-7",
            doctor.bio ? "text-slate-600" : "text-slate-400",
          ].join(" ")}
        >
          {doctor.bio || t("hospitalsPage.doctorBioEmpty")}
        </p>
        {doctor.specialtyAreas && doctor.specialtyAreas.length > 0 ? (
          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-xs font-bold text-slate-400">
              {t("hospitalsPage.doctorAreasTitle")}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {doctor.specialtyAreas.map((area) => (
                <Tag key={area} label={area} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
};

const HospitalDetail = ({ hospital }: { hospital: Hospital }) => {
  const { t } = useTranslation();
  const hasDoctors = hospital.doctors.length > 0;
  const hasBanner = !!hospital.bannerImage;

  return (
    <div className="space-y-6">
      {/* 병원 소개 — 배너 오른쪽 블러 스머지 */}
      <SectionCard padding="none" className="overflow-hidden">
        <div className="relative">
          {/* 오른쪽 배너 이미지 — 블러 마스크 스머지 */}
          {hasBanner ? (
            <div className="pointer-events-none absolute inset-y-0 right-0 w-1/2 sm:w-2/5">
              <ImageWithFallback
                src={hospital.bannerImage}
                alt={hospital.name}
                fallbackText={hospital.name.trim().charAt(0)}
                className="h-full w-full object-cover"
                style={{ objectPosition: hospital.bannerImagePosition || "50% 50%" }}
                fallbackClassName="h-full w-full bg-blue-50"
              />
              {/* 왼쪽→오른쪽 그라데이션 마스크 */}
              <div
                className="absolute inset-0"
                style={{
                  background: "linear-gradient(to right, rgba(255,255,255,1) 0%, rgba(255,255,255,0.85) 20%, rgba(255,255,255,0.4) 50%, rgba(255,255,255,0) 100%)",
                }}
              />
              {/* 블러 레이어 — 부드러운 스머지 */}
              <div
                className="absolute inset-0"
                style={{
                  backdropFilter: "blur(2px)",
                  WebkitBackdropFilter: "blur(2px)",
                  maskImage: "linear-gradient(to right, black 0%, transparent 60%)",
                  WebkitMaskImage: "linear-gradient(to right, black 0%, transparent 60%)",
                }}
              />
            </div>
          ) : null}

          {/* 텍스트 콘텐츠 (왼쪽) */}
          <div className="relative z-10 p-8 sm:w-3/5">
            <h2 className="text-2xl font-extrabold text-slate-950">
              {hospital.name}
            </h2>
            {hospital.tagline ? (
              <p className="mt-2 text-sm font-bold text-blue-600">
                {hospital.tagline}
              </p>
            ) : null}
            <p
              className={[
                "mt-4 whitespace-pre-line text-sm leading-7",
                hospital.intro
                  ? "font-medium text-slate-600"
                  : "font-medium text-slate-400",
              ].join(" ")}
            >
              {hospital.intro || t("hospitalsPage.introEmpty")}
            </p>

            {hospital.features && hospital.features.length > 0 ? (
              <div className="mt-5 flex flex-wrap gap-2">
                {hospital.features.map((feature) => (
                  <Tag key={feature} label={feature} />
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {/* 진료시간 / 오시는 길 / 연락처 */}
        <div className="border-t border-slate-100 px-8 pb-8 pt-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <InfoItem
              label={t("hospitalsPage.infoHours")}
              value={hospital.hours}
            />
            <InfoItem
              label={t("hospitalsPage.infoDirections")}
              value={hospital.address}
            />
            <InfoItem
              label={t("hospitalsPage.infoContact")}
              value={hospital.phone}
            />
          </div>
        </div>
      </SectionCard>

      {/* 원장 소개 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900">
            {t("hospitalsPage.doctorsTitle")}
          </h2>
          {hasDoctors ? (
            <span className="text-sm font-semibold text-slate-400">
              {t("hospitalsPage.doctorsCount", {
                count: hospital.doctors.length,
              })}
            </span>
          ) : null}
        </div>

        {/* flex-wrap + justify-center: 홀수일 때(또는 1명일 때) 마지막 카드가 가운데 정렬 */}
        {hasDoctors ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:justify-center">
            {hospital.doctors.map((doctor) => (
              <div
                key={doctor.doctorid}
                className="w-full sm:w-[calc(50%-0.5rem)]"
              >
                <DoctorCard doctor={doctor} />
              </div>
            ))}
          </div>
        ) : (
          <SectionCard>
            <p className="py-8 text-center text-sm font-semibold text-slate-400">
              {t("hospitalsPage.doctorsEmpty")}
            </p>
          </SectionCard>
        )}
      </section>
    </div>
  );
};

const HospitalsPage = () => {
  const { t } = useTranslation();

  // 현재 병원/등록 목록은 전역 store 단일 소스. (온보딩 게이트가 이미 load 완료)
  const myHospitals = useHospitalStore((state) => state.myHospitals);
  const selectedId = useHospitalStore((state) => state.currentHospitalId);
  const handleSelect = useHospitalStore((state) => state.setCurrent);
  const status = useHospitalStore((state) => state.status);

  const [hospital, setHospital] = useState<Hospital | null>(null);

  const isLoading = status === "idle" || status === "loading";

  // 선택 병원 상세 로드
  useEffect(() => {
    if (selectedId == null) {
      setHospital(null);
      return;
    }
    let mounted = true;
    getHospitalDetail(selectedId)
      .then((detail) => {
        if (mounted) setHospital(detail);
      })
      .catch(() => {
        if (mounted) setHospital(null);
      });
    return () => {
      mounted = false;
    };
  }, [selectedId]);

  return (
    <GuardianLayout>
      <PageHeader
        title={t("hospitalsPage.title")}
        description={t("hospitalsPage.description")}
        rightAction={
          myHospitals.length > 0 ? (
            <HospitalSwitcher
              hospitals={myHospitals}
              selectedId={selectedId}
              onSelect={handleSelect}
            />
          ) : undefined
        }
      />

      {isLoading ? (
        <div className="flex flex-1 min-h-[480px] items-center justify-center">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
        </div>
      ) : myHospitals.length === 0 ? (
        // 등록된 병원이 없는 보호자 — 병원 등록 유도
        <div className="flex flex-1 min-h-[480px] flex-col items-center justify-center rounded-2xl border border-slate-100 bg-white p-8 text-center shadow-sm">
          <h2 className="text-xl font-bold text-slate-800">
            {t("hospitalsPage.emptyTitle")}
          </h2>
          <p className="mx-auto mt-3 max-w-sm text-sm font-semibold leading-6 text-slate-500">
            {t("hospitalsPage.emptyDescription")}
          </p>
        </div>
      ) : hospital ? (
        <HospitalDetail hospital={hospital} />
      ) : (
        <div className="flex flex-1 min-h-[480px] items-center justify-center rounded-2xl border border-slate-100 bg-white p-8 shadow-sm">
          <p className="text-sm font-semibold text-slate-500">
            {t("hospitalsPage.noHospitals")}
          </p>
        </div>
      )}
    </GuardianLayout>
  );
};

export default HospitalsPage;
