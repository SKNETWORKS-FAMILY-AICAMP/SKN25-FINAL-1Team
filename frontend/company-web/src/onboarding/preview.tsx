/**
 * 보호자 앱 병원 페이지 미리보기.
 * 운영팀이 발행 전에 "보호자에게 이렇게 보인다"를 그대로 확인하는 컴포넌트.
 * guardian-web hospitals-page 와 동일한 구성(배너·소개·진료시간·원장 카드).
 *
 * 배너 레이아웃: 오른쪽에 블러+마스크 스머지로 배치.
 * 사진 없으면 배경색만 보여 자연스럽게 처리.
 */
import type {
  DoctorApplication,
  HospitalApplication,
  OperatingHours,
} from "./types";

export function formatHours(hours: OperatingHours): string[] {
  const lines: string[] = [];
  const fmt = (label: string, v: { open: string; close: string } | null) =>
    v ? `${label} ${v.open} ~ ${v.close}` : `${label} 휴진`;
  lines.push(fmt("평일", hours.weekday));
  lines.push(fmt("토요일", hours.saturday));
  // 일요일·공휴일이 둘 다 휴진이면 한 줄로 합침
  if (hours.sunday === null && hours.holiday === null) {
    lines.push("일요일·공휴일 휴진");
  } else {
    lines.push(fmt("일요일", hours.sunday));
    lines.push(fmt("공휴일", hours.holiday));
  }
  if (hours.lunch) lines.push(`점심 ${hours.lunch.start} ~ ${hours.lunch.end}`);
  return lines;
}

function Avatar({
  src,
  name,
  className,
  fallbackClassName,
}: {
  src?: string;
  name: string;
  className: string;
  fallbackClassName: string;
}) {
  if (src) return <img src={src} alt={name} className={className} />;
  return <div className={fallbackClassName}>{name.trim().charAt(0)}</div>;
}

function InfoItem({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-4">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-1.5 whitespace-pre-line text-sm font-semibold leading-6 text-slate-700">
        {value || "정보 없음"}
      </p>
    </div>
  );
}

function DoctorCard({ doctor }: { doctor: DoctorApplication }) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <Avatar
        src={doctor.photo?.dataUrl}
        name={doctor.name || "?"}
        className="h-56 w-full object-cover object-top"
        fallbackClassName="flex h-56 w-full items-center justify-center bg-blue-50 text-5xl font-extrabold text-blue-600"
      />
      <div className="flex flex-1 flex-col p-5">
        <h3 className="text-base font-extrabold text-slate-950">{doctor.name}</h3>
        {doctor.specialty ? (
          <p className="mt-1 text-sm font-bold text-blue-600">{doctor.specialty}</p>
        ) : null}
        {doctor.education ? (
          <p className="mt-1 text-xs font-semibold text-slate-400">{doctor.education}</p>
        ) : null}
        {doctor.bio ? (
          <p className="mt-3 text-sm font-medium leading-7 text-slate-600">{doctor.bio}</p>
        ) : null}
        {doctor.specialtyAreas.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
            {doctor.specialtyAreas.map((a) => (
              <span key={a} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">
                {a}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/**
 * 병원 소개 히어로 카드 — 배너 사진이 오른쪽에 블러 스머지로 등장.
 * 사진 없으면 카드 배경색만 보여서 자연스러움.
 */
function HeroCard({ app }: { app: HospitalApplication }) {
  const hasBanner = !!app.banner?.dataUrl;

  return (
    <section className="relative overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm">
      {/* 오른쪽 배너 이미지 — 블러 마스크 스머지 */}
      {hasBanner ? (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-1/2 sm:w-2/5">
          <img
            src={app.banner!.dataUrl}
            alt={app.hospitalName}
            className="h-full w-full object-cover"
          />
          {/* 왼쪽→오른쪽 그라데이션 마스크: 카드 배경(white)에서 투명으로 */}
          <div
            className="absolute inset-0"
            style={{
              background: "linear-gradient(to right, rgba(255,255,255,1) 0%, rgba(255,255,255,0.85) 20%, rgba(255,255,255,0.4) 50%, rgba(255,255,255,0) 100%)",
            }}
          />
          {/* 추가 블러 레이어 — 부드러운 스머지 효과 */}
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
      <div className="relative z-10 p-6 sm:w-3/5">
        <h2 className="text-2xl font-extrabold text-slate-950">{app.hospitalName}</h2>
        {app.tagline ? (
          <p className="mt-2 text-sm font-bold text-blue-600">{app.tagline}</p>
        ) : null}
        {app.intro ? (
          <p className="mt-4 whitespace-pre-line text-sm font-medium leading-7 text-slate-600">
            {app.intro}
          </p>
        ) : null}
        {app.features.length > 0 ? (
          <div className="mt-5 flex flex-wrap gap-2">
            {app.features.map((f) => (
              <span key={f} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">
                {f}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function HospitalPreview({ app }: { app: HospitalApplication }) {
  return (
    <div className="space-y-6 rounded-2xl bg-slate-50 p-5">
      {/* 병원 소개 — 배너 오른쪽 블러 레이아웃 */}
      <HeroCard app={app} />

      {/* 정보 카드 */}
      <div className="grid gap-3 sm:grid-cols-3">
        <InfoItem label="진료시간" value={formatHours(app.hours).join("\n")} />
        <InfoItem label="오시는 길" value={app.hospitalAddress} />
        <InfoItem label="연락처" value={app.hospitalPhone} />
      </div>

      {/* 원장 소개 */}
      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-900">원장 소개</h2>
        {app.doctors.length > 0 ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:justify-center">
            {app.doctors.map((d) => (
              <div key={d.key} className="w-full sm:w-[calc(50%-0.5rem)]">
                <DoctorCard doctor={d} />
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border border-slate-100 bg-white py-8 text-center text-sm font-semibold text-slate-400 shadow-sm">
            등록된 원장 정보가 없습니다.
          </p>
        )}
      </section>
    </div>
  );
}
