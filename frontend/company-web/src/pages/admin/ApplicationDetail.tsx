import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText, KeyRound, Pencil, Plus, Save, Trash2, X } from "lucide-react";

import {
  CharCount,
  Field,
  FileField,
  TagInput,
} from "../../onboarding/form-fields";
import { generateTempPassword, getApplication, updateApplication, setStatus } from "../../onboarding/store";
import { HospitalPreview } from "../../onboarding/preview";
import type { DoctorApplication, HospitalApplication, UploadedFile } from "../../onboarding/types";
import { LIMITS } from "../../onboarding/types";
import StatusBadge from "./StatusBadge";

/* ── 작은 유틸 컴포넌트 ── */
function DocChip({ label, file }: { label: string; file?: UploadedFile }) {
  if (!file) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-xs font-bold text-slate-400">
        {label}: 미첨부
      </div>
    );
  }
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
      {file.dataUrl ? (
        <img src={file.dataUrl} alt={file.name} className="h-12 w-12 rounded-lg object-cover" />
      ) : (
        <FileText className="h-8 w-8 text-slate-400" />
      )}
      <div className="min-w-0">
        <p className="text-xs font-bold text-slate-400">{label}</p>
        <p className="truncate text-sm font-bold text-slate-700">{file.name}</p>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-bold text-slate-800">{value || "-"}</p>
    </div>
  );
}

const newDoctor = (): DoctorApplication => ({
  key: `d_${Math.random().toString(36).slice(2, 9)}`,
  name: "",
  licenseNumber: "",
  specialtyAreas: [],
});

/* ── 운영진 편집 폼 ── */
function EditForm({
  app,
  onSave,
  onCancel,
}: {
  app: HospitalApplication;
  onSave: (updated: HospitalApplication) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<HospitalApplication>({ ...app, doctors: app.doctors.map((d) => ({ ...d })) });

  const set = <K extends keyof HospitalApplication>(key: K, value: HospitalApplication[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const updateDoctor = (key: string, patch: Partial<DoctorApplication>) =>
    setDraft((prev) => ({
      ...prev,
      doctors: prev.doctors.map((d) => (d.key === key ? { ...d, ...patch } : d)),
    }));

  const removeDoctor = (key: string) =>
    setDraft((prev) => ({ ...prev, doctors: prev.doctors.filter((d) => d.key !== key) }));

  const addDoctor = () =>
    setDraft((prev) => ({ ...prev, doctors: [...prev.doctors, newDoctor()] }));

  const handleSave = () => {
    const updated = updateApplication(draft.id, draft);
    if (updated) onSave(updated);
  };

  return (
    <div className="space-y-5">
      {/* 병원 공개 콘텐츠 */}
      <section className="rounded-2xl border border-blue-100 bg-blue-50/30 p-5">
        <h3 className="mb-4 text-sm font-black text-blue-800">병원 공개 콘텐츠 수정</h3>
        <div className="space-y-4">
          <Field label="병원명" required>
            <input
              className="contact-input"
              value={draft.hospitalName}
              onChange={(e) => set("hospitalName", e.target.value)}
            />
          </Field>
          <Field label="한 줄 소개" required hint={<CharCount value={draft.tagline} max={LIMITS.tagline} />}>
            <input
              className="contact-input"
              value={draft.tagline}
              onChange={(e) => set("tagline", e.target.value)}
            />
          </Field>
          <Field label="병원 소개 본문" required hint={<CharCount value={draft.intro} max={LIMITS.intro} />}>
            <textarea
              className="contact-input min-h-28 resize-y py-3"
              value={draft.intro}
              onChange={(e) => set("intro", e.target.value)}
            />
          </Field>
          <Field label="병원 특징" hint={`태그 (최대 ${LIMITS.features}개)`}>
            <TagInput
              value={draft.features}
              onChange={(v) => set("features", v)}
              max={LIMITS.features}
              maxLen={LIMITS.feature}
              placeholder="특징 입력"
            />
          </Field>
          <Field label="배너 사진" hint="변경 시 새 이미지 선택">
            <FileField file={draft.banner} onChange={(f) => set("banner", f)} accept="image/*" image />
          </Field>
        </div>
      </section>

      {/* 신원·계정 정보 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-black text-slate-700">신원·계정 정보 수정</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="대표 연락처" required>
            <input className="contact-input" value={draft.hospitalPhone} onChange={(e) => set("hospitalPhone", e.target.value)} />
          </Field>
          <Field label="대표 이메일" required>
            <input className="contact-input" type="email" value={draft.ownerEmail} onChange={(e) => set("ownerEmail", e.target.value)} />
          </Field>
          <Field label="주소" required>
            <input className="contact-input" value={draft.hospitalAddress} onChange={(e) => set("hospitalAddress", e.target.value)} />
          </Field>
          <Field label="사업자등록번호">
            <input className="contact-input" value={draft.businessNumber} onChange={(e) => set("businessNumber", e.target.value)} />
          </Field>
        </div>
      </section>

      {/* 원장 정보 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-black text-slate-700">원장 정보 수정</h3>
          <button
            type="button"
            onClick={addDoctor}
            className="flex items-center gap-1 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 transition hover:bg-blue-100"
          >
            <Plus className="h-3.5 w-3.5" /> 원장 추가
          </button>
        </div>
        <div className="space-y-4">
          {draft.doctors.map((doctor, idx) => (
            <div key={doctor.key} className="rounded-xl border border-slate-200 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-black text-slate-700">원장 {idx + 1}</span>
                {draft.doctors.length > 1 ? (
                  <button
                    type="button"
                    onClick={() => removeDoctor(doctor.key)}
                    className="flex items-center gap-1 text-xs font-bold text-rose-500 hover:text-rose-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> 삭제
                  </button>
                ) : null}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="이름" required>
                  <input className="contact-input" value={doctor.name} onChange={(e) => updateDoctor(doctor.key, { name: e.target.value })} />
                </Field>
                <Field label="면허번호" required>
                  <input className="contact-input" value={doctor.licenseNumber} onChange={(e) => updateDoctor(doctor.key, { licenseNumber: e.target.value })} />
                </Field>
                <Field label="전문 진료">
                  <input className="contact-input" value={doctor.specialty ?? ""} onChange={(e) => updateDoctor(doctor.key, { specialty: e.target.value })} />
                </Field>
                <Field label="학력">
                  <input className="contact-input" value={doctor.education ?? ""} onChange={(e) => updateDoctor(doctor.key, { education: e.target.value })} />
                </Field>
                <Field label="이메일">
                  <input className="contact-input" type="email" value={doctor.email ?? ""} onChange={(e) => updateDoctor(doctor.key, { email: e.target.value })} />
                </Field>
                <Field label="면허증 파일">
                  <FileField file={doctor.licenseFile} onChange={(f) => updateDoctor(doctor.key, { licenseFile: f })} accept="image/*,application/pdf" />
                </Field>
              </div>
              <div className="mt-3 space-y-3">
                <Field label="원장 소개" hint={<CharCount value={doctor.bio ?? ""} max={LIMITS.bio} />}>
                  <textarea
                    className="contact-input min-h-20 resize-y py-3"
                    value={doctor.bio ?? ""}
                    onChange={(e) => updateDoctor(doctor.key, { bio: e.target.value })}
                  />
                </Field>
                <Field label="전문 분야" hint={`태그 (최대 ${LIMITS.areas}개)`}>
                  <TagInput
                    value={doctor.specialtyAreas}
                    onChange={(v) => updateDoctor(doctor.key, { specialtyAreas: v })}
                    max={LIMITS.areas}
                    maxLen={LIMITS.area}
                    placeholder="전문분야 입력"
                  />
                </Field>
                <Field label="원장 사진">
                  <FileField file={doctor.photo} onChange={(f) => updateDoctor(doctor.key, { photo: f })} accept="image/*" image />
                </Field>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 편집 미리보기 */}
      <section>
        <h3 className="mb-3 text-sm font-black text-slate-700">수정 미리보기</h3>
        <HospitalPreview app={draft} />
      </section>

      {/* 저장/취소 */}
      <div className="sticky bottom-0 flex gap-3 border-t border-slate-200 bg-slate-50/90 py-4 backdrop-blur">
        <button type="button" onClick={handleSave} className="mp-btn-primary flex flex-1 items-center justify-center gap-2">
          <Save className="h-4 w-4" /> 변경 저장
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-5 text-sm font-bold text-slate-500 transition hover:bg-slate-50"
        >
          <X className="h-4 w-4" /> 취소
        </button>
      </div>
    </div>
  );
}

/* ── 메인 상세 페이지 ── */
export default function ApplicationDetail() {
  const { id } = useParams();
  const [app, setApp] = useState<HospitalApplication | undefined>(() =>
    id ? getApplication(id) : undefined,
  );
  const [editing, setEditing] = useState(false);

  if (!app) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <Link to="/admin" className="text-sm font-bold text-blue-600">
          ← 목록으로
        </Link>
        <p className="mt-6 text-sm font-bold text-slate-500">신청을 찾을 수 없습니다.</p>
      </div>
    );
  }

  const handlePublish = () => {
    const updated = setStatus(app.id, "승인발행", {
      issuedTempPassword: generateTempPassword(),
    });
    if (updated) setApp(updated);
  };

  const handleReject = () => {
    const reason = window.prompt("반려 사유를 입력하세요");
    if (reason === null) return;
    const updated = setStatus(app.id, "반려", { rejectReason: reason.trim() });
    if (updated) setApp(updated);
  };

  const published = app.status === "승인발행";

  /* 편집 모드 */
  if (editing) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="flex w-fit items-center gap-1 text-sm font-bold text-slate-500 hover:text-blue-700"
        >
          <ArrowLeft className="h-4 w-4" /> 편집 취소
        </button>
        <div className="mt-4 flex items-center gap-3">
          <h1 className="text-2xl font-black text-slate-900">{app.hospitalName}</h1>
          <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-black text-blue-700">편집 중</span>
        </div>
        <div className="mt-5">
          <EditForm
            app={app}
            onSave={(updated) => {
              setApp(updated);
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      </div>
    );
  }

  /* 일반 보기 모드 */
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <Link to="/admin" className="flex w-fit items-center gap-1 text-sm font-bold text-slate-500 hover:text-blue-700">
        <ArrowLeft className="h-4 w-4" /> 목록으로
      </Link>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-black text-slate-900">{app.hospitalName}</h1>
          <StatusBadge status={app.status} />
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-bold text-blue-700 transition hover:bg-blue-100"
          >
            <Pencil className="h-3.5 w-3.5" /> 수정
          </button>
          <span className="text-sm font-semibold text-slate-400">
            신청일 {new Date(app.createdAt).toLocaleString("ko-KR")}
          </span>
        </div>
      </div>

      {/* 발행 결과 / 반려 사유 배너 */}
      {published ? (
        <div className="mt-5 flex items-start gap-3 rounded-2xl border border-green-200 bg-green-50 p-4">
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-green-600" />
          <div className="text-sm font-bold text-green-800">
            발행 완료 — 계정이 생성되었습니다.
            <div className="mt-1 font-semibold text-green-700">
              로그인 아이디: <span className="font-black">{app.desiredLoginId}</span> · 임시 비밀번호:{" "}
              <span className="font-black">{app.issuedTempPassword}</span>
            </div>
            <p className="mt-1 text-xs font-medium text-green-600">
              (데모 표시. 실제로는 {app.ownerEmail} 로 자동 발송됩니다.)
            </p>
          </div>
        </div>
      ) : null}
      {app.status === "반려" ? (
        <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm font-bold text-rose-700">
          반려됨 — 사유: {app.rejectReason || "(없음)"}
        </div>
      ) : null}

      {/* 신원·계정 + 서류 (비공개) */}
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-black text-slate-700">신원·계정 정보 (비공개)</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Info label="사업자등록번호" value={app.businessNumber} />
          <Info label="대표 연락처" value={app.hospitalPhone} />
          <Info label="대표 이메일" value={app.ownerEmail} />
          <Info label="주소" value={app.hospitalAddress} />
          <Info label="희망 로그인 아이디" value={app.desiredLoginId} />
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <DocChip label="사업자등록증" file={app.businessLicenseFile} />
          {app.doctors.map((d, i) => (
            <DocChip key={d.key} label={`${d.name || `원장 ${i + 1}`} 면허증`} file={d.licenseFile} />
          ))}
        </div>
      </section>

      {/* 보호자 페이지 미리보기 */}
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-black text-slate-700">보호자에게 보이는 화면 (미리보기)</h2>
        <HospitalPreview app={app} />
      </section>

      {/* 액션 */}
      {!published ? (
        <div className="sticky bottom-0 mt-6 flex gap-3 border-t border-slate-200 bg-slate-50/80 py-4 backdrop-blur">
          <button type="button" onClick={handlePublish} className="mp-btn-primary flex-1">
            페이지 등록하기 (발행)
          </button>
          <button
            type="button"
            onClick={handleReject}
            className="inline-flex h-11 items-center justify-center rounded-full border border-rose-200 bg-white px-5 text-sm font-bold text-rose-500 transition hover:bg-rose-50"
          >
            반려
          </button>
        </div>
      ) : null}
    </div>
  );
}
