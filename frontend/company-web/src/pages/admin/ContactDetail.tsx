import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Send } from "lucide-react";
import { getContact, replyContact, type ContactInquiryOut } from "../../onboarding/api";

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-bold text-slate-800">{value || "-"}</p>
    </div>
  );
}

export default function ContactDetail() {
  const { id } = useParams();
  const contactId = Number(id);
  const [inquiry, setInquiry] = useState<ContactInquiryOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [replyMsg, setReplyMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    getContact(contactId)
      .then((data) => {
        setInquiry(data);
        setSent(data.is_replied);
      })
      .catch(() => setInquiry(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (Number.isFinite(contactId)) load();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactId]);

  const handleReply = async () => {
    if (!replyMsg.trim()) return;
    setSending(true);
    setError("");
    try {
      await replyContact(contactId, replyMsg.trim());
      setSent(true);
      setReplyMsg("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "답장 발송에 실패했습니다.");
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="h-40 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    );
  }

  if (!inquiry) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <Link to="/admin/contacts" className="text-sm font-bold text-blue-600">← 목록으로</Link>
        <p className="mt-6 text-sm font-bold text-slate-500">문의를 찾을 수 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <Link
        to="/admin/contacts"
        className="flex w-fit items-center gap-1 text-sm font-bold text-slate-500 hover:text-blue-700"
      >
        <ArrowLeft className="h-4 w-4" /> 목록으로
      </Link>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-black text-slate-900">{inquiry.name}님의 문의</h1>
        <span className="text-sm font-semibold text-slate-400">
          {new Date(inquiry.created_at).toLocaleString("ko-KR")}
        </span>
      </div>

      {/* 발신자 정보 */}
      <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-black text-slate-700">문의자 정보</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <InfoRow label="이름" value={inquiry.name} />
          <InfoRow label="유형" value={inquiry.user_type} />
          <InfoRow label="연락처" value={inquiry.phone} />
          <InfoRow label="이메일" value={inquiry.email} />
        </div>
      </section>

      {/* 문의 내용 */}
      <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-black text-slate-700">문의 내용</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm font-medium leading-6 text-slate-700">
          {inquiry.message}
        </p>
      </section>

      {/* 답장 완료 배지 */}
      {inquiry.is_replied && (
        <div className="mt-4 flex items-center gap-2 rounded-2xl border border-green-200 bg-green-50 px-5 py-3">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
          <p className="text-sm font-bold text-green-800">답장이 발송되었습니다.</p>
        </div>
      )}

      {/* 답장 작성 */}
      {!inquiry.is_replied && (
        <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-black text-slate-700">
            답장 발송{" "}
            <span className="font-semibold text-slate-400">→ {inquiry.email}</span>
          </h2>
          <textarea
            value={replyMsg}
            onChange={(e) => setReplyMsg(e.target.value)}
            rows={6}
            placeholder="답장 내용을 입력하세요..."
            className="mt-3 w-full resize-y rounded-xl border border-slate-200 px-4 py-3 text-sm font-medium outline-none placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
          />

          {error && (
            <p className="mt-2 text-xs font-bold text-red-500">{error}</p>
          )}

          {sent && !inquiry.is_replied && (
            <div className="mt-2 flex items-center gap-2 text-sm font-bold text-green-700">
              <CheckCircle2 className="h-4 w-4" /> 답장이 발송되었습니다.
            </div>
          )}

          <button
            type="button"
            onClick={handleReply}
            disabled={sending || !replyMsg.trim()}
            className="mt-4 flex h-11 items-center gap-2 rounded-full bg-blue-600 px-6 text-sm font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            {sending ? "발송 중..." : "답장 보내기"}
          </button>
        </section>
      )}
    </div>
  );
}
