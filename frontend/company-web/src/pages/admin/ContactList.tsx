import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listContacts, type ContactInquiryOut } from "../../onboarding/api";

const USER_TYPE_LABELS: Record<string, string> = {
  보호자: "보호자",
  동물병원: "동물병원",
  "제휴/협업": "제휴/협업",
  기타: "기타",
};

export default function ContactList() {
  const [items, setItems] = useState<ContactInquiryOut[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    listContacts()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="h-40 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-2xl font-black text-slate-900">홈페이지 문의</h1>
      <p className="mt-1 text-sm font-semibold text-slate-400">
        총 {items.length}건 · 미답변 {items.filter((i) => !i.is_replied).length}건
      </p>

      {items.length === 0 ? (
        <div className="mt-10 rounded-2xl border border-dashed border-slate-200 py-16 text-center text-sm font-bold text-slate-400">
          접수된 문의가 없습니다.
        </div>
      ) : (
        <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-left text-xs font-black text-slate-500">
                <th className="px-5 py-3">#</th>
                <th className="px-5 py-3">이름</th>
                <th className="px-5 py-3">유형</th>
                <th className="px-5 py-3">이메일</th>
                <th className="px-5 py-3">접수일</th>
                <th className="px-5 py-3">상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  onClick={() => navigate(`/admin/contacts/${item.id}`)}
                  className="cursor-pointer border-b border-slate-100 transition hover:bg-blue-50 last:border-none"
                >
                  <td className="px-5 py-3.5 font-bold text-slate-400">{item.id}</td>
                  <td className="px-5 py-3.5 font-bold text-slate-800">{item.name}</td>
                  <td className="px-5 py-3.5">
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-600">
                      {USER_TYPE_LABELS[item.user_type] ?? item.user_type}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-slate-600">{item.email}</td>
                  <td className="px-5 py-3.5 text-slate-500">
                    {new Date(item.created_at).toLocaleString("ko-KR", {
                      year: "numeric",
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td className="px-5 py-3.5">
                    {item.is_replied ? (
                      <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-bold text-green-700">
                        답변 완료
                      </span>
                    ) : (
                      <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-700">
                        미답변
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
