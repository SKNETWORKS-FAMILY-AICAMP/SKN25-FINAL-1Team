import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText, KeyRound } from "lucide-react";

import {
  approveApplication,
  getApplication,
  rejectApplication,
  type ApplicationOut,
} from "../../onboarding/api";
import { HospitalPreview } from "../../onboarding/preview";
import StatusBadge from "./StatusBadge";

function DocLink({ label, url }: { label: string; url?: string | null }) {
  if (!url) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-xs font-bold text-slate-400">
        {label}: 미첨부
      </div>
    );
  }
  const isImage = /\.(png|jpe?g|webp|gif)$/i.test(url);
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 transition hover:border-blue-200"
    >
      {isImage ? (
        <img src={url} alt={label} className="h-12 w-12 rounded-lg object-cover" />
      ) : (
        <FileText className="h-8 w-8 text-slate-400" />
      )}
      <div className="min-w-0">
        <p className="text-xs font-bold text-slate-400">{label}</p>
        <p className="truncate text-sm font-bold text-blue-600">서류 보기</p>
      </div>
    </a>
  );
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-bold text-slate-800">{value || "-"}</p>
    </div>
  );
}

export default function ApplicationDetail() {
  const { id } = useParams();
  const reqId = Number(id);
  const [app, setApp] = useState<ApplicationOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [issued, setIssued] = useState<{ loginid: string; temp_password: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    getApplication(reqId)
      .then((a) => setApp(a))
      .catch(() => setApp(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (Number.isFinite(reqId)) load();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqId]);

  const handlePublish = async () => {
    setBusy(true);
    try {
      const result = await approveApplication(reqId);
      setIssued({ loginid: result.loginid, temp_password: result.temp_password });
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "발행 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    const reason = window.prompt("반려 사유를 입력하세요");
    if (reason === null) return;
    setBusy(true);
    try {
      await rejectApplication(reqId, reason.trim());
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "반려 실패");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="h-40 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    );
  }

  if (!app) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <Link to="/admin" className="text-sm font-bold text-blue-600">← 목록으로</Link>
        <p className="mt-6 text-sm font-bold text-slate-500">신청을 찾을 수 없습니다.</p>
      </div>
    );
  }

  const published = app.status === "승인발행";

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
        <span className="text-sm font-semibold text-slate-400">
          신청일 {app.createdAt ? new Date(app.createdAt).toLocaleString("ko-KR") : "-"}
        </span>
      </div>

      {/* 발행 결과 / 반려 사유 */}
      {published ? (
        <div className="mt-5 flex items-start gap-3 rounded-2xl border border-green-200 bg-green-50 p-4">
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-green-600" />
          <div className="text-sm font-bold text-green-800">
            발행 완료 — 계정이 생성되었습니다.
            {issued ? (
              <div className="mt-1 font-semibold text-green-700">
                로그인 아이디: <span className="font-black">{issued.loginid}</span> · 임시 비밀번호:{" "}
                <span className="font-black">{issued.temp_password}</span>
              </div>
            ) : (
              <div className="mt-1 font-semibold text-green-700">
                로그인 아이디: <span className="font-black">{app.desiredLoginId}</span> (임시 비밀번호는 발행 시 1회 표시)
              </div>
            )}
            <p className="mt-1 text-xs font-medium text-green-600">
              실제로는 {app.ownerEmail || "대표 이메일"} 로 자동 발송됩니다.
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
          <DocLink label="사업자등록증" url={app.businessLicenseUrl} />
          {app.doctors.map((d, i) => (
            <DocLink key={i} label={`${d.name || `원장 ${i + 1}`} 면허증`} url={d.licenseUrl} />
          ))}
        </div>
      </section>

      {/* 보호자 페이지 미리보기 */}
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-black text-slate-700">보호자에게 보이는 화면 (미리보기)</h2>
        <HospitalPreview app={app} />
      </section>

      {/* 액션 */}
      {!published && app.status !== "반려" ? (
        <div className="sticky bottom-0 mt-6 flex gap-3 border-t border-slate-200 bg-slate-50/80 py-4 backdrop-blur">
          <button type="button" onClick={handlePublish} disabled={busy} className="mp-btn-primary flex-1">
            페이지 등록하기 (발행)
          </button>
          <button
            type="button"
            onClick={handleReject}
            disabled={busy}
            className="inline-flex h-11 items-center justify-center rounded-full border border-rose-200 bg-white px-5 text-sm font-bold text-rose-500 transition hover:bg-rose-50 disabled:opacity-50"
          >
            반려
          </button>
        </div>
      ) : null}
    </div>
  );
}
