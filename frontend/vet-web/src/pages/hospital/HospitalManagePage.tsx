import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Plus, Trash2, X } from "lucide-react";
import type { AuthSession } from "../../api/authApi";
import AppLayout, { AppMenuId } from "../../layouts/AppLayout";
import { InlineTimeSelect, Toggle, defaultWeek } from "../../components/settings/settingsShared";
import { fetchHospitalDoctors, type DoctorInfo } from "../../api/emrApi";
import {
  fetchHospitalProfile,
  updateHospitalProfile,
  fetchDoctors,
  createDoctor,
  deleteDoctor,
  updateDoctorProfile,
  uploadHospitalFile,
  type HospitalProfile,
  type DoctorProfile,
} from "../../api/vetHospitalApi";
import {
  type DaySchedule,
  fetchWeeklySchedule,
  updateWeeklySchedule,
  fetchVetWeeklySchedule,
  updateVetWeeklySchedule,
  fetchClosedDates,
  addClosedDate,
  removeClosedDate,
  getSettingsApiErrorMessage,
} from "../../api/settingsApi";

// ── 타입 ─────────────────────────────────────────────────────────────

interface EditDoctor extends DoctorProfile {
  licenseNumber: string;
  specialty: string;
  education: string;
  bio: string;
  specialtyAreas: string[];
  profileImage: string;
  profileImagePosition: string;
}

interface EditHospital {
  name: string;
  address: string;
  phone: string;
  tagline: string;
  intro: string;
  features: string[];
  bannerImage: string;
  bannerImagePosition: string;
  doctors: EditDoctor[];
}

const inputCls =
  "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100";
const labelCls = "text-xs font-bold text-slate-500";
const DEFAULT_BANNER_POS = "50% 50%";
const DEFAULT_DOCTOR_POS = "50% 20%";
const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

function toEditHospital(p: HospitalProfile, docs: DoctorProfile[]): EditHospital {
  return {
    name: p.name ?? "",
    address: p.address ?? "",
    phone: p.phone ?? "",
    tagline: p.tagline ?? "",
    intro: p.intro ?? "",
    features: p.features ?? [],
    bannerImage: p.bannerImage ?? "",
    bannerImagePosition: p.bannerImagePosition ?? DEFAULT_BANNER_POS,
    doctors: docs.map((d) => ({
      ...d,
      licenseNumber: d.licenseNumber ?? "",
      specialty: d.specialty ?? "",
      education: d.education ?? "",
      bio: d.bio ?? "",
      specialtyAreas: d.specialtyAreas ?? [],
      profileImage: d.profileImage ?? "",
      profileImagePosition: d.profileImagePosition ?? DEFAULT_DOCTOR_POS,
    })),
  };
}

// ── 메인 페이지 ───────────────────────────────────────────────────────

interface Props {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

export default function HospitalManagePage({ session, onLogout, onNavigate }: Props) {
  const [draft, setDraft] = useState<EditHospital | null>(null);
  const [hours, setHours] = useState<DaySchedule[]>([]);
  const [msg, setMsg] = useState("");

  const flash = (m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg(""), 2500);
  };

  const reload = async () => {
    const [profile, docs, schedule] = await Promise.all([
      fetchHospitalProfile(session.accessToken),
      fetchDoctors(session.accessToken),
      fetchWeeklySchedule(session.accessToken),
    ]);
    setDraft(toEditHospital(profile, docs));
    setHours(schedule);
  };

  useEffect(() => {
    void reload().catch(() => setMsg("불러오기에 실패했습니다."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.accessToken]);

  const patchHospital = (p: Partial<EditHospital>) =>
    setDraft((cur) => (cur ? { ...cur, ...p } : cur));

  const patchDoctor = (did: number, p: Partial<EditDoctor>) =>
    setDraft((cur) =>
      cur
        ? { ...cur, doctors: cur.doctors.map((d) => (d.doctorid === did ? { ...d, ...p } : d)) }
        : cur
    );

  const moveDoctor = (did: number, dir: -1 | 1) =>
    setDraft((cur) => {
      if (!cur) return cur;
      const arr = [...cur.doctors];
      const idx = arr.findIndex((d) => d.doctorid === did);
      const next = idx + dir;
      if (next < 0 || next >= arr.length) return cur;
      [arr[idx], arr[next]] = [arr[next], arr[idx]];
      return { ...cur, doctors: arr };
    });

  const saveProfile = async () => {
    if (!draft) return;
    await updateHospitalProfile(session.accessToken, {
      name: draft.name,
      address: draft.address,
      phone: draft.phone,
      tagline: draft.tagline,
      intro: draft.intro,
      features: draft.features,
      bannerImage: draft.bannerImage || undefined,
      bannerImagePosition: draft.bannerImagePosition,
    });
    flash("병원 정보 저장됨");
  };

  const saveDoctor = async (doc: EditDoctor) => {
    await updateDoctorProfile(session.accessToken, doc.doctorid, {
      name: doc.name,
      licenseNumber: doc.licenseNumber || undefined,
      specialty: doc.specialty,
      education: doc.education,
      bio: doc.bio,
      specialtyAreas: doc.specialtyAreas,
      profileImage: doc.profileImage || undefined,
      profileImagePosition: doc.profileImagePosition,
    });
    flash("원장 정보 저장됨");
  };

  if (!draft) {
    return (
      <AppLayout session={session} activeMenu="hospital-manage" onLogout={onLogout} onNavigate={onNavigate}>
        <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-400">
          불러오는 중…
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout session={session} activeMenu="hospital-manage" onLogout={onLogout} onNavigate={onNavigate}>
      <div data-tour="vet-hospital" className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900">병원 관리</h1>
          <p className="mt-0.5 text-sm font-bold text-slate-500">
            보호자 화면에 표시되는 병원 정보와 운영 일정을 관리합니다.
          </p>
        </div>
      </div>

      {msg && (
        <div className="mb-4 rounded-lg bg-blue-50 px-4 py-2 text-sm font-bold text-blue-700">
          {msg}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 왼쪽: 편집 폼 */}
        <div className="space-y-5">
          {/* 병원 정보 */}
          <Section title="병원 정보">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="병원명">
                <input className={inputCls} value={draft.name} onChange={(e) => patchHospital({ name: e.target.value })} />
              </Field>
              <Field label="전화">
                <input className={inputCls} value={draft.phone} onChange={(e) => patchHospital({ phone: e.target.value })} />
              </Field>
            </div>
            <Field label="한 줄 소개 (태그라인)">
              <input className={inputCls} value={draft.tagline} onChange={(e) => patchHospital({ tagline: e.target.value })} />
            </Field>
            <Field label="주소">
              <input className={inputCls} value={draft.address} onChange={(e) => patchHospital({ address: e.target.value })} />
            </Field>
            <Field label="소개 본문">
              <textarea
                className={`${inputCls} h-28 resize-none py-2`}
                value={draft.intro}
                onChange={(e) => patchHospital({ intro: e.target.value })}
              />
            </Field>
            <Field label="특징 태그">
              <DoctorTagInput value={draft.features} onChange={(arr) => patchHospital({ features: arr })} />
            </Field>
            <Field label="배너 이미지 (드래그로 초점 조정)">
              <ImageEditor
                url={draft.bannerImage}
                position={draft.bannerImagePosition}
                prefix="hospital"
                aspect="4 / 3"
                accessToken={session.accessToken}
                onUrl={(u) => patchHospital({ bannerImage: u })}
                onPosition={(p) => patchHospital({ bannerImagePosition: p })}
              />
            </Field>
            <SaveButton onClick={() => void saveProfile().catch((e) => alert(e instanceof Error ? e.message : "저장 실패"))} />
          </Section>

          {/* 진료시간 */}
          <HoursForm
            hours={hours}
            onSave={async (next) => {
              const saved = await updateWeeklySchedule(session.accessToken, next);
              setHours(saved);
              flash("진료시간 저장됨");
            }}
          />

          {/* 의사별 근무시간 */}
          <VetScheduleForm accessToken={session.accessToken} hospitalHours={hours} />

          {/* 특정일 휴진 */}
          <ClosedDatesForm accessToken={session.accessToken} />

          {/* 원장 */}
          <DoctorsSection
            draft={draft}
            accessToken={session.accessToken}
            onPatch={patchDoctor}
            onSave={saveDoctor}
            onAdd={async (name: string) => {
              const newDoc = await createDoctor(session.accessToken, name);
              setDraft((cur) =>
                cur
                  ? {
                      ...cur,
                      doctors: [
                        ...cur.doctors,
                        {
                          ...newDoc,
                          licenseNumber: newDoc.licenseNumber ?? "",
                          specialty: newDoc.specialty ?? "",
                          education: newDoc.education ?? "",
                          bio: newDoc.bio ?? "",
                          specialtyAreas: newDoc.specialtyAreas ?? [],
                          profileImage: newDoc.profileImage ?? "",
                          profileImagePosition: newDoc.profileImagePosition ?? DEFAULT_DOCTOR_POS,
                        },
                      ],
                    }
                  : cur
              );
              flash("원장이 추가됐습니다.");
            }}
            onDelete={async (did: number) => {
              if (!window.confirm("해당 원장을 삭제하시겠습니까?")) return;
              await deleteDoctor(session.accessToken, did);
              setDraft((cur) =>
                cur ? { ...cur, doctors: cur.doctors.filter((d) => d.doctorid !== did) } : cur
              );
              flash("원장이 삭제됐습니다.");
            }}
            onMove={moveDoctor}
          />
        </div>

        {/* 오른쪽: 실시간 미리보기 */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          <p className="mb-2 text-xs font-bold text-slate-400">보호자 화면 미리보기</p>
          <HospitalPreview draft={draft} />
        </div>
      </div>
    </AppLayout>
  );
}

// ── 보호자 화면 미리보기 ──────────────────────────────────────────────

function HospitalPreview({ draft }: { draft: EditHospital }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-sm">
      {/* 병원 소개 — guardian-web HospitalDetail 구조 */}
      <div className="relative">
        {draft.bannerImage ? (
          <div className="pointer-events-none absolute inset-y-0 right-0 w-1/2 sm:w-2/5">
            <img
              src={draft.bannerImage}
              alt=""
              className="h-full w-full object-cover"
              style={{ objectPosition: draft.bannerImagePosition }}
            />
            {/* 그라데이션 마스크 */}
            <div
              className="absolute inset-0"
              style={{ background: "linear-gradient(to right, rgba(255,255,255,1) 0%, rgba(255,255,255,0.85) 20%, rgba(255,255,255,0.4) 50%, rgba(255,255,255,0) 100%)" }}
            />
            {/* 블러 레이어 */}
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
        <div className="relative z-10 p-6 sm:w-3/5">
          <h2 className="text-xl font-extrabold text-slate-950">{draft.name || "병원명"}</h2>
          {draft.tagline && <p className="mt-2 text-sm font-bold text-blue-600">{draft.tagline}</p>}
          <p className={`mt-3 whitespace-pre-line text-sm font-medium leading-7 ${draft.intro ? "text-slate-600" : "text-slate-300"}`}>
            {draft.intro || "병원 소개가 여기 표시됩니다."}
          </p>
          {draft.features.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {draft.features.map((f) => (
                <span key={f} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">{f}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 원장 소개 */}
      <div className="border-t border-slate-100 p-5">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-base font-bold text-slate-900">원장 소개</p>
          {draft.doctors.length > 0 && (
            <span className="text-sm font-semibold text-slate-400">{draft.doctors.length}명</span>
          )}
        </div>
        {draft.doctors.length === 0 ? (
          <p className="py-6 text-center text-sm font-semibold text-slate-300">등록된 원장이 없습니다.</p>
        ) : (
          <div className="flex flex-wrap justify-center gap-4">
            {draft.doctors.map((doc) => (
              <div key={doc.doctorid} className="w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm sm:w-[calc(50%-0.5rem)]">
                {doc.profileImage ? (
                  <img
                    src={doc.profileImage}
                    alt={doc.name}
                    className="aspect-[4/3] w-full object-cover"
                    style={{ objectPosition: doc.profileImagePosition }}
                  />
                ) : (
                  <div className="flex aspect-[4/3] w-full items-center justify-center bg-blue-50 text-4xl font-extrabold text-blue-600">
                    {(doc.name || "?").trim().charAt(0)}
                  </div>
                )}
                <div className="flex flex-col p-5">
                  <h3 className="text-base font-extrabold text-slate-950">{doc.name || "원장"}</h3>
                  {doc.specialty && <p className="mt-1 text-sm font-bold text-blue-600">{doc.specialty}</p>}
                  {doc.education && <p className="mt-0.5 text-xs font-semibold text-slate-400">{doc.education}</p>}
                  <p className={`mt-3 text-sm font-medium leading-6 ${doc.bio ? "text-slate-600" : "text-slate-300"}`}>
                    {doc.bio || "소개글이 없습니다."}
                  </p>
                  {doc.specialtyAreas.length > 0 && (
                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <p className="mb-2 text-xs font-bold text-slate-400">전문 분야</p>
                      <div className="flex flex-wrap gap-1.5">
                        {doc.specialtyAreas.map((area) => (
                          <span key={area} className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700">{area}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 이미지 + 초점 드래그 ──────────────────────────────────────────────

function parsePos(pos: string): { x: number; y: number } {
  const m = pos.match(/(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%/);
  return m ? { x: Number(m[1]), y: Number(m[2]) } : { x: 50, y: 50 };
}
const clamp = (n: number) => Math.max(0, Math.min(100, n));

function ImageEditor({
  url,
  position,
  prefix,
  aspect,
  accessToken,
  onUrl,
  onPosition,
}: {
  url: string;
  position: string;
  prefix: "hospital" | "doctor";
  aspect: string;
  accessToken: string;
  onUrl: (url: string) => void;
  onPosition: (pos: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const drag = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const [busy, setBusy] = useState(false);

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || e.buttons !== 1) return;
    const r = ref.current!.getBoundingClientRect();
    const dx = ((e.clientX - d.sx) / r.width) * 100;
    const dy = ((e.clientY - d.sy) / r.height) * 100;
    onPosition(`${Math.round(clamp(d.px - dx))}% ${Math.round(clamp(d.py - dy))}%`);
  };

  const handleFile = async (file: File) => {
    setBusy(true);
    try {
      onUrl(await uploadHospitalFile(accessToken, file, prefix));
    } catch (err) {
      alert(err instanceof Error ? err.message : "업로드 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {url ? (
        <div
          ref={ref}
          className="relative cursor-grab touch-none select-none overflow-hidden rounded-lg border border-slate-200 active:cursor-grabbing"
          style={{ aspectRatio: aspect }}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            const { x, y } = parsePos(position);
            drag.current = { sx: e.clientX, sy: e.clientY, px: x, py: y };
          }}
          onPointerMove={onPointerMove}
          onPointerUp={() => { drag.current = null; }}
          onPointerCancel={() => { drag.current = null; }}
        >
          <img
            src={url}
            alt=""
            draggable={false}
            className="pointer-events-none h-full w-full object-cover"
            style={{ objectPosition: position }}
          />
        </div>
      ) : (
        <div
          className="flex items-center justify-center rounded-lg border border-dashed border-slate-300 py-8 text-xs font-bold text-slate-400"
          style={{ aspectRatio: aspect }}
        >
          이미지 없음
        </div>
      )}
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"
        >
          {busy ? "업로드 중…" : url ? "이미지 변경" : "이미지 선택"}
        </button>
        {url && (
          <button
            type="button"
            onClick={() => onUrl("")}
            className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-bold text-red-500 transition hover:bg-red-50"
          >
            이미지 삭제
          </button>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
          e.target.value = "";
        }}
      />
      {url && <p className="mt-1 text-[11px] font-semibold text-slate-400">이미지를 드래그해 위치를 맞추세요.</p>}
    </div>
  );
}

// ── 원장 편집 카드 ────────────────────────────────────────────────────

function DoctorEditor({
  doc,
  accessToken,
  onPatch,
  onSave,
  onDelete,
  onMoveUp,
  onMoveDown,
}: {
  doc: EditDoctor;
  accessToken: string;
  onPatch: (p: Partial<EditDoctor>) => void;
  onSave: () => Promise<void>;
  onDelete: () => Promise<void>;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
}) {
  const [saving, setSaving] = useState(false);
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="mb-3 flex items-center justify-between">
        {/* 순서 변경 버튼 */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={!onMoveUp}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-25 disabled:cursor-not-allowed"
            title="위로"
          >
            ↑
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={!onMoveDown}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-25 disabled:cursor-not-allowed"
            title="아래로"
          >
            ↓
          </button>
        </div>
        <button
          type="button"
          onClick={() => void onDelete()}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-slate-400 hover:bg-red-50 hover:text-red-500"
        >
          <Trash2 className="h-3.5 w-3.5" />
          삭제
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="이름">
          <input className={inputCls} value={doc.name} onChange={(e) => onPatch({ name: e.target.value })} />
        </Field>
        <Field label="면허번호">
          <input className={inputCls} value={doc.licenseNumber} onChange={(e) => onPatch({ licenseNumber: e.target.value })} />
        </Field>
        <Field label="전문 진료">
          <input className={inputCls} value={doc.specialty} onChange={(e) => onPatch({ specialty: e.target.value })} />
        </Field>
        <Field label="학력">
          <input className={inputCls} value={doc.education} onChange={(e) => onPatch({ education: e.target.value })} />
        </Field>
      </div>
      <Field label="소개글">
        <textarea
          className={`${inputCls} h-24 resize-none py-2`}
          value={doc.bio}
          onChange={(e) => onPatch({ bio: e.target.value })}
        />
      </Field>
      <Field label="전문 분야">
        <DoctorTagInput value={doc.specialtyAreas} onChange={(arr) => onPatch({ specialtyAreas: arr })} />
      </Field>
      <Field label="원장 사진 (드래그로 초점 조정)">
        <ImageEditor
          url={doc.profileImage}
          position={doc.profileImagePosition}
          prefix="doctor"
          aspect="4 / 3"
          accessToken={accessToken}
          onUrl={(u) => onPatch({ profileImage: u })}
          onPosition={(p) => onPatch({ profileImagePosition: p })}
        />
      </Field>
      <SaveButton
        onClick={async () => {
          setSaving(true);
          try { await onSave(); } catch (e) { alert(e instanceof Error ? e.message : "저장 실패"); } finally { setSaving(false); }
        }}
        saving={saving}
      />
    </div>
  );
}

// ── 원장 섹션 (목록 + 추가) ───────────────────────────────────────────

function DoctorsSection({
  draft,
  accessToken,
  onPatch,
  onSave,
  onAdd,
  onDelete,
  onMove,
}: {
  draft: EditHospital;
  accessToken: string;
  onPatch: (did: number, p: Partial<EditDoctor>) => void;
  onSave: (doc: EditDoctor) => Promise<void>;
  onAdd: (name: string) => Promise<void>;
  onDelete: (did: number) => Promise<void>;
  onMove: (did: number, dir: -1 | 1) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);

  const handleAdd = async () => {
    const trimmed = newName.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      await onAdd(trimmed);
      setNewName("");
      setAdding(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "추가 실패");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section title="원장">
      <div className="space-y-3">
        {draft.doctors.map((doc, idx) => (
          <DoctorEditor
            key={doc.doctorid}
            doc={doc}
            accessToken={accessToken}
            onPatch={(p) => onPatch(doc.doctorid, p)}
            onSave={() => onSave(doc)}
            onDelete={() => onDelete(doc.doctorid)}
            onMoveUp={idx > 0 ? () => onMove(doc.doctorid, -1) : undefined}
            onMoveDown={idx < draft.doctors.length - 1 ? () => onMove(doc.doctorid, 1) : undefined}
          />
        ))}
        {draft.doctors.length === 0 && !adding && (
          <p className="py-4 text-center text-sm font-semibold text-slate-400">등록된 원장이 없습니다.</p>
        )}
      </div>

      {adding ? (
        <div className="mt-3 flex items-center gap-2">
          <input
            autoFocus
            className={inputCls}
            placeholder="원장 이름"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.nativeEvent.isComposing) return; if (e.key === "Enter") void handleAdd(); if (e.key === "Escape") { setAdding(false); setNewName(""); } }}
          />
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={saving || !newName.trim()}
            className="h-10 shrink-0 rounded-lg bg-blue-600 px-4 text-sm font-bold text-white hover:bg-blue-700 disabled:bg-slate-300"
          >
            {saving ? "추가 중…" : "추가"}
          </button>
          <button
            type="button"
            onClick={() => { setAdding(false); setNewName(""); }}
            className="h-10 shrink-0 rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-500 hover:bg-slate-50"
          >
            취소
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="mt-1 flex items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-4 py-2 text-sm font-bold text-slate-500 transition hover:border-blue-300 hover:text-blue-600"
        >
          <Plus className="h-4 w-4" />
          원장 추가
        </button>
      )}
    </Section>
  );
}

// ── 진료시간 ──────────────────────────────────────────────────────────

function HoursForm({ hours, onSave }: { hours: DaySchedule[]; onSave: (h: DaySchedule[]) => Promise<void> }) {
  const [rows, setRows] = useState<DaySchedule[]>(hours.length ? hours : defaultWeek);
  const [bulk, setBulk] = useState({ start: "09:00", end: "18:00", lunchStart: "12:00", lunchEnd: "13:00" });
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (hours.length) setRows(hours); }, [hours]);

  const patch = (dow: number, p: Partial<DaySchedule>) =>
    setRows((cur) => cur.map((r) => (r.day_of_week === dow ? { ...r, ...p } : r)));

  const toggleOpen = (dow: number) => {
    const day = rows.find((d) => d.day_of_week === dow)!;
    if (!day.is_open) {
      patch(dow, { is_open: true, start_time: "09:00", end_time: "18:00", lunch_start: "12:00", lunch_end: "13:00" });
    } else {
      patch(dow, { is_open: false, start_time: null, end_time: null, lunch_start: null, lunch_end: null });
    }
  };

  const applyBulk = () =>
    setRows((prev) =>
      prev.map((d) =>
        d.is_open
          ? { ...d, start_time: bulk.start, end_time: bulk.end, lunch_start: bulk.lunchStart, lunch_end: bulk.lunchEnd }
          : d
      )
    );

  return (
    <Section title="진료시간">
      {/* 일괄 적용 */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 px-4 py-3">
        <span className="shrink-0 text-xs font-extrabold text-slate-500">일괄 적용</span>
        <InlineTimeSelect value={bulk.start} onChange={(v) => setBulk((b) => ({ ...b, start: v }))} />
        <span className="text-xs text-slate-400">~</span>
        <InlineTimeSelect value={bulk.end} onChange={(v) => setBulk((b) => ({ ...b, end: v }))} />
        <span className="text-xs text-slate-300">|</span>
        <span className="text-xs font-semibold text-slate-400">점심</span>
        <InlineTimeSelect value={bulk.lunchStart} onChange={(v) => setBulk((b) => ({ ...b, lunchStart: v }))} />
        <span className="text-xs text-slate-400">~</span>
        <InlineTimeSelect value={bulk.lunchEnd} onChange={(v) => setBulk((b) => ({ ...b, lunchEnd: v }))} />
        <button
          type="button"
          onClick={applyBulk}
          className="shrink-0 h-8 rounded-lg bg-blue-600 px-3 text-xs font-extrabold text-white hover:bg-blue-700"
        >
          적용
        </button>
      </div>

      {/* 요일별 테이블 */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="pb-2 w-10 text-left text-xs font-extrabold text-slate-500">요일</th>
              <th className="pb-2 text-left text-xs font-extrabold text-slate-500">운영 시간</th>
              <th className="pb-2 text-left text-xs font-extrabold text-slate-500">점심 시간</th>
              <th className="pb-2 w-16 text-center text-xs font-extrabold text-slate-500">운영</th>
            </tr>
          </thead>
          <tbody>
            {[...rows].sort((a, b) => a.day_of_week - b.day_of_week).map((day) => {
              const noLunch = day.is_open && !day.lunch_start;
              return (
                <tr key={day.day_of_week} className="border-b border-slate-50 last:border-0">
                  <td className="py-3 text-sm font-extrabold text-slate-700">
                    {DAY_LABELS[day.day_of_week]}
                  </td>
                  <td className="py-3">
                    {day.is_open ? (
                      <div className="flex items-center gap-1.5">
                        <InlineTimeSelect
                          value={day.start_time ?? "09:00"}
                          onChange={(v) => patch(day.day_of_week, { start_time: v })}
                        />
                        <span className="text-xs text-slate-400">~</span>
                        <InlineTimeSelect
                          value={day.end_time ?? "18:00"}
                          onChange={(v) => patch(day.day_of_week, { end_time: v })}
                        />
                      </div>
                    ) : (
                      <span className="text-xs font-semibold text-slate-300">휴진</span>
                    )}
                  </td>
                  <td className="py-3">
                    {day.is_open ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <InlineTimeSelect
                          value={day.lunch_start ?? "12:00"}
                          onChange={(v) => patch(day.day_of_week, { lunch_start: v })}
                          disabled={noLunch}
                        />
                        <span className={`text-xs ${noLunch ? "text-slate-200" : "text-slate-400"}`}>~</span>
                        <InlineTimeSelect
                          value={day.lunch_end ?? "13:00"}
                          onChange={(v) => patch(day.day_of_week, { lunch_end: v })}
                          disabled={noLunch}
                        />
                        <label className="flex cursor-pointer items-center gap-1">
                          <input
                            type="checkbox"
                            checked={noLunch}
                            onChange={(e) => {
                              if (e.target.checked) {
                                patch(day.day_of_week, { lunch_start: null, lunch_end: null });
                              } else {
                                patch(day.day_of_week, { lunch_start: "12:00", lunch_end: "13:00" });
                              }
                            }}
                            className="h-3.5 w-3.5 rounded border-slate-300 accent-blue-600"
                          />
                          <span className="text-xs font-semibold text-slate-400">점심 없음</span>
                        </label>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-300">-</span>
                    )}
                  </td>
                  <td className="py-3 text-center">
                    <Toggle checked={day.is_open} onChange={() => toggleOpen(day.day_of_week)} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SaveButton
        onClick={async () => {
          setSaving(true);
          try { await onSave(rows); } finally { setSaving(false); }
        }}
        saving={saving}
      />
    </Section>
  );
}

// ── 의사별 근무시간 (인라인) ──────────────────────────────────────────

function VetScheduleForm({
  accessToken,
  hospitalHours,
}: {
  accessToken: string;
  hospitalHours: DaySchedule[];
}) {
  const [doctors, setDoctors] = useState<DoctorInfo[]>([]);
  const [selectedVetId, setSelectedVetId] = useState<number | undefined>();
  const [schedule, setSchedule] = useState<DaySchedule[]>([]);
  const [selectedDow, setSelectedDow] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchHospitalDoctors(accessToken)
      .then((docs) => {
        setDoctors(docs);
        setSelectedVetId((cur) => cur ?? docs[0]?.doctorid);
      })
      .catch(() => {});
  }, [accessToken]);

  useEffect(() => {
    if (!selectedVetId) return;
    fetchVetWeeklySchedule(accessToken, selectedVetId)
      .then((doctorSchedule) => {
        const merged = doctorSchedule.map((day) => {
          if (day.is_open) return day;
          const hosp = hospitalHours.find((h) => h.day_of_week === day.day_of_week);
          return hosp?.is_open ? { ...hosp, day_of_week: day.day_of_week } : day;
        });
        setSchedule(merged);
      })
      .catch(() => {});
  }, [accessToken, selectedVetId, hospitalHours]);

  const currentDay = schedule.find((d) => d.day_of_week === selectedDow);

  const updateCurrentDay = (patch: Partial<DaySchedule>) =>
    setSchedule((prev) =>
      prev.map((d) => (d.day_of_week === selectedDow ? { ...d, ...patch } : d))
    );

  const handleSave = async () => {
    if (!selectedVetId) return;
    setSaving(true);
    setError("");
    try {
      await updateVetWeeklySchedule(accessToken, selectedVetId, schedule);
      setError("");
    } catch (err) {
      setError(getSettingsApiErrorMessage(err, "저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section title="의사별 근무시간">
      {/* 의사 선택 */}
      <div>
        <label className="mb-1.5 block text-xs font-extrabold text-slate-600">수의사 선택</label>
        <select
          value={selectedVetId ?? ""}
          onChange={(e) => setSelectedVetId(Number(e.target.value))}
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-50"
        >
          {doctors.map((d) => (
            <option key={d.doctorid} value={d.doctorid}>{d.doctor_name}</option>
          ))}
        </select>
      </div>

      {/* 요일 탭 */}
      <div className="flex gap-1">
        {DAY_LABELS.map((label, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setSelectedDow(i)}
            className={`flex-1 h-9 rounded-lg text-sm font-extrabold transition ${
              selectedDow === i ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {currentDay && (
        <>
          {/* 근무 시간 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-400">출근 시간</label>
              <InlineTimeSelect
                value={currentDay.start_time ?? "09:00"}
                onChange={(v) => updateCurrentDay({ start_time: v, is_open: true })}
                disabled={!currentDay.is_open}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-400">퇴근 시간</label>
              <InlineTimeSelect
                value={currentDay.end_time ?? "18:00"}
                onChange={(v) => updateCurrentDay({ end_time: v })}
                disabled={!currentDay.is_open}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-400">점심 시작</label>
              <InlineTimeSelect
                value={currentDay.lunch_start ?? "12:00"}
                onChange={(v) => updateCurrentDay({ lunch_start: v })}
                disabled={!currentDay.lunch_start}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-400">점심 종료</label>
              <InlineTimeSelect
                value={currentDay.lunch_end ?? "13:00"}
                onChange={(v) => updateCurrentDay({ lunch_end: v })}
                disabled={!currentDay.lunch_start}
              />
            </div>
          </div>

          {/* 옵션 */}
          <div className="space-y-2">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={!currentDay.is_open}
                onChange={(e) => {
                  if (e.target.checked) {
                    updateCurrentDay({ is_open: false, start_time: null, end_time: null, lunch_start: null, lunch_end: null });
                  } else {
                    updateCurrentDay({ is_open: true, start_time: "09:00", end_time: "18:00", lunch_start: "12:00", lunch_end: "13:00" });
                  }
                }}
                className="h-4 w-4 rounded border-slate-300 accent-blue-600"
              />
              <span className="text-sm font-semibold text-slate-700">이 요일은 휴무입니다.</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={!currentDay.lunch_start}
                onChange={(e) => {
                  if (e.target.checked) {
                    updateCurrentDay({ lunch_start: null, lunch_end: null });
                  } else {
                    updateCurrentDay({ lunch_start: "12:00", lunch_end: "13:00" });
                  }
                }}
                className="h-4 w-4 rounded border-slate-300 accent-blue-600"
              />
              <span className="text-sm font-semibold text-slate-700">점심 시간이 없습니다.</span>
            </label>
          </div>
        </>
      )}

      {error && <p className="text-xs font-bold text-red-600">{error}</p>}
      <SaveButton onClick={() => void handleSave()} saving={saving} />
    </Section>
  );
}

// ── 특정일 휴진 (인라인) ──────────────────────────────────────────────

function ClosedDatesForm({ accessToken }: { accessToken: string }) {
  const [closedDates, setClosedDates] = useState<string[]>([]);
  const [newDate, setNewDate] = useState("");
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchClosedDates(accessToken).then(setClosedDates).catch(() => {});
  }, [accessToken]);

  const handleAdd = async () => {
    if (!newDate) return;
    setWarning("");
    setError("");
    try {
      const result = await addClosedDate(accessToken, newDate);
      setClosedDates((prev) => [...prev, newDate].sort());
      setNewDate("");
      if (result.has_existing_reservations) {
        setWarning(`해당 날짜에 예약이 ${result.reservation_count}건 있습니다. 기존 예약은 직접 처리해주세요.`);
      }
    } catch {
      setError("휴진일 등록에 실패했습니다.");
    }
  };

  const handleRemove = async (d: string) => {
    setWarning("");
    setError("");
    try {
      await removeClosedDate(accessToken, d);
      setClosedDates((prev) => prev.filter((x) => x !== d));
    } catch {
      setError("휴진일 해제에 실패했습니다.");
    }
  };

  return (
    <Section title="특정일 휴진">
      {/* 날짜 추가 */}
      <div>
        <label className="mb-1.5 block text-xs font-extrabold text-slate-600">날짜 추가</label>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={newDate}
            onChange={(e) => { setNewDate(e.target.value); setError(""); setWarning(""); }}
            className="h-9 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-50"
          />
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={!newDate}
            className="flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-3 text-xs font-extrabold text-white hover:bg-blue-700 disabled:bg-blue-200 disabled:cursor-not-allowed"
          >
            <Plus className="h-3.5 w-3.5" />
            추가
          </button>
        </div>
      </div>

      {warning && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p className="text-xs font-bold text-amber-700">{warning}</p>
        </div>
      )}
      {error && <p className="text-xs font-bold text-red-600">{error}</p>}

      {/* 등록된 휴진일 목록 */}
      <div>
        <p className="mb-2 text-xs font-extrabold text-slate-600">
          등록된 휴진일 ({closedDates.length})
        </p>
        {closedDates.length > 0 ? (
          <ul className="max-h-60 overflow-y-auto space-y-1.5">
            {closedDates.map((d) => (
              <li key={d} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5">
                <span className="text-sm font-bold text-slate-800">{d}</span>
                <button
                  type="button"
                  onClick={() => void handleRemove(d)}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs font-semibold text-slate-300">등록된 휴진일이 없습니다.</p>
        )}
      </div>
    </Section>
  );
}

// ── 공용 레이아웃 컴포넌트 ────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-extrabold text-slate-900">{title}</h2>
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className={labelCls}>{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function SaveButton({ onClick, saving }: { onClick: () => void; saving?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={saving}
      className="mt-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-bold text-white transition hover:bg-blue-700 disabled:bg-slate-300"
    >
      {saving ? "저장 중…" : "저장"}
    </button>
  );
}

// ── 전문 분야 태그 입력 ───────────────────────────────────────────────

const MAX_SPECIALTY_TAGS = 8;

function DoctorTagInput({ value, onChange }: { value: string[]; onChange: (arr: string[]) => void }) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const t = draft.trim();
    if (!t || value.includes(t) || value.length >= MAX_SPECIALTY_TAGS) {
      setDraft("");
      return;
    }
    onChange([...value, t]);
    setDraft("");
  };

  return (
    <div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.nativeEvent.isComposing) return;
            if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
          }}
          placeholder={value.length >= MAX_SPECIALTY_TAGS ? `최대 ${MAX_SPECIALTY_TAGS}개` : "내과 진료, 노령동물 건강관리 ..."}
          disabled={value.length >= MAX_SPECIALTY_TAGS}
          className={inputCls}
        />
        <button
          type="button"
          onClick={add}
          disabled={value.length >= MAX_SPECIALTY_TAGS}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      {value.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <span key={tag} className="flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
              {tag}
              <button
                type="button"
                onClick={() => onChange(value.filter((t) => t !== tag))}
                className="text-blue-400 hover:text-blue-700"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <p className="mt-1 text-[11px] font-semibold text-slate-400">태그 (최대 {MAX_SPECIALTY_TAGS}개)</p>
    </div>
  );
}
