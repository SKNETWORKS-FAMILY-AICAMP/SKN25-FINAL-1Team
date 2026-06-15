import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Plus, Trash2 } from "lucide-react";

import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import {
  CharCount,
  Field,
  FileField,
  SectionCard,
  TagInput,
} from "../../onboarding/form-fields";
import { submitSignupRequest, uploadFile, type SignupRequestPayload } from "../../onboarding/api";
import {
  EMPTY_HOURS,
  LIMITS,
  type DayHours,
  type DoctorApplication,
  type OperatingHours,
  type UploadedFile,
} from "../../onboarding/types";

const newDoctor = (): DoctorApplication => ({
  key: `d_${Math.random().toString(36).slice(2, 9)}`,
  name: "",
  licenseNumber: "",
  specialtyAreas: [],
});

// ── 진료시간 (요일 버킷) 편집기 ──────────────────────────────
function HoursRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: DayHours | null;
  onChange: (v: DayHours | null) => void;
}) {
  const closed = value === null;
  return (
    <div className="flex flex-wrap items-center gap-3 py-1.5">
      <span className="w-20 text-sm font-extrabold text-slate-700">{label}</span>
      <label className="flex items-center gap-1.5 text-sm font-bold text-slate-500">
        <input
          type="checkbox"
          checked={closed}
          onChange={(e) => onChange(e.target.checked ? null : { open: "09:00", close: "18:00" })}
        />
        휴진
      </label>
      {!closed ? (
        <div className="flex items-center gap-2">
          <input
            type="time"
            value={value.open}
            onChange={(e) => onChange({ ...value, open: e.target.value })}
            className="contact-input w-auto py-1.5"
          />
          <span className="text-slate-400">~</span>
          <input
            type="time"
            value={value.close}
            onChange={(e) => onChange({ ...value, close: e.target.value })}
            className="contact-input w-auto py-1.5"
          />
        </div>
      ) : null}
    </div>
  );
}

function HoursEditor({
  hours,
  onChange,
}: {
  hours: OperatingHours;
  onChange: (h: OperatingHours) => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <HoursRow label="평일" value={hours.weekday} onChange={(v) => onChange({ ...hours, weekday: v })} />
      <HoursRow label="토요일" value={hours.saturday} onChange={(v) => onChange({ ...hours, saturday: v })} />
      <HoursRow label="일요일" value={hours.sunday} onChange={(v) => onChange({ ...hours, sunday: v })} />
      <HoursRow label="공휴일" value={hours.holiday} onChange={(v) => onChange({ ...hours, holiday: v })} />
      <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-slate-200 pt-3">
        <label className="flex items-center gap-1.5 text-sm font-extrabold text-slate-700">
          <input
            type="checkbox"
            checked={hours.lunch !== null}
            onChange={(e) =>
              onChange({ ...hours, lunch: e.target.checked ? { start: "12:30", end: "13:30" } : null })
            }
          />
          점심시간
        </label>
        {hours.lunch ? (
          <div className="flex items-center gap-2">
            <input
              type="time"
              value={hours.lunch.start}
              onChange={(e) => onChange({ ...hours, lunch: { ...hours.lunch!, start: e.target.value } })}
              className="contact-input w-auto py-1.5"
            />
            <span className="text-slate-400">~</span>
            <input
              type="time"
              value={hours.lunch.end}
              onChange={(e) => onChange({ ...hours, lunch: { ...hours.lunch!, end: e.target.value } })}
              className="contact-input w-auto py-1.5"
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ── 신청 페이지 ──────────────────────────────────────────────
export default function ApplyPage() {
  const [hospitalName, setHospitalName] = useState("");
  const [businessNumber, setBusinessNumber] = useState("");
  const [businessLicenseFile, setBusinessLicenseFile] = useState<UploadedFile>();
  const [hospitalPhone, setHospitalPhone] = useState("");
  const [hospitalAddress, setHospitalAddress] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [desiredLoginId, setDesiredLoginId] = useState("");

  const [tagline, setTagline] = useState("");
  const [intro, setIntro] = useState("");
  const [features, setFeatures] = useState<string[]>([]);
  const [banner, setBanner] = useState<UploadedFile>();
  const [hours, setHours] = useState<OperatingHours>(EMPTY_HOURS);

  const [doctors, setDoctors] = useState<DoctorApplication[]>([newDoctor()]);
  const [agree, setAgree] = useState(false);

  const [errors, setErrors] = useState<string[]>([]);
  const [submittedId, setSubmittedId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const updateDoctor = (key: string, patch: Partial<DoctorApplication>) =>
    setDoctors((list) => list.map((d) => (d.key === key ? { ...d, ...patch } : d)));

  const validate = (): string[] => {
    const e: string[] = [];
    if (!hospitalName.trim()) e.push("병원명을 입력해 주세요.");
    if (!/^\d{10}$/.test(businessNumber.replace(/-/g, ""))) e.push("사업자등록번호 10자리를 정확히 입력해 주세요.");
    if (!businessLicenseFile) e.push("사업자등록증 파일을 첨부해 주세요.");
    if (!hospitalPhone.trim()) e.push("대표 연락처를 입력해 주세요.");
    if (!hospitalAddress.trim()) e.push("주소를 입력해 주세요.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(ownerEmail)) e.push("대표 이메일을 정확히 입력해 주세요.");
    if (!/^[A-Za-z0-9]{4,20}$/.test(desiredLoginId)) e.push("희망 아이디는 영문·숫자 4~20자로 입력해 주세요.");
    if (!tagline.trim()) e.push("한 줄 소개를 입력해 주세요.");
    else if (tagline.length > LIMITS.tagline) e.push(`한 줄 소개는 ${LIMITS.tagline}자 이내로 입력해 주세요.`);
    if (intro.trim().length < LIMITS.introMin) e.push(`병원 소개는 ${LIMITS.introMin}자 이상 입력해 주세요.`);
    else if (intro.length > LIMITS.intro) e.push(`병원 소개는 ${LIMITS.intro}자 이내로 입력해 주세요.`);
    doctors.forEach((d, i) => {
      if (!d.name.trim()) e.push(`${i + 1}번째 원장의 이름을 입력해 주세요.`);
      if (!d.licenseNumber.trim()) e.push(`${i + 1}번째 원장의 면허번호를 입력해 주세요.`);
      if (!d.licenseFile) e.push(`${i + 1}번째 원장의 면허증 파일을 첨부해 주세요.`);
    });
    if (!agree) e.push("개인정보 수집·이용에 동의해 주세요.");
    return e;
  };

  const uploadPickedFile = async (
    picked: UploadedFile | undefined,
    prefix: "hospital" | "doctor" | "signup-docs",
  ) => {
    if (!picked?.file) return undefined;
    return uploadFile(picked.file, prefix);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const e = validate();
    setErrors(e);
    if (e.length > 0) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    setSubmitting(true);
    try {
      const businessLicenseUrl = await uploadPickedFile(businessLicenseFile, "signup-docs");
      const bannerUrl = await uploadPickedFile(banner, "hospital");
      const doctorPayloads = await Promise.all(
        doctors.map(async (doctor) => ({
          name: doctor.name.trim(),
          licenseNumber: doctor.licenseNumber.trim(),
          licenseUrl: await uploadPickedFile(doctor.licenseFile, "doctor"),
          email: doctor.email?.trim() || undefined,
          specialty: doctor.specialty?.trim() || undefined,
          education: doctor.education?.trim() || undefined,
          bio: doctor.bio?.trim() || undefined,
          specialtyAreas: doctor.specialtyAreas,
          photoUrl: await uploadPickedFile(doctor.photo, "doctor"),
        })),
      );
      const payload: SignupRequestPayload = {
        hospitalName: hospitalName.trim(),
        businessNumber: businessNumber.trim(),
        businessLicenseUrl,
        hospitalPhone: hospitalPhone.trim(),
        hospitalAddress: hospitalAddress.trim(),
        ownerEmail: ownerEmail.trim(),
        desiredLoginId: desiredLoginId.trim(),
        tagline: tagline.trim(),
        intro: intro.trim(),
        features,
        bannerUrl,
        hours,
        doctors: doctorPayloads,
      };
      const created = await submitSignupRequest(payload);
      setSubmittedId(String(created.id));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setErrors([err instanceof Error ? err.message : "입점 신청 제출에 실패했습니다."]);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      {/* 상단바 */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <img src={medipawSymbol} alt="MediPaw" className="h-9 w-auto" />
          </Link>
          <Link to="/" className="text-sm font-bold text-slate-500 transition hover:text-blue-700">
            홈으로
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
        {submittedId ? (
          <div className="rounded-2xl border border-blue-100 bg-white p-8 text-center shadow-sm">
            <CheckCircle2 className="mx-auto h-12 w-12 text-blue-600" />
            <h1 className="mt-4 text-2xl font-black text-slate-900">신청이 접수되었습니다</h1>
            <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">
              접수번호 <span className="font-black text-slate-800">{submittedId}</span>
              <br />
              운영팀이 제출하신 서류로 신원을 확인한 뒤, 입력하신 이메일로 계정 정보를 보내드립니다.
            </p>
            <Link to="/" className="mp-btn-primary mt-6">
              홈으로 돌아가기
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-blue-700">For Hospitals</p>
              <h1 className="mt-2 text-3xl font-black text-slate-950">동물병원 입점 신청</h1>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
                아래 내용은 신원 확인 후 보호자 앱의 병원 페이지에 그대로 노출됩니다. 정확하고 충실하게 작성해 주세요.
              </p>
            </div>

            {errors.length > 0 ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                <p className="text-sm font-black text-rose-700">아래 항목을 확인해 주세요</p>
                <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm font-bold text-rose-600">
                  {errors.map((msg) => (
                    <li key={msg}>{msg}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 1. 병원 정보 (신원·계정) */}
            <SectionCard step={1} title="병원 정보 · 계정" description="신원 확인 및 로그인 계정 발급에 사용됩니다. (비공개)">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="병원명" required>
                  <input className="contact-input" value={hospitalName} onChange={(e) => setHospitalName(e.target.value)} placeholder="메디포 동물병원" />
                </Field>
                <Field label="사업자등록번호" required hint="숫자 10자리">
                  <input className="contact-input" value={businessNumber} onChange={(e) => setBusinessNumber(e.target.value)} placeholder="123-45-67890" />
                </Field>
                <Field label="대표 연락처" required>
                  <input className="contact-input" value={hospitalPhone} onChange={(e) => setHospitalPhone(e.target.value)} placeholder="02-1234-5678" />
                </Field>
                <Field label="대표 이메일" required hint="계정 정보를 받을 이메일">
                  <input className="contact-input" type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} placeholder="hospital@email.com" />
                </Field>
                <Field label="주소 (오시는 길)" required>
                  <input className="contact-input" value={hospitalAddress} onChange={(e) => setHospitalAddress(e.target.value)} placeholder="서울특별시 강남구 테헤란로 123, 2층" />
                </Field>
                <Field label="희망 로그인 아이디" required hint="영문·숫자 4~20자">
                  <input className="contact-input" value={desiredLoginId} onChange={(e) => setDesiredLoginId(e.target.value)} placeholder="medipaw_gangnam" />
                </Field>
              </div>
              <div className="mt-4">
                <Field label="사업자등록증" required hint="jpg / png / pdf, 10MB 이하">
                  <FileField file={businessLicenseFile} onChange={setBusinessLicenseFile} accept="image/*,application/pdf" />
                </Field>
              </div>
            </SectionCard>

            {/* 2. 병원 소개 (공개) */}
            <SectionCard step={2} title="병원 소개" description="보호자 앱 병원 페이지에 노출되는 공개 콘텐츠입니다.">
              <div className="space-y-4">
                <Field label="한 줄 소개" required hint={<CharCount value={tagline} max={LIMITS.tagline} />}>
                  <input className="contact-input" value={tagline} onChange={(e) => setTagline(e.target.value)} placeholder="반려동물과 보호자가 안심하고 방문할 수 있는 따뜻한 진료 환경을 제공합니다." />
                </Field>
                <Field label="병원 소개 본문" required hint={<CharCount value={intro} max={LIMITS.intro} />}>
                  <textarea className="contact-input min-h-32 resize-y py-3" value={intro} onChange={(e) => setIntro(e.target.value)} placeholder="병원의 진료 철학, 주요 진료 분야, 보유 장비 등을 자유롭게 소개해 주세요. (10자 이상)" />
                </Field>
                <Field label="병원 특징" hint={`태그로 입력 (최대 ${LIMITS.features}개, 각 ${LIMITS.feature}자)`}>
                  <TagInput value={features} onChange={setFeatures} max={LIMITS.features} maxLen={LIMITS.feature} placeholder="정확한 진단, 맞춤 진료 ..." />
                </Field>
                <Field label="병원 배너 사진" hint="가로형 권장 (16:9), 5MB 이하">
                  <FileField file={banner} onChange={setBanner} accept="image/*" image />
                </Field>
              </div>
            </SectionCard>

            {/* 3. 진료시간 */}
            <SectionCard step={3} title="진료시간" description="요일별로 진료시간을 설정해 주세요. 휴진 요일은 '휴진'을 체크합니다.">
              <HoursEditor hours={hours} onChange={setHours} />
            </SectionCard>

            {/* 4. 원장 정보 */}
            <SectionCard step={4} title="원장 정보" description="원장님마다 작성해 주세요. 면허증은 신원 확인용(비공개), 나머지는 보호자에게 공개됩니다.">
              <div className="space-y-5">
                {doctors.map((doctor, idx) => (
                  <div key={doctor.key} className="rounded-xl border border-slate-200 p-4">
                    <div className="mb-4 flex items-center justify-between">
                      <h3 className="text-sm font-black text-slate-700">원장 {idx + 1}</h3>
                      {doctors.length > 1 ? (
                        <button
                          type="button"
                          onClick={() => setDoctors((list) => list.filter((d) => d.key !== doctor.key))}
                          className="flex items-center gap-1 text-xs font-bold text-rose-500 hover:text-rose-600"
                        >
                          <Trash2 className="h-3.5 w-3.5" /> 삭제
                        </button>
                      ) : null}
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="이름" required>
                        <input className="contact-input" value={doctor.name} onChange={(e) => updateDoctor(doctor.key, { name: e.target.value })} placeholder="김민지 원장" />
                      </Field>
                      <Field label="수의사 면허번호" required>
                        <input className="contact-input" value={doctor.licenseNumber} onChange={(e) => updateDoctor(doctor.key, { licenseNumber: e.target.value })} placeholder="제 12345 호" />
                      </Field>
                      <Field label="전문 진료">
                        <input className="contact-input" value={doctor.specialty ?? ""} onChange={(e) => updateDoctor(doctor.key, { specialty: e.target.value })} placeholder="내과 전문 진료" />
                      </Field>
                      <Field label="학력">
                        <input className="contact-input" value={doctor.education ?? ""} onChange={(e) => updateDoctor(doctor.key, { education: e.target.value })} placeholder="서울대학교 수의과대학 졸업" />
                      </Field>
                      <Field label="이메일" hint="연락용 (선택)">
                        <input className="contact-input" type="email" value={doctor.email ?? ""} onChange={(e) => updateDoctor(doctor.key, { email: e.target.value })} placeholder="doctor@email.com" />
                      </Field>
                      <Field label="면허증" required hint="jpg / png / pdf">
                        <FileField file={doctor.licenseFile} onChange={(f) => updateDoctor(doctor.key, { licenseFile: f })} accept="image/*,application/pdf" />
                      </Field>
                    </div>
                    <div className="mt-4 space-y-4">
                      <Field label="원장 소개" hint={<CharCount value={doctor.bio ?? ""} max={LIMITS.bio} />}>
                        <textarea className="contact-input min-h-24 resize-y py-3" value={doctor.bio ?? ""} onChange={(e) => updateDoctor(doctor.key, { bio: e.target.value })} placeholder="경력, 진료 철학 등을 소개해 주세요." />
                      </Field>
                      <Field label="전문 분야" hint={`태그 (최대 ${LIMITS.areas}개)`}>
                        <TagInput value={doctor.specialtyAreas} onChange={(v) => updateDoctor(doctor.key, { specialtyAreas: v })} max={LIMITS.areas} maxLen={LIMITS.area} placeholder="내과 진료, 노령동물 건강관리 ..." />
                      </Field>
                      <Field label="원장 사진" hint="세로 인물 권장 (3:4), 5MB 이하">
                        <FileField file={doctor.photo} onChange={(f) => updateDoctor(doctor.key, { photo: f })} accept="image/*" image />
                      </Field>
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setDoctors((list) => [...list, newDoctor()])}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 py-3 text-sm font-bold text-slate-500 transition hover:border-blue-300 hover:text-blue-600"
                >
                  <Plus className="h-4 w-4" /> 원장 추가
                </button>
              </div>
            </SectionCard>

            {/* 5. 동의 + 제출 */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <label className="flex items-start gap-2 text-sm font-bold text-slate-600">
                <input type="checkbox" className="mt-1" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
                <span>
                  신원 확인 및 서비스 제공을 위한 개인정보·서류 수집 및 이용에 동의합니다. (필수)
                </span>
              </label>
              <button type="submit" disabled={submitting} className="mp-btn-primary mt-5 w-full disabled:opacity-60">
                {submitting ? "제출 중…" : "입점 신청하기"}
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
