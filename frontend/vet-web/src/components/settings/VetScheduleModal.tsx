import { useEffect, useState } from "react";
import { X } from "lucide-react";
import {
  type DaySchedule,
  fetchVetWeeklySchedule,
  getSettingsApiErrorMessage,
  updateVetWeeklySchedule,
} from "../../api/settingsApi";
import { fetchHospitalDoctors, type DoctorInfo } from "../../api/emrApi";
import type { AuthSession } from "../../api/authApi";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";
import { defaultWeek, InlineTimeSelect } from "./settingsShared";

interface Props {
  session: AuthSession;
  onClose: () => void;
  onOpenDetail: (vetId?: number) => void;
}

type VetBasicTimes = {
  start_time: string;
  end_time: string;
  lunch_start: string;
  lunch_end: string;
};

export function VetScheduleModal({ session, onClose, onOpenDetail }: Props) {
  const [doctors, setDoctors] = useState<DoctorInfo[]>([]);
  const [vetTimes, setVetTimes] = useState<Record<number, VetBasicTimes>>({});
  const [vetSchedules, setVetSchedules] = useState<Record<number, DaySchedule[]>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEscapeToClose(onClose, !saving);

  useEffect(() => {
    async function load() {
      const docs = await fetchHospitalDoctors(session.accessToken);
      const entries = await Promise.all(
        docs.map(async (d) => {
          const sched = await fetchVetWeeklySchedule(session.accessToken, d.doctorid);
          return [d.doctorid, sched] as [number, DaySchedule[]];
        })
      );
      const schedMap = Object.fromEntries(entries) as Record<number, DaySchedule[]>;
      const timesMap: Record<number, VetBasicTimes> = {};
      for (const doc of docs) {
        const sched = schedMap[doc.doctorid] ?? [];
        const ref = sched.find((s) => s.is_open && s.start_time) ?? sched[0];
        timesMap[doc.doctorid] = {
          start_time: ref?.start_time ?? "09:00",
          end_time: ref?.end_time ?? "18:00",
          lunch_start: ref?.lunch_start ?? "12:00",
          lunch_end: ref?.lunch_end ?? "13:00",
        };
      }
      setDoctors(docs);
      setVetSchedules(schedMap);
      setVetTimes(timesMap);
    }
    load()
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [session.accessToken]);

  const updateVetTime = (doctorid: number, patch: Partial<VetBasicTimes>) => {
    setVetTimes((prev) => ({ ...prev, [doctorid]: { ...prev[doctorid], ...patch } }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await Promise.all(
        doctors.map(async (doc) => {
          const times = vetTimes[doc.doctorid];
          if (!times) return;
          const prevSched = vetSchedules[doc.doctorid] ?? defaultWeek;
          const newSched: DaySchedule[] = prevSched.map((d) =>
            d.is_open
              ? {
                  ...d,
                  start_time: times.start_time,
                  end_time: times.end_time,
                  lunch_start: times.lunch_start,
                  lunch_end: times.lunch_end,
                }
              : d
          );
          await updateVetWeeklySchedule(session.accessToken, doc.doctorid, newSched);
        })
      );
      onClose();
    } catch (err: unknown) {
      setError(getSettingsApiErrorMessage(err, "저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">의사별 근무 시간 설정</h2>
            <p className="mt-0.5 text-xs font-semibold text-slate-400">
              수의사별 출퇴근/퇴근/점심 시간을 설정할 수 있습니다.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 테이블 */}
        <div className="px-6 py-4">
          {loading ? (
            <p className="py-8 text-center text-sm text-slate-400">수의사 정보를 불러오는 중...</p>
          ) : doctors.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">등록된 수의사가 없습니다.</p>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">수의사</th>
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">출근 시간</th>
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">퇴근 시간</th>
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">점심 시작</th>
                  <th className="pb-2 text-left text-xs font-extrabold text-slate-500">점심 종료</th>
                </tr>
              </thead>
              <tbody>
                {doctors.map((doc) => {
                  const times = vetTimes[doc.doctorid];
                  if (!times) return null;
                  return (
                    <tr key={doc.doctorid} className="border-b border-slate-50 last:border-0">
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-extrabold text-blue-700">
                            {doc.doctor_name.charAt(0)}
                          </div>
                          <span className="whitespace-nowrap text-sm font-bold text-slate-800">
                            {doc.doctor_name}
                          </span>
                        </div>
                      </td>
                      <td className="py-3">
                        <InlineTimeSelect
                          value={times.start_time}
                          onChange={(v) => updateVetTime(doc.doctorid, { start_time: v })}
                        />
                      </td>
                      <td className="py-3">
                        <InlineTimeSelect
                          value={times.end_time}
                          onChange={(v) => updateVetTime(doc.doctorid, { end_time: v })}
                        />
                      </td>
                      <td className="py-3">
                        <InlineTimeSelect
                          value={times.lunch_start}
                          onChange={(v) => updateVetTime(doc.doctorid, { lunch_start: v })}
                        />
                      </td>
                      <td className="py-3">
                        <InlineTimeSelect
                          value={times.lunch_end}
                          onChange={(v) => updateVetTime(doc.doctorid, { lunch_end: v })}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {error && <p className="mt-3 text-xs font-bold text-red-600">{error}</p>}

          <p className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-slate-400">
            <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-300 text-[10px] font-extrabold">
              i
            </span>
            요일별로 다른 근무 시간을 설정하려면, 하단의 '상세 설정'에서 설정할 수 있습니다.
          </p>
        </div>

        {/* 푸터 */}
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4">
          <button
            type="button"
            onClick={() => onOpenDetail()}
            className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-extrabold text-slate-600 hover:bg-slate-50"
          >
            상세 설정
          </button>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="h-10 rounded-lg border border-slate-200 px-5 text-sm font-extrabold text-slate-600 hover:bg-slate-50"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || loading}
              className="h-10 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white hover:bg-blue-700 disabled:bg-blue-200"
            >
              {saving ? "저장 중..." : "저장"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
