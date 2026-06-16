import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getHospital,
  getHospitalHours,
  updateHospitalProfile,
  updateHospitalHours,
  addDoctor,
  updateDoctorProfile,
  setDoctorActive,
  uploadFile,
  type AdminHospitalDetail,
  type DaySchedule,
} from "../../onboarding/api";

const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];
const inputCls =
  "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100";
const labelCls = "text-xs font-bold text-slate-500";
const DEFAULT_BANNER_POS = "50% 50%";
const DEFAULT_DOCTOR_POS = "50% 20%";

// 편집 중 초안(canonical): features/specialtyAreas는 배열로 보관.
interface EditDoctor {
  doctorid: number;
  name: string;
  specialty: string;
  education: string;
  bio: string;
  specialtyAreas: string[];
  profileImage: string;
  profileImagePosition: string;
  is_active: boolean;
}
interface EditHospital {
  hospitalid: number;
  name: string;
  tagline: string;
  address: string;
  phone: string;
  intro: string;
  features: string[];
  bannerImage: string;
  bannerImagePosition: string;
  doctors: EditDoctor[];
}

function toDraft(d: AdminHospitalDetail): EditHospital {
  return {
    hospitalid: d.hospitalid,
    name: d.name || "",
    tagline: d.tagline || "",
    address: d.address || "",
    phone: d.phone || "",
    intro: d.intro || "",
    features: d.features || [],
    bannerImage: d.bannerImage || "",
    bannerImagePosition: d.bannerImagePosition || DEFAULT_BANNER_POS,
    doctors: (d.doctors || []).map((doc) => ({
      doctorid: doc.doctorid,
      name: doc.name || "",
      specialty: doc.specialty || "",
      education: doc.education || "",
      bio: doc.bio || "",
      specialtyAreas: doc.specialtyAreas || [],
      profileImage: doc.profileImage || "",
      profileImagePosition: doc.profileImagePosition || DEFAULT_DOCTOR_POS,
      is_active: doc.is_active,
    })),
  };
}

export default function HospitalManage() {
  const { id } = useParams();
  const hid = Number(id);

  const [draft, setDraft] = useState<EditHospital | null>(null);
  const [hours, setHours] = useState<DaySchedule[]>([]);
  const [msg, setMsg] = useState("");

  const reload = async () => {
    const [d, h] = await Promise.all([getHospital(hid), getHospitalHours(hid)]);
    setDraft(toDraft(d));
    setHours(h);
  };

  useEffect(() => {
    void reload().catch(() => setMsg("불러오기에 실패했습니다."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hid]);

  const flash = (m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg(""), 2500);
  };

  const patchHospital = (p: Partial<EditHospital>) => setDraft((cur) => (cur ? { ...cur, ...p } : cur));
  const patchDoctor = (did: number, p: Partial<EditDoctor>) =>
    setDraft((cur) =>
      cur ? { ...cur, doctors: cur.doctors.map((d) => (d.doctorid === did ? { ...d, ...p } : d)) } : cur,
    );

  if (!draft) {
    return <div className="mx-auto max-w-3xl px-6 py-8 text-sm font-semibold text-slate-400">불러오는 중…</div>;
  }

  const saveProfile = async () => {
    await updateHospitalProfile(hid, {
      name: draft.name,
      tagline: draft.tagline,
      address: draft.address,
      phone: draft.phone,
      intro: draft.intro,
      bannerImage: draft.bannerImage || undefined,
      bannerImagePosition: draft.bannerImagePosition,
      features: draft.features,
    });
    flash("병원 정보 저장됨");
  };

  const saveDoctor = async (doc: EditDoctor) => {
    await updateDoctorProfile(doc.doctorid, {
      name: doc.name,
      specialty: doc.specialty,
      education: doc.education,
      bio: doc.bio,
      specialtyAreas: doc.specialtyAreas,
      profileImage: doc.profileImage || undefined,
      profileImagePosition: doc.profileImagePosition,
    });
    flash("원장 정보 저장됨");
  };

  const toggleActive = async (doc: EditDoctor) => {
    await setDoctorActive(doc.doctorid, !doc.is_active);
    patchDoctor(doc.doctorid, { is_active: !doc.is_active });
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <Link to="/admin/hospitals" className="text-sm font-bold text-blue-600 hover:text-blue-700">
        ← 병원 목록
      </Link>
      <h1 className="mt-2 text-2xl font-black text-slate-900">{draft.name}</h1>
      {msg ? <div className="mt-3 rounded-lg bg-blue-50 px-4 py-2 text-sm font-bold text-blue-700">{msg}</div> : null}

      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        {/* 왼쪽: 편집 폼 */}
        <div className="space-y-5">
          <Section title="병원 정보">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="병원명"><input className={inputCls} value={draft.name} onChange={(e) => patchHospital({ name: e.target.value })} /></Field>
              <Field label="전화"><input className={inputCls} value={draft.phone} onChange={(e) => patchHospital({ phone: e.target.value })} /></Field>
            </div>
            <Field label="한 줄 소개(태그라인)"><input className={inputCls} value={draft.tagline} onChange={(e) => patchHospital({ tagline: e.target.value })} /></Field>
            <Field label="주소"><input className={inputCls} value={draft.address} onChange={(e) => patchHospital({ address: e.target.value })} /></Field>
            <Field label="소개 본문"><textarea className={`${inputCls} h-28 resize-none py-2`} value={draft.intro} onChange={(e) => patchHospital({ intro: e.target.value })} /></Field>
            <Field label="특징 태그 (쉼표로 구분)">
              <TagsInput value={draft.features} onChange={(arr) => patchHospital({ features: arr })} />
            </Field>
            <Field label="배너 이미지 (드래그로 초점 조정)">
              <ImageEditor
                url={draft.bannerImage}
                position={draft.bannerImagePosition}
                prefix="hospital"
                aspect="16 / 7"
                onUrl={(u) => patchHospital({ bannerImage: u })}
                onPosition={(p) => patchHospital({ bannerImagePosition: p })}
              />
            </Field>
            <SaveButton onClick={saveProfile} />
          </Section>

          <HoursForm hours={hours} onSave={async (next) => { await updateHospitalHours(hid, next); setHours(next); flash("진료시간 저장됨"); }} />

          <Section title="원장">
            <div className="space-y-3">
              {draft.doctors.map((doc) => (
                <DoctorEditor
                  key={doc.doctorid}
                  doc={doc}
                  onPatch={(p) => patchDoctor(doc.doctorid, p)}
                  onSave={() => saveDoctor(doc)}
                  onToggleActive={() => toggleActive(doc)}
                />
              ))}
            </div>
            <AddDoctorForm hid={hid} onAdded={async () => { await reload(); flash("원장 추가됨"); }} />
          </Section>
        </div>

        {/* 오른쪽: 실시간 미리보기 (보호자 화면) */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          <p className="mb-2 text-xs font-bold text-slate-400">보호자 화면 미리보기</p>
          <HospitalPreview draft={draft} />
        </div>
      </div>
    </div>
  );
}

// ── 미리보기 (guardian 병원탭 근사) ──────────────────────────
function HospitalPreview({ draft }: { draft: EditHospital }) {
  const activeDoctors = draft.doctors.filter((d) => d.is_active);
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-sm">
      {/* 배너 + 텍스트 */}
      <div className="relative">
        {draft.bannerImage ? (
          <div className="pointer-events-none absolute inset-y-0 right-0 w-2/5">
            <img src={draft.bannerImage} alt="" className="h-full w-full object-cover" style={{ objectPosition: draft.bannerImagePosition }} />
            <div className="absolute inset-0" style={{ background: "linear-gradient(to right, #fff 0%, rgba(255,255,255,0.6) 45%, rgba(255,255,255,0) 100%)" }} />
          </div>
        ) : null}
        <div className="relative z-10 p-6 sm:w-3/5">
          <h2 className="text-xl font-extrabold">{draft.name || "병원명"}</h2>
          {draft.tagline ? <p className="mt-1 text-sm font-bold text-blue-600">{draft.tagline}</p> : null}
          <p className={`mt-3 whitespace-pre-line text-sm leading-6 ${draft.intro ? "text-slate-600" : "text-slate-300"}`}>
            {draft.intro || "병원 소개가 여기 표시됩니다."}
          </p>
          {draft.features.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {draft.features.map((f) => (
                <span key={f} className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700">{f}</span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      {/* 원장 */}
      <div className="border-t border-slate-100 p-4">
        <p className="mb-3 text-sm font-bold text-slate-700">원장 소개 {activeDoctors.length > 0 ? `(${activeDoctors.length})` : ""}</p>
        {activeDoctors.length === 0 ? (
          <p className="py-6 text-center text-sm font-semibold text-slate-300">활성 원장이 없습니다.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {activeDoctors.map((doc) => (
              <div key={doc.doctorid} className="overflow-hidden rounded-xl border border-slate-200">
                {doc.profileImage ? (
                  <img src={doc.profileImage} alt={doc.name} className="h-40 w-full object-cover" style={{ objectPosition: doc.profileImagePosition }} />
                ) : (
                  <div className="flex h-40 w-full items-center justify-center bg-blue-50 text-4xl font-extrabold text-blue-600">
                    {(doc.name || "?").trim().charAt(0)}
                  </div>
                )}
                <div className="p-3">
                  <h3 className="text-sm font-extrabold">{doc.name || "원장"}</h3>
                  {doc.specialty ? <p className="mt-0.5 text-xs font-bold text-blue-600">{doc.specialty}</p> : null}
                  {doc.bio ? <p className="mt-1.5 line-clamp-3 text-xs text-slate-500">{doc.bio}</p> : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 이미지 + 초점 드래그 ────────────────────────────────────
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
  onUrl,
  onPosition,
}: {
  url: string;
  position: string;
  prefix: "hospital" | "doctor";
  aspect: string;
  onUrl: (url: string) => void;
  onPosition: (pos: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const drag = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const [busy, setBusy] = useState(false);

  // grab-pan: 이미지를 손으로 잡고 끄는 느낌. 드래그 방향과 같은 방향으로 사진이 따라온다
  // (object-position 은 반대로 움직여야 하므로 delta 를 뺀다).
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
      onUrl(await uploadFile(file, prefix));
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
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
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
        <div className="flex items-center justify-center rounded-lg border border-dashed border-slate-300 py-8 text-xs font-bold text-slate-400" style={{ aspectRatio: aspect }}>
          이미지 없음
        </div>
      )}
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={busy}
        className="mt-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"
      >
        {busy ? "업로드 중…" : url ? "이미지 변경" : "이미지 선택"}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
          e.target.value = ""; // 같은 파일 재선택 허용
        }}
      />
      {url ? <p className="mt-1 text-[11px] font-semibold text-slate-400">이미지를 드래그해 위치를 맞추세요.</p> : null}
    </div>
  );
}

// ── 원장 편집 카드 ──────────────────────────────────────────
function DoctorEditor({
  doc,
  onPatch,
  onSave,
  onToggleActive,
}: {
  doc: EditDoctor;
  onPatch: (p: Partial<EditDoctor>) => void;
  onSave: () => Promise<void>;
  onToggleActive: () => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  return (
    <div className={`rounded-xl border p-4 ${doc.is_active ? "border-slate-200" : "border-slate-200 bg-slate-50 opacity-70"}`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-bold text-slate-700">#{doc.doctorid} {doc.is_active ? "" : "(비활성)"}</span>
        <button
          type="button"
          onClick={() => void onToggleActive()}
          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
            doc.is_active ? "border border-rose-200 text-rose-500 hover:bg-rose-50" : "border border-blue-200 text-blue-600 hover:bg-blue-50"
          }`}
        >
          {doc.is_active ? "비활성화" : "활성화"}
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="이름"><input className={inputCls} value={doc.name} onChange={(e) => onPatch({ name: e.target.value })} /></Field>
        <Field label="전문 진료"><input className={inputCls} value={doc.specialty} onChange={(e) => onPatch({ specialty: e.target.value })} /></Field>
      </div>
      <Field label="학력"><input className={inputCls} value={doc.education} onChange={(e) => onPatch({ education: e.target.value })} /></Field>
      <Field label="소개글"><textarea className={`${inputCls} h-24 resize-none py-2`} value={doc.bio} onChange={(e) => onPatch({ bio: e.target.value })} /></Field>
      <Field label="전문 분야 (쉼표로 구분)"><TagsInput value={doc.specialtyAreas} onChange={(arr) => onPatch({ specialtyAreas: arr })} /></Field>
      <Field label="원장 사진 (드래그로 초점 조정)">
        <ImageEditor
          url={doc.profileImage}
          position={doc.profileImagePosition}
          prefix="doctor"
          aspect="4 / 5"
          onUrl={(u) => onPatch({ profileImage: u })}
          onPosition={(p) => onPatch({ profileImagePosition: p })}
        />
      </Field>
      <SaveButton
        onClick={async () => {
          setSaving(true);
          try {
            await onSave();
          } catch (e) {
            alert(e instanceof Error ? e.message : "저장 실패");
          } finally {
            setSaving(false);
          }
        }}
        saving={saving}
      />
    </div>
  );
}

// ── 진료시간 ────────────────────────────────────────────────
function HoursForm({ hours, onSave }: { hours: DaySchedule[]; onSave: (h: DaySchedule[]) => Promise<void> }) {
  const [rows, setRows] = useState<DaySchedule[]>(hours);
  const [saving, setSaving] = useState(false);
  useEffect(() => setRows(hours), [hours]);

  const patch = (dow: number, p: Partial<DaySchedule>) =>
    setRows((cur) => cur.map((r) => (r.day_of_week === dow ? { ...r, ...p } : r)));

  return (
    <Section title="진료시간">
      <div className="space-y-2">
        {[...rows].sort((a, b) => a.day_of_week - b.day_of_week).map((r) => (
          <div key={r.day_of_week} className="flex items-center gap-3">
            <span className="w-6 text-sm font-bold text-slate-700">{DAY_LABELS[r.day_of_week] ?? r.day_of_week}</span>
            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              <input type="checkbox" checked={r.is_open} onChange={(e) => patch(r.day_of_week, { is_open: e.target.checked })} /> 진료
            </label>
            <input type="time" disabled={!r.is_open} value={r.start_time || ""} onChange={(e) => patch(r.day_of_week, { start_time: e.target.value })} className="h-9 rounded-lg border border-slate-200 px-2 text-sm disabled:bg-slate-50" />
            <span className="text-slate-400">~</span>
            <input type="time" disabled={!r.is_open} value={r.end_time || ""} onChange={(e) => patch(r.day_of_week, { end_time: e.target.value })} className="h-9 rounded-lg border border-slate-200 px-2 text-sm disabled:bg-slate-50" />
          </div>
        ))}
      </div>
      <SaveButton onClick={async () => { setSaving(true); try { await onSave(rows); } finally { setSaving(false); } }} saving={saving} />
    </Section>
  );
}

// ── 원장 추가 ───────────────────────────────────────────────
function AddDoctorForm({ hid, onAdded }: { hid: number; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await addDoctor(hid, { name: name.trim(), specialty: specialty.trim() || undefined, specialtyAreas: [] });
      setName(""); setSpecialty(""); setOpen(false);
      onAdded();
    } catch (e) {
      alert(e instanceof Error ? e.message : "추가 실패");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-3 w-full rounded-xl border border-dashed border-slate-300 py-3 text-sm font-bold text-slate-500 transition hover:bg-slate-50">
        + 원장 추가
      </button>
    );
  }
  return (
    <div className="mt-3 rounded-xl border border-blue-200 bg-blue-50/40 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="이름 *"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="전문 진료"><input className={inputCls} value={specialty} onChange={(e) => setSpecialty(e.target.value)} /></Field>
      </div>
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={() => void submit()} disabled={saving || !name.trim()} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-700 disabled:bg-slate-300">
          {saving ? "추가 중…" : "추가"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-bold text-slate-600 transition hover:bg-slate-50">취소</button>
      </div>
      <p className="mt-2 text-xs font-semibold text-slate-400">추가 후 카드에서 사진·경력·소개를 채울 수 있어요. (예약은 수의사웹에서 원장 진료시간 설정 후 가능)</p>
    </div>
  );
}

// ── 공용 ────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-black text-slate-900">{title}</h2>
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
    <button type="button" onClick={onClick} disabled={saving} className="mt-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-bold text-white transition hover:bg-blue-700 disabled:bg-slate-300">
      {saving ? "저장 중…" : "저장"}
    </button>
  );
}

// 쉼표 태그 입력 — 내부 텍스트 버퍼 유지, 정리된 배열을 emit(타이핑 매끄럽게).
function TagsInput({ value, onChange }: { value: string[]; onChange: (arr: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  // 외부에서 value가 바뀌면(다른 병원 로드 등) 동기화
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current !== value && value.join(", ") !== text) {
      setText(value.join(", "));
    }
    prev.current = value;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <input
      className={inputCls}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean));
      }}
    />
  );
}
