import { useMemo, useState } from "react";
import {
  Bell,
  Building2,
  CalendarCheck,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock3,
  Home,
  LockKeyhole,
  LogOut,
  Plus,
  RefreshCcw,
  Search,
  Settings,
  UsersRound,
} from "lucide-react";
import petProfile from "../../assets/demo/profile-mangmang.png";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

type VetMenu = "home" | "emr" | "reservation" | "patients" | "hospital-manage" | "settings";
type TriageType = "응급" | "준긴급" | "일반" | "완료";

interface ScheduleItem {
  id: number;
  time: string;
  end: string;
  petName: string;
  species: string;
  guardian: string;
  doctor: string;
  type: TriageType;
  top: number;
  height: number;
  column?: number;
}

const menus: Array<{ id: VetMenu; label: string; Icon: typeof Home }> = [
  { id: "home", label: "홈", Icon: Home },
  { id: "emr", label: "EMR", Icon: ClipboardList },
  { id: "reservation", label: "예약 관리", Icon: CalendarDays },
  { id: "patients", label: "환자 관리", Icon: UsersRound },
  { id: "hospital-manage", label: "병원 관리", Icon: Building2 },
  { id: "settings", label: "설정", Icon: Settings },
];

const schedules: ScheduleItem[] = [
  { id: 1, time: "09:00", end: "09:30", petName: "뽀삐", species: "강아지", guardian: "김보호자", doctor: "김수의", type: "준긴급", top: 18, height: 54 },
  { id: 2, time: "09:30", end: "10:00", petName: "나비", species: "고양이", guardian: "이영희", doctor: "김수의", type: "일반", top: 78, height: 54 },
  { id: 3, time: "10:00", end: "10:40", petName: "뭉치", species: "강아지", guardian: "박민준", doctor: "박진료", type: "응급", top: 138, height: 72 },
  { id: 4, time: "11:00", end: "11:30", petName: "복실이", species: "강아지", guardian: "최수진", doctor: "박진료", type: "일반", top: 258, height: 54 },
  { id: 5, time: "14:00", end: "14:30", petName: "하루", species: "고양이", guardian: "정다은", doctor: "김수의", type: "완료", top: 570, height: 54 },
];

const patientDetails = {
  name: "뽀삐",
  species: "강아지",
  breed: "말티즈",
  age: "3살",
  weight: "8.5kg",
  guardian: "김보호자",
  summary: [
    "2~3일 전부터 구토/설사 증상 호소",
    "식욕 저하 동반, 활력 감소는 뚜렷하지 않음",
    "최근 사료 변경 이력 있음",
  ],
  soap: `[S] 보호자 보고: 2~3일 전부터 구토와 설사, 식욕 저하.
[O] 체중 8.5kg, 체온 38.8도. 복부 촉진 시 약간 긴장.
[A] 급성 위장관염 의심. 식이 변경 관련 가능성.
[P] 혈액검사 및 복부초음파 권고. 수액치료, 구토억제제 처방 검토.`,
};

function PawLogo() {
  return (
    <span className="flex items-center gap-2">
      <img src={medipawSymbol} alt="MediPaw" className="h-9 w-auto" />
    </span>
  );
}

function VetLayout({
  activeMenu,
  onNavigate,
  children,
}: {
  activeMenu: VetMenu;
  onNavigate: (menu: VetMenu) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="h-screen overflow-hidden bg-slate-50 text-slate-800">
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-3">
        <button
          type="button"
          onClick={() => onNavigate("home")}
          className="flex items-center rounded-lg p-1"
          aria-label="홈으로 이동"
        >
          <PawLogo />
        </button>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-2 text-xs font-bold tabular-nums text-slate-700 md:flex">
            <Clock3 className="h-4 w-4 text-blue-600" />
            <span>2026.06.17 (수) 09:45:21</span>
          </div>
          <button
            type="button"
            className="relative flex h-8 w-8 items-center justify-center rounded-lg border-l border-r border-slate-100 text-blue-600 transition hover:bg-slate-50"
            aria-label="알림"
          >
            <Bell className="h-4 w-4" />
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500" />
          </button>
          <button
            type="button"
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-extrabold text-slate-800 transition hover:bg-slate-50"
          >
            <span>해피펫 동물병원</span>
            <ChevronDown className="h-4 w-4 text-slate-500" />
          </button>
        </div>
      </header>

      <div className="flex pt-14">
        <aside className="fixed bottom-0 left-0 top-14 z-20 flex w-40 flex-col justify-between border-r border-slate-200 bg-white px-2.5 py-3">
          <nav className="space-y-1.5" aria-label="주요 메뉴">
            {menus.map(({ id, label, Icon }) => {
              const isActive = id === activeMenu;
              return (
                <button
                  type="button"
                  key={id}
                  onClick={() => onNavigate(id)}
                  className={[
                    "flex h-10 w-full items-center gap-2 rounded-lg px-2.5 text-left text-xs font-extrabold transition",
                    isActive
                      ? "bg-blue-50 text-blue-600"
                      : "text-slate-800 hover:bg-slate-50 hover:text-blue-600",
                  ].join(" ")}
                >
                  <Icon className="h-4 w-4 shrink-0 text-blue-600" />
                  <span className="truncate">{label}</span>
                </button>
              );
            })}
          </nav>

          <section className="rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm">
            <p className="text-[10px] font-bold text-slate-600">수의사 계정</p>
            <p className="mt-0.5 truncate text-xs font-extrabold text-slate-800">김수의 원장</p>
            <div className="mt-2 border-t border-slate-100 pt-2">
              <p className="text-[10px] font-bold text-slate-600">마지막 로그인</p>
              <p className="mt-0.5 text-[10px] font-extrabold tabular-nums text-slate-800">
                2026.06.17 08:51
              </p>
            </div>
            <button
              type="button"
              className="mt-2 flex h-8 w-full items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white text-xs font-extrabold text-slate-600"
            >
              <LogOut className="h-3.5 w-3.5" />
              로그아웃
            </button>
          </section>
        </aside>

        <main className="ml-40 h-[calc(100vh-56px)] flex-1 overflow-y-auto bg-slate-50 px-4 pb-8 pt-5">
          {children}
        </main>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  wrapper,
  valueClass,
}: {
  label: string;
  value: string;
  wrapper: string;
  valueClass: string;
}) {
  return (
    <article className={`flex h-20 w-36 flex-col justify-center rounded-lg px-4 ${wrapper}`}>
      <p className={`text-2xl font-extrabold leading-none tabular-nums ${valueClass}`}>{value}</p>
      <p className="mt-2 text-xs font-extrabold text-slate-500">{label}</p>
    </article>
  );
}

function TriageBadge({ type }: { type: TriageType }) {
  const tone: Record<TriageType, string> = {
    응급: "bg-red-50 text-red-600 border-red-100",
    준긴급: "bg-[#FFFBEB] text-[#D97706] border-[#FDE68A]",
    일반: "bg-slate-50 text-slate-600 border-slate-200",
    완료: "bg-[#E6F4EA] text-[#137333] border-[#CEEAD6]",
  };
  return (
    <span className={`inline-flex h-6 shrink-0 items-center whitespace-nowrap rounded-md border px-2 text-xs font-extrabold ${tone[type]}`}>
      {type === "준긴급" ? "준응급" : type === "완료" ? "검진" : type}
    </span>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return <section className="rounded-lg border border-slate-200 bg-white shadow-sm">{children}</section>;
}

function WorkspacePane({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-slate-50">
      <div className="flex h-8 shrink-0 items-center justify-between border-b border-slate-300 bg-slate-100 px-2.5">
        <h2 className="truncate text-[12px] font-extrabold text-slate-800">{title}</h2>
        {meta ? (
          <span className="ml-2 shrink-0 rounded bg-white/70 px-1.5 py-0.5 text-[10px] font-extrabold text-slate-500">
            {meta}
          </span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1.5 flex flex-col">
        {children}
      </div>
    </section>
  );
}

function StaticSplitHandle() {
  return (
    <div className="relative w-1 shrink-0 bg-slate-300">
      <span className="absolute left-1/2 top-1/2 h-10 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/70" />
    </div>
  );
}

function TimelinePanel() {
  const hourTicks = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"];
  const hourHeight = 56;
  return (
    <Panel>
      <div className="flex items-center gap-4 border-b border-slate-100 px-5 py-3">
        <h2 className="text-lg font-extrabold tracking-normal text-slate-900">오늘의 일정</h2>
        <div className="hidden items-center gap-2 text-sm font-extrabold text-slate-600 lg:flex">
          <CalendarCheck className="h-4 w-4 text-blue-600" />
          <span>진료실 1</span>
          <span className="text-xs font-bold text-slate-500">수의사: 김수의, 박진료</span>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {["김수의", "박진료"].map((name, index) => (
            <div key={name} className="flex items-center gap-1.5">
              <span className={`h-2.5 w-2.5 rounded-full ${index === 0 ? "bg-teal-500" : "bg-orange-300"}`} />
              <span className="text-xs font-bold text-slate-600">{name}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="px-5 py-3">
        <div className="grid grid-cols-[56px_1fr] gap-2">
          <div className="relative h-[448px]">
            {hourTicks.map((tick, index) => (
              <div
                key={tick}
                className="absolute left-0 text-xs font-extrabold tabular-nums text-slate-600"
                style={{ top: index * hourHeight }}
              >
                {tick}
              </div>
            ))}
          </div>
          <div className="relative h-[448px] overflow-hidden rounded-lg border border-slate-100 bg-white">
            {hourTicks.map((tick, index) => (
              <div key={tick} className="absolute left-0 right-0 border-t border-slate-100" style={{ top: index * hourHeight }} />
            ))}
            <div className="absolute inset-x-0 flex items-center bg-slate-100 px-3 text-xs font-extrabold text-slate-600" style={{ top: 168, height: 56 }}>
              12:00 - 13:00 <span className="ml-5">점심시간</span>
            </div>
            <div className="absolute bottom-0 top-0 z-[3] border-l border-slate-100" style={{ left: "50%" }} />
            {schedules.map((item) => {
              const doctorIndex = item.doctor === "김수의" ? 0 : 1;
              const left = `calc(${doctorIndex * 50}% + 4px)`;
              const width = "calc(50% - 8px)";
              const bar = doctorIndex === 0 ? "before:bg-teal-500" : "before:bg-orange-300";
              return (
                <article
                  key={item.id}
                  className={`absolute z-10 flex items-center justify-between gap-3 overflow-hidden rounded-lg border border-slate-200 bg-white py-2 pl-5 pr-3.5 text-left shadow-[0_4px_12px_rgba(15,23,42,0.08)] before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg ${bar}`}
                  style={{ top: item.top * (hourHeight / 96), height: Math.max(item.height * (hourHeight / 96), 36), left, width }}
                >
                  <div className="grid min-w-0 flex-1 grid-cols-[92px_minmax(100px,1fr)] items-center gap-4">
                    <p className="text-xs font-extrabold tabular-nums text-slate-600">
                      {item.time}-{item.end}
                    </p>
                    <p className="truncate text-sm font-extrabold text-slate-800">
                      {item.petName} ({item.species})
                    </p>
                  </div>
                  <TriageBadge type={item.type} />
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function HomeView() {
  return (
    <div className="flex min-h-[calc(100vh-160px)] min-w-0 flex-col overflow-y-auto">
      <div className="mb-4 flex min-w-0 items-start gap-6">
        <div className="min-w-0 shrink-0">
          <h1 className="text-2xl font-extrabold text-slate-900">오늘의 진료 현황</h1>
          <p className="mt-2 text-sm font-bold tabular-nums text-slate-500">2026.06.18 (목)</p>
        </div>
        <div className="grid w-fit grid-cols-4 gap-3 pt-1">
          <SummaryCard label="전체 예약" value="5" wrapper="bg-slate-50" valueClass="text-blue-500" />
          <SummaryCard label="대기 중" value="4" wrapper="bg-amber-50" valueClass="text-amber-700" />
          <SummaryCard label="응급" value="1" wrapper="bg-[#FFEFEF]" valueClass="text-[#E11D48]" />
          <SummaryCard label="진료 완료" value="1" wrapper="bg-slate-50" valueClass="text-slate-600" />
        </div>
      </div>
      <TimelinePanel />
    </div>
  );
}

function EmrView() {
  return (
    <div className="relative h-[calc(100vh-74px)] min-h-0 overflow-hidden text-[12px]">
      <div className="flex h-full min-h-0 overflow-hidden rounded-md border border-slate-300 bg-slate-200">
        <div className="min-w-0 basis-[22%]">
          <WorkspacePane title="접수 / 대기" meta="1명">
            <div className="flex min-h-0 flex-1 flex-col gap-1.5">
              <Panel>
                <div className="px-4 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h2 className="text-sm font-extrabold text-slate-900">오늘 1건 대기 중</h2>
                      <p className="mt-0.5 text-xs font-bold text-slate-400">갱신 오전 11:12</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <span className="text-xs font-bold text-slate-400">수의사</span>
                      <select className="h-7 w-auto rounded-lg border border-slate-200 bg-white px-2 text-xs font-extrabold text-slate-700 outline-none">
                        <option>관리자</option>
                      </select>
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-[32px_minmax(0,1fr)_32px_48px_32px] gap-1.5">
                    <button type="button" className="h-8 rounded-lg border border-slate-200 text-slate-600">‹</button>
                    <div className="flex h-8 items-center justify-center rounded-lg border border-slate-200 text-xs font-extrabold tabular-nums text-slate-600">
                      2026.06.18
                    </div>
                    <button type="button" className="h-8 rounded-lg border border-slate-200 text-slate-600">›</button>
                    <button type="button" className="h-8 rounded-lg border border-slate-200 text-xs font-extrabold text-slate-600">오늘</button>
                    <button type="button" className="h-8 rounded-lg bg-teal-50 text-xs font-extrabold text-teal-700">↻</button>
                  </div>
                </div>
                <div className="grid grid-cols-2 border-y border-slate-100 bg-slate-50 p-1">
                  <button type="button" className="h-8 rounded-md bg-white text-sm font-extrabold text-teal-700 shadow-sm">
                    진료 대기 1
                  </button>
                  <button type="button" className="h-8 rounded-md text-sm font-extrabold text-slate-500">
                    진료 완료 0
                  </button>
                </div>
                <table className="w-full table-fixed text-left">
                  <tbody>
                    <tr className="bg-slate-50 text-xs text-slate-500">
                      <td className="w-[72px] px-4 py-3 font-extrabold tabular-nums">14:30</td>
                      <td className="px-3 py-3">
                        <p className="font-extrabold text-slate-800">뽀미</p>
                        <p className="mt-0.5 truncate font-bold text-slate-400">테스트보호자 · 말티즈</p>
                      </td>
                      <td className="w-[72px] px-2 py-3">
                        <TriageBadge type="일반" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </Panel>

              <Panel>
                <div className="relative px-5 py-4">
                  <div className="flex items-center gap-4 pr-10">
                    <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-3xl font-black text-slate-300">
                      🐾
                    </div>
                    <div className="flex min-w-0 items-center gap-3">
                      <h1 className="text-2xl font-extrabold text-slate-900">뽀미</h1>
                      <span className="text-2xl font-extrabold text-rose-500">♀</span>
                    </div>
                  </div>
                  <p className="mt-3 text-sm font-extrabold text-slate-600">
                    말티즈 | 암컷 | 3.2kg | 5살(2021-03-15)
                  </p>
                  <p className="mt-2 text-sm font-extrabold text-slate-600">최근 내원일: 2026-06-16</p>
                  <p className="mt-2 text-sm font-extrabold text-slate-600">마지막 정기검진일: 검진 이력 없음</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-md bg-slate-50 px-2.5 py-1 text-xs font-extrabold text-slate-600">중성화 O</span>
                  </div>
                </div>
              </Panel>
            </div>
          </WorkspacePane>
        </div>

        <StaticSplitHandle />

        <div className="min-w-0 basis-[28%]">
          <WorkspacePane title="사전 문진 / 히스토리" meta="뽀미">
            <div className="flex flex-1 flex-col gap-1.5">
              <Panel>
                <div className="border-b border-slate-100 px-4 py-2.5">
                  <h2 className="text-base font-extrabold text-slate-900">사전 문진 / 메모</h2>
                </div>
                <div className="space-y-2 px-4 py-3">
                  <button type="button" className="h-10 w-full rounded-md bg-teal-700 text-xs font-extrabold text-white">
                    사전문진 + 메모 전체 옮기기
                  </button>
                  <div className="rounded-lg border border-teal-100 bg-teal-50/60 px-3 py-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-extrabold text-slate-900">AI 요약 문진</p>
                      <button type="button" className="h-7 rounded-md border border-slate-200 bg-white px-2 text-xs font-extrabold text-slate-400">옮기기</button>
                    </div>
                    <p className="mt-3 text-xs font-bold leading-5 text-slate-400">예약 사전문진 내용이 없습니다.</p>
                  </div>
                  <div className="rounded-lg border border-teal-100 bg-teal-50/60 px-3 py-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-extrabold text-slate-900">메모</p>
                      <button type="button" className="h-7 rounded-md border border-slate-200 bg-white px-2 text-xs font-extrabold text-slate-400">옮기기</button>
                    </div>
                    <p className="mt-3 text-xs font-bold leading-5 text-slate-700">수의사 메모가 없습니다.</p>
                  </div>
                  <p className="pt-1 text-xs font-extrabold text-slate-900">첨부 파일</p>
                  <div className="rounded-lg bg-slate-50 px-4 py-4 text-center text-xs font-extrabold text-slate-400">
                    보호자 첨부 파일 없음
                  </div>
                </div>
              </Panel>

              <Panel>
                <div className="border-b border-slate-100 px-4 py-2.5">
                  <h2 className="text-base font-extrabold text-slate-900">과거 문진 기록</h2>
                </div>
                <div className="space-y-3 px-4 py-3">
                  <article className="rounded-lg border border-slate-200 p-3">
                    <div className="grid grid-cols-[92px_1fr] gap-3">
                      <p className="text-sm font-extrabold tabular-nums text-slate-600">2026-06-16</p>
                      <div>
                        <p className="text-sm font-extrabold text-slate-900">두통</p>
                        <p className="mt-2 text-xs font-bold text-slate-400">관리자</p>
                      </div>
                    </div>
                    <div className="mt-3 rounded-lg bg-slate-50 p-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-extrabold text-teal-700">처방전</p>
                        <button type="button" className="text-xs font-extrabold text-slate-600">펼치기</button>
                      </div>
                      <div className="mt-3 overflow-hidden rounded-md border border-slate-200 bg-white text-[11px] font-bold text-slate-500">
                        <div className="grid grid-cols-[1fr_64px_86px_48px] bg-slate-50 px-2 py-1.5">
                          <span>약제명</span><span>용량</span><span>형태</span><span>기간</span>
                        </div>
                        {["테타눔산 24%(...) | 1ml | IV(정맥) | 3일", "호미오캄(HOM...) | 0.5ml | SC(피하) | 3일"].map((row) => {
                          const cells = row.split(" | ");
                          return (
                            <div key={row} className="grid grid-cols-[1fr_64px_86px_48px] border-t border-slate-100 px-2 py-1.5">
                              {cells.map((cell) => <span key={cell} className="truncate">{cell}</span>)}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </article>
                </div>
              </Panel>
            </div>
          </WorkspacePane>
        </div>

        <StaticSplitHandle />

        <div className="min-w-0 flex-1">
          <WorkspacePane title="진료 / 첨부 / 처방" meta="작성 가능">
            <div className="flex flex-1 flex-col gap-1.5">
              <Panel>
                <div className="border-b border-slate-100 px-4 py-2.5">
                  <div className="flex items-center justify-between">
                    <h2 className="text-base font-extrabold text-slate-900">현재 진료 내용 입력</h2>
                    <button type="button" className="h-8 rounded-md bg-teal-700 px-3 text-xs font-extrabold text-white">
                      진료 완료
                    </button>
                  </div>
                </div>
                <div className="space-y-4 p-4">
                  <textarea
                    readOnly
                    placeholder="진료 내용을 입력하세요..."
                    className="h-52 w-full resize-none rounded-md border border-slate-200 bg-white p-3 text-xs font-bold leading-5 text-slate-700 outline-none placeholder:text-slate-400"
                  />
                  <div className="border-t border-slate-100 pt-4">
                    <h3 className="mb-3 text-sm font-extrabold text-slate-900">사진 등록</h3>
                    <div className="flex h-14 items-center rounded-lg border border-dashed border-slate-300 px-4 text-xs font-extrabold text-slate-500">
                      파일을 드래그하거나 클릭하여 업로드
                      <span className="ml-3 text-slate-400">JPG, PNG, PDF, MP4 · 최대 50MB</span>
                    </div>
                  </div>
                </div>
              </Panel>

              <Panel>
                <div className="border-b border-slate-100 px-4 py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-base font-extrabold text-slate-900">처방전</h2>
                    <div className="flex gap-2">
                      <button type="button" className="h-8 rounded-md border border-slate-200 px-3 text-xs font-extrabold text-teal-700">처방전 자동 생성</button>
                      <button type="button" className="h-8 rounded-md border border-slate-200 px-3 text-xs font-extrabold text-slate-600">미리보기</button>
                    </div>
                  </div>
                </div>
                <div className="p-3">
                  <div className="mb-2 flex h-9 items-center rounded-lg border border-teal-700 bg-white px-3">
                    <input readOnly placeholder="약제명 검색 (예: 아모시실린)" className="min-w-0 flex-1 bg-transparent text-xs font-bold outline-none placeholder:text-slate-400" />
                    <Search className="h-4 w-4 text-teal-700" />
                  </div>
                  <div className="overflow-hidden rounded-md border border-slate-200 text-xs">
                    <div className="grid grid-cols-[1fr_1fr_1fr_1fr_70px_60px_50px] gap-1 border-b border-slate-200 bg-slate-50 px-2 py-2 text-[10px] font-extrabold text-slate-400">
                      <span>약제명</span><span>형태</span><span>용량</span><span>용법</span><span>기간</span><span>필수</span><span>삭제</span>
                    </div>
                    <div className="py-8 text-center text-xs font-extrabold text-slate-400">
                      검색을 통해 약을 추가해주세요.
                    </div>
                  </div>
                </div>
              </Panel>
            </div>
          </WorkspacePane>
        </div>
      </div>
    </div>
  );
}

function ReservationView() {
  const [viewMode, setViewMode] = useState<"day" | "week" | "month">("day");
  const [selectedId, setSelectedId] = useState(101);
  const reservationRows = [
    { id: 101, time: "09:00", end: "09:30", pet: "뽀삐", guardian: "김보호자", species: "강아지", doctor: "김수의", type: "준긴급" },
    { id: 102, time: "09:30", end: "10:00", pet: "나비", guardian: "이영희", species: "고양이", doctor: "김수의", type: "일반" },
    { id: 103, time: "10:00", end: "10:40", pet: "몽치", guardian: "박민준", species: "강아지", doctor: "박진료", type: "응급" },
    { id: 104, time: "11:00", end: "11:30", pet: "복실이", guardian: "최수진", species: "강아지", doctor: "박진료", type: "일반" },
    { id: 105, time: "14:00", end: "14:30", pet: "하루", guardian: "정다은", species: "고양이", doctor: "김수의", type: "완료" },
  ] as const;
  const selected = reservationRows.find((item) => item.id === selectedId) ?? reservationRows[0];
  const hours = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"];
  const topLabel = viewMode === "week" ? "06.14-06.20" : viewMode === "month" ? "2026.06" : "2026.06.18";

  return (
    <div className="flex h-[calc(100vh-108px)] flex-col overflow-hidden">
      <div className="relative mb-2 flex h-[68px] shrink-0 items-center gap-4 rounded-lg border border-slate-200 bg-white px-4 shadow-sm">
        <div className="flex shrink-0 items-center gap-3">
          <div className="grid h-10 w-[224px] shrink-0 grid-cols-[40px_1fr_40px] rounded-lg border border-slate-200 bg-white">
            <button type="button" className="flex h-10 w-10 items-center justify-center border-r border-slate-100 text-slate-600">
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button type="button" className="flex min-w-0 items-center justify-center gap-1.5 px-2 text-sm font-extrabold tabular-nums text-slate-800">
              <CalendarDays className="h-4 w-4 shrink-0 text-slate-600" />
              <span className="truncate">{topLabel}</span>
            </button>
            <button type="button" className="flex h-10 w-10 items-center justify-center border-l border-slate-100 text-slate-600">
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <button type="button" className="h-10 w-[72px] rounded-lg border border-slate-200 bg-white text-sm font-extrabold text-slate-600">
            오늘
          </button>
        </div>

        <div className="absolute left-1/2 top-1/2 flex shrink-0 -translate-x-1/2 -translate-y-1/2 items-center justify-center gap-3">
          {[
            ["day", "일간"],
            ["week", "주간"],
            ["month", "월간"],
          ].map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode as "day" | "week" | "month")}
              className={[
                "h-11 w-[80px] whitespace-nowrap rounded-lg px-5 text-sm font-extrabold transition",
                viewMode === mode ? "bg-teal-700 text-white shadow-sm" : "border border-slate-200 bg-white text-slate-600",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex shrink-0 items-center justify-end gap-3">
          <select className="h-10 w-[132px] rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-700">
            <option>전체 수의사</option>
            <option>김수의</option>
            <option>박진료</option>
          </select>
          <button type="button" className="flex h-10 w-[116px] items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-600">
            <RefreshCcw className="h-4 w-4" />
            새로고침
          </button>
          <button type="button" className="flex h-10 w-[132px] items-center justify-center gap-2 rounded-lg bg-teal-700 px-5 text-sm font-extrabold text-white shadow-sm">
            <Plus className="h-4 w-4" />
            예약 추가
          </button>
        </div>
      </div>

      {viewMode === "day" ? (
        <div className="grid min-h-0 flex-1 grid-cols-[240px_1fr_280px] gap-2">
          <aside className="space-y-3">
            <Panel>
              <div className="grid grid-cols-[36px_1fr_36px] items-center px-4 py-3">
                <button type="button" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <h2 className="text-center text-lg font-extrabold text-slate-900">2026년 06월</h2>
                <button type="button" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <div className="grid grid-cols-7 gap-1 px-4 pb-4 text-center text-xs font-extrabold">
                {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
                  <span key={day} className="py-2 text-slate-500">{day}</span>
                ))}
                {[31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 1, 2, 3, 4].map((day, index) => (
                  <button
                    key={`${day}-${index}`}
                    type="button"
                    className={[
                      "h-8 rounded-lg text-xs font-extrabold",
                      index === 18 ? "bg-teal-700 text-white" : [5, 10, 15, 20, 25, 30].includes(day) ? "bg-teal-50 text-teal-700" : index === 0 || index > 30 ? "text-slate-300" : "text-slate-700 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    {day}
                  </button>
                ))}
              </div>
            </Panel>
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex items-center justify-between gap-2">
                <h2 className="text-sm font-extrabold text-slate-900">상태 필터</h2>
              </div>
              <div className="space-y-3">
                {[
                  ["응급", 0, "bg-red-50 text-red-500 border border-red-100"],
                  ["준응급", 0, "bg-amber-50 text-amber-700 border border-amber-100"],
                  ["일반", 1, "bg-slate-50 text-slate-600 border border-slate-200"],
                ].map(([label, count, tone]) => (
                  <button key={label} type="button" className="flex w-full items-center justify-between rounded-lg p-1.5 text-left transition hover:bg-slate-50">
                    <span className={`inline-flex h-9 w-[72px] items-center justify-center rounded-md text-sm font-extrabold ${tone}`}>{label}</span>
                    <span className="flex h-8 min-w-8 items-center justify-center rounded-lg border border-slate-100 bg-white px-2 text-sm font-extrabold text-slate-800">{count}</span>
                  </button>
                ))}
              </div>
            </section>
          </aside>

          <Panel>
            <div className="relative h-full min-h-[640px] p-5">
              <div className="absolute left-1/2 top-4 z-10 -translate-x-1/2 text-center">
                <p className="text-sm font-extrabold text-slate-900">목요일</p>
                <p className="text-sm font-bold text-slate-500">6/18</p>
              </div>
              <div className="absolute right-5 top-5 flex items-center gap-4">
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-600"><i className="h-2.5 w-2.5 rounded-full bg-teal-500" />관리자</span>
                <span className="flex items-center gap-1.5 text-xs font-bold text-slate-600"><i className="h-2.5 w-2.5 rounded-full bg-orange-300" />김수의</span>
              </div>
              <div className="grid h-full grid-cols-[56px_1fr] pt-14">
                <div className="relative">
                  {hours.map((hour, index) => (
                    <div key={hour} className="absolute left-0 text-sm font-extrabold tabular-nums text-slate-600" style={{ top: index * 66 }}>
                      {hour}
                    </div>
                  ))}
                </div>
                <div className="relative overflow-hidden rounded-lg border border-slate-100 bg-white" style={{ height: 594 }}>
                  {hours.map((hour, index) => (
                    <div key={hour} className="absolute left-0 right-0 border-t border-slate-100" style={{ top: index * 66 }} />
                  ))}
                  <div className="absolute bottom-0 top-0 border-l border-slate-100" style={{ left: "50%" }} />
                  <div className="absolute inset-x-0 flex items-center bg-slate-100 px-4 text-sm font-extrabold text-slate-600" style={{ top: 198, height: 66 }}>
                    12:00 ~ 13:00 <span className="ml-5">점심시간</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedId(201)}
                    className="absolute z-10 flex h-10 items-center gap-3 rounded-lg border border-slate-200 bg-white py-1 pl-6 pr-3 text-left shadow-sm before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg before:bg-teal-500"
                    style={{ top: 363, left: 4, width: "calc(50% - 8px)" }}
                  >
                    <img src={petProfile} alt="" className="h-7 w-7 rounded-md object-cover" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-extrabold text-slate-800">14:30 ~ 15:00</span>
                      <span className="block truncate text-xs font-extrabold text-slate-900">뽀미 (테스트보호자)</span>
                    </span>
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-extrabold text-slate-600">일반</span>
                  </button>
                </div>
              </div>
            </div>
          </Panel>

          <Panel>
            <div className="border-b border-slate-100 px-5 py-3">
              <h2 className="text-base font-extrabold text-slate-900">예약 상세 정보</h2>
            </div>
            <div className="space-y-5 p-5">
              <div className="flex gap-4">
                <img src={petProfile} alt="" className="h-20 w-20 rounded-lg object-cover" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-base font-extrabold text-slate-900">뽀미</p>
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-extrabold text-slate-600">일반</span>
                    <span className="text-xl font-extrabold text-rose-500">♀</span>
                  </div>
                  <p className="mt-2 text-sm font-bold text-slate-600">말티즈 | 5세 | 3.2kg</p>
                  <p className="mt-2 text-sm font-extrabold text-slate-900">010-0000-0001</p>
                </div>
              </div>
              <button type="button" className="h-10 w-full rounded-lg border border-teal-700 bg-teal-50 text-sm font-extrabold text-teal-700">
                환자 상세정보
              </button>
              {[
                ["예약 날짜", "2026.06.18(목)"],
                ["예약 시간", "14:30"],
                ["보호자", "테스트보호자"],
                ["성별", "여자"],
                ["진료 항목", "일반진료"],
                ["담당 수의사", "관리자"],
                ["메모", ""],
              ].map(([label, value]) => (
                <div key={label} className="grid grid-cols-[96px_1fr] border-b border-slate-100 pb-3">
                  <p className="text-sm font-extrabold text-slate-500">{label}</p>
                  <p className="text-sm font-extrabold text-slate-900">{value}</p>
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3 pt-8">
                <button type="button" className="h-11 rounded-lg border border-teal-700 bg-white text-sm font-extrabold text-teal-700">수정</button>
                <button type="button" className="h-11 rounded-lg border border-red-300 bg-white text-sm font-extrabold text-red-500">삭제</button>
              </div>
            </div>
          </Panel>
        </div>
      ) : viewMode === "week" ? (
        <Panel>
          <div className="relative min-h-[650px] overflow-hidden">
            <div className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-slate-200">
              <div className="space-y-1 px-3 py-2 text-xs font-bold text-slate-600">
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-teal-500" />관리자</span>
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-orange-300" />김수의</span>
              </div>
              {[
                ["일", "06.14", "text-red-500"],
                ["월", "06.15", ""],
                ["화", "06.16", ""],
                ["수", "06.17", ""],
                ["목", "06.18", "text-teal-700"],
                ["금", "06.19", ""],
                ["토", "06.20", ""],
              ].map(([day, date, tone]) => (
                <div key={date} className="border-l border-slate-200 py-2 text-center">
                  <p className={`text-xs font-extrabold ${tone || "text-slate-500"}`}>{day}</p>
                  <p className={`text-base font-black ${tone || "text-slate-900"}`}>{date}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-[56px_repeat(7,1fr)]">
              <div className="relative h-[560px]">
                {["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"].map((hour, index) => (
                  <span key={hour} className="absolute left-3 text-sm font-extrabold text-slate-900" style={{ top: index * 48 + 8 }}>{hour}</span>
                ))}
              </div>
              {Array.from({ length: 7 }, (_, dayIndex) => (
                <div key={dayIndex} className={`relative h-[560px] border-l border-slate-100 ${dayIndex === 0 || dayIndex === 6 ? "bg-slate-200/60" : dayIndex === 4 ? "bg-slate-50" : "bg-white"}`}>
                  {Array.from({ length: 12 }, (_, i) => <div key={i} className="absolute left-0 right-0 border-t border-slate-100" style={{ top: i * 48 }} />)}
                  <div className="absolute inset-x-0 flex items-center justify-center bg-slate-100 text-sm font-extrabold text-slate-600" style={{ top: 144, height: 48 }}>
                    {dayIndex === 3 ? "점심시간" : ""}
                  </div>
                  {dayIndex === 2 ? (
                    <div className="absolute left-1 right-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-extrabold shadow-sm before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1 before:rounded-l-lg before:bg-teal-500" style={{ top: 384 }}>
                      17:00-17:30<br />뽀미
                    </div>
                  ) : null}
                  {dayIndex === 4 ? (
                    <div className="absolute left-1 right-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-extrabold shadow-sm before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1 before:rounded-l-lg before:bg-teal-500" style={{ top: 264 }}>
                      14:30-15:00<br />뽀미
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </Panel>
      ) : (
        <section className="min-h-0 flex-1 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="grid grid-cols-7 border-b border-slate-200 text-center text-sm font-extrabold text-slate-700">
            {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
              <div key={day} className="border-r border-slate-100 py-4 last:border-r-0">{day}</div>
            ))}
          </div>
          <div className="grid h-[calc(100%-53px)] grid-cols-7 grid-rows-5">
            {[31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, "", "", "", ""].map((day, index) => {
              const currentMonth = typeof day === "number" && index > 0 && index < 31;
              const isEmpty = day === "";
              const counts: Record<number, number> = { 3: 4, 6: 3, 9: 2, 12: 1, 15: 4, 18: 1, 21: 2, 24: 1, 27: 4, 30: 3 };
              const isToday = currentMonth && day === 18;
              const isHoliday = currentMonth && (day === 3 || day === 6);
              return (
                <button
                  key={`${day}-${index}`}
                  type="button"
                  className={[
                    "border-b border-r border-slate-100 p-4 text-left last:border-r-0 hover:bg-slate-50",
                    isEmpty ? "cursor-default bg-white hover:bg-white" : !currentMonth ? "bg-slate-50 text-slate-300" : isToday ? "ring-1 ring-inset ring-teal-700" : "bg-white",
                  ].join(" ")}
                >
                  {isEmpty ? null : (
                    <>
                      <div className="flex items-start justify-between">
                        <span className={`text-base font-black ${!currentMonth ? "text-slate-300" : isHoliday || index % 7 === 0 ? "text-red-500" : index % 7 === 6 ? "text-teal-700" : "text-slate-900"}`}>{day}</span>
                        {isToday ? <span className="rounded-full bg-teal-700 px-2 py-1 text-xs font-extrabold text-white">오늘</span> : null}
                      </div>
                      {isHoliday ? <span className="ml-3 text-xs font-extrabold text-red-500">{day === 3 ? "전국동시지방선거" : "현충일"}</span> : null}
                      <p className={`mt-6 inline-flex rounded-lg px-3 py-2 text-sm font-extrabold ${currentMonth ? "bg-slate-50 text-slate-900" : "bg-white text-slate-300"}`}>
                        총 {currentMonth ? counts[day] ?? 0 : 0}건
                      </p>
                    </>
                  )}
                </button>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

function PatientsView() {
  const [selectedPatient, setSelectedPatient] = useState<string | null>(null);
  const patients = [
    { petName: "뽀삐", age: "3살", guardianName: "김보호자", phone: "010-2222-2222", breed: "말티즈", lastVisitDate: "2026-06-17", memo: "구토/설사" },
    { petName: "나비", age: "5살", guardianName: "이영희", phone: "010-3333-3333", breed: "코리안쇼트헤어", lastVisitDate: "2026-06-17", memo: "정기검진" },
    { petName: "몽이", age: "2살", guardianName: "박민준", phone: "010-4444-4444", breed: "포메라니안", lastVisitDate: "2026-06-13", memo: "피부 발진" },
    { petName: "하루", age: "4살", guardianName: "정다은", phone: "010-5555-5555", breed: "랙돌", lastVisitDate: "2026-06-11", memo: "예방접종" },
  ];
  const selected = patients.find((patient) => patient.petName === selectedPatient);

  if (selected) {
    return (
      <div className="space-y-4">
        <button type="button" onClick={() => setSelectedPatient(null)} className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-600">
          목록으로
        </button>
        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <Panel>
            <div className="p-5">
              <div className="flex h-24 w-24 items-center justify-center rounded-lg bg-blue-50 text-3xl font-black text-blue-600">
                {selected.petName[0]}
              </div>
              <h1 className="mt-4 text-2xl font-extrabold text-slate-900">{selected.petName}</h1>
              <p className="mt-2 text-sm font-bold text-slate-500">{selected.breed} · {selected.age}</p>
              <div className="mt-5 space-y-3">
                {[
                  ["보호자", selected.guardianName],
                  ["전화번호", selected.phone],
                  ["최근 내원일", selected.lastVisitDate],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-slate-50 px-4 py-3">
                    <p className="text-xs font-bold text-slate-400">{label}</p>
                    <p className="mt-1 text-sm font-extrabold text-slate-800">{value}</p>
                  </div>
                ))}
              </div>
            </div>
          </Panel>
          <Panel>
            <div className="border-b border-slate-100 px-5 py-4">
              <h2 className="text-lg font-extrabold text-slate-900">EMR 진료 기록</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {["2026-06-17 일반진료 - 위장관염 의심", "2026-06-10 정기검진 - 특이사항 없음", "2026-05-21 피부 상담 - 샴푸 변경 권고"].map((history) => (
                <article key={history} className="px-5 py-4">
                  <p className="text-sm font-extrabold text-slate-800">{history}</p>
                  <p className="mt-1 text-xs font-bold text-slate-400">진료 기록은 조회 전용 데모 데이터입니다.</p>
                </article>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col">
      <div className="mb-6 flex min-w-0 flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
        <h1 className="text-2xl font-extrabold text-slate-900">환자 관리</h1>
          <p className="mt-1 text-sm font-bold text-slate-500">병원 전체 환자 리스트를 확인하고 관리할 수 있습니다.</p>
      </div>
        <label className="relative w-full max-w-[420px]">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500" />
          <input readOnly placeholder="강아지 이름 또는 보호자 이름 검색" className="h-12 w-full rounded-lg border border-slate-200 bg-white pl-12 pr-4 text-sm font-bold text-slate-800 outline-none placeholder:text-slate-400" />
        </label>
      </div>
      <section className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm h-[calc(100vh-184px)]">
        <div className="flex h-[64px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 xl:px-6">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-extrabold text-slate-900">전체 환자</h2>
            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-sm font-extrabold text-blue-600">{patients.length}</span>
          </div>
          <select className="h-11 min-w-[128px] rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-600 outline-none">
            <option>전체</option>
            <option>강아지</option>
            <option>고양이</option>
          </select>
        </div>
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
          <table className="w-full table-fixed border-collapse text-left">
            <thead className="bg-slate-50">
              <tr className="border-b border-slate-200 text-xs font-extrabold uppercase tracking-wide text-slate-400">
                {["이름", "나이", "보호자", "전화번호", "품종", "최근 내원일", "메모", ""].map((label) => (
                  <th key={label} className="px-4 py-3.5">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {patients.map((patient) => (
                <tr key={patient.petName} onClick={() => setSelectedPatient(patient.petName)} className="group h-[56px] cursor-pointer border-b border-slate-100 text-sm text-slate-700 last:border-b-0 hover:bg-slate-50">
                  <td className="truncate px-4 py-3 font-extrabold text-slate-800">{patient.petName}</td>
                  <td className="px-4 py-3 text-slate-600">{patient.age}</td>
                  <td className="truncate px-4 py-3 font-semibold">{patient.guardianName}</td>
                  <td className="truncate px-4 py-3 tabular-nums text-slate-600">{patient.phone}</td>
                  <td className="px-4 py-3"><span className="inline-flex max-w-full rounded-md bg-slate-50 px-2 py-0.5 text-xs font-extrabold text-slate-600">{patient.breed}</span></td>
                  <td className="px-4 py-3 tabular-nums text-slate-600">{patient.lastVisitDate}</td>
                  <td className="truncate px-4 py-3 text-slate-400">{patient.memo}</td>
                  <td className="px-4 py-3">
                    <button type="button" className="h-9 w-[78px] rounded-lg border border-blue-100 bg-white text-sm font-extrabold text-blue-600 hover:bg-blue-50">
                      상세보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex h-[56px] shrink-0 items-center justify-center gap-2 border-t border-slate-100 px-6">
          <button type="button" className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600"><ChevronLeft className="h-4 w-4" /></button>
          {[1, 2, 3].map((page) => (
            <button key={page} type="button" className={`h-9 w-9 rounded-lg text-sm font-extrabold ${page === 1 ? "bg-blue-50 text-blue-600" : "text-slate-600 hover:bg-slate-50"}`}>{page}</button>
          ))}
          <button type="button" className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600"><ChevronRight className="h-4 w-4" /></button>
        </div>
      </section>
    </div>
  );
}

function HospitalManageView() {
  const [hospitalInfo, setHospitalInfo] = useState({
    name: "MediPaw 동물병원",
    phone: "02-0000-0001",
    tagline: "보호자와 의료진이 함께 확인하는 반려동물 주치의 병원",
    address: "서울시 강남구 테스트로 1",
    description: "AI 문진으로 내원 전 증상을 정리하고, 담당 원장이 예약 전후 기록을 이어서 확인합니다.",
  });
  const [tagDraft, setTagDraft] = useState("");
  const [hospitalTags, setHospitalTags] = useState(["AI 문진 연동", "예약 가능", "주치의 관리"]);
  const [directorCards, setDirectorCards] = useState([
    { name: "관리자", license: "3-4070", specialty: "", education: "", intro: "" },
    { name: "김수의", license: "3-9999", specialty: "", education: "", intro: "" },
  ]);

  const weekdays = [
    ["월", "09:00", "18:00", true],
    ["화", "09:00", "21:00", true],
    ["수", "09:00", "18:00", true],
    ["목", "09:00", "18:00", true],
    ["금", "09:00", "18:00", true],
    ["토", "휴진", "-", false],
    ["일", "휴진", "-", false],
  ] as const;

  const updateHospitalInfo = (field: keyof typeof hospitalInfo, value: string) => {
    setHospitalInfo((current) => ({ ...current, [field]: value }));
  };

  const addHospitalTag = () => {
    const nextTag = tagDraft.trim();
    if (!nextTag || hospitalTags.includes(nextTag) || hospitalTags.length >= 8) return;
    setHospitalTags((current) => [...current, nextTag]);
    setTagDraft("");
  };

  const removeHospitalTag = (tag: string) => {
    setHospitalTags((current) => current.filter((item) => item !== tag));
  };

  const updateDirector = (index: number, field: keyof (typeof directorCards)[number], value: string) => {
    setDirectorCards((current) =>
      current.map((director, directorIndex) =>
        directorIndex === index ? { ...director, [field]: value } : director,
      ),
    );
  };

  return (
    <div className="pb-8">
      <div className="mb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900">병원 관리</h1>
          <p className="mt-1 text-sm font-bold text-slate-500">보호자 화면에 표시되는 병원 정보와 운영 일정을 관리합니다.</p>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(620px,1fr)_minmax(520px,1fr)]">
        <div className="space-y-5">
          <DemoSection title="병원 정보">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">병원명</span>
                <input value={hospitalInfo.name} onChange={(event) => updateHospitalInfo("name", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800 outline-none" />
              </label>
              <label className="block">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">전화</span>
                <input value={hospitalInfo.phone} onChange={(event) => updateHospitalInfo("phone", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800 outline-none" />
              </label>
              <label className="block sm:col-span-2">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">한 줄 소개 (태그라인)</span>
                <input value={hospitalInfo.tagline} onChange={(event) => updateHospitalInfo("tagline", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800 outline-none" />
              </label>
              <label className="block sm:col-span-2">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">주소</span>
                <input value={hospitalInfo.address} onChange={(event) => updateHospitalInfo("address", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800 outline-none" />
              </label>
              <label className="block sm:col-span-2">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">소개 본문</span>
                <textarea value={hospitalInfo.description} onChange={(event) => updateHospitalInfo("description", event.target.value)} className="h-32 w-full resize-none rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-800 outline-none" />
              </label>
              <div className="sm:col-span-2">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">특징 태그</span>
                <div className="grid grid-cols-[1fr_52px] gap-2">
                  <input value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addHospitalTag();
                    }
                  }} placeholder="내과 진료, 노령동물 건강관리 ..." className="h-11 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold outline-none placeholder:text-slate-400" />
                  <button type="button" onClick={addHospitalTag} className="flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600">
                    <Plus className="h-5 w-5" />
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {hospitalTags.map((tag) => (
                    <button key={tag} type="button" onClick={() => removeHospitalTag(tag)} className="inline-flex h-7 items-center rounded-full bg-teal-50 px-3 text-xs font-extrabold text-teal-700">
                      {tag} <span className="ml-1 text-teal-500">×</span>
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-xs font-bold text-slate-400">태그 (최대 8개)</p>
              </div>
              <div className="sm:col-span-2">
                <span className="mb-2 block text-xs font-extrabold text-slate-500">배너 이미지 (드래그로 초점 조정)</span>
                <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-sm font-extrabold text-slate-400">
                  이미지 없음
                </div>
              </div>
            </div>
            <button type="button" className="mt-5 h-11 rounded-lg bg-teal-700 px-6 text-sm font-extrabold text-white">저장</button>
          </DemoSection>

          <DemoSection title="진료시간">
            <div className="rounded-lg bg-slate-50 p-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-xs font-extrabold text-slate-500">일괄 적용</span>
                <select className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                  <option>09:00</option>
                </select>
                <span className="text-slate-400">~</span>
                <select className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                  <option>18:00</option>
                </select>
                <span className="h-5 border-l border-slate-200" />
                <span className="text-xs font-extrabold text-slate-500">점심</span>
                <select className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                  <option>12:00</option>
                </select>
                <span className="text-slate-400">~</span>
                <select className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                  <option>13:00</option>
                </select>
                <button type="button" className="h-10 rounded-lg bg-teal-700 px-4 text-sm font-extrabold text-white">적용</button>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-[42px_1.2fr_1fr_72px] gap-x-4 border-b border-slate-100 pb-3 text-xs font-extrabold text-slate-500">
              <span>요일</span>
              <span>운영 시간</span>
              <span>점심 시간</span>
              <span className="text-right">운영</span>
            </div>
            <div className="divide-y divide-slate-100">
              {weekdays.map(([day, start, end, active]) => (
                <div key={day} className="grid grid-cols-[42px_1.2fr_1fr_72px] items-center gap-x-4 py-3">
                  <span className="text-sm font-extrabold text-slate-700">{day}</span>
                  {active ? (
                    <div className="flex items-center gap-2">
                      <select className="h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                        <option>{start}</option>
                      </select>
                      <span className="text-slate-400">~</span>
                      <select className="h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                        <option>{end}</option>
                      </select>
                    </div>
                  ) : (
                    <span className="text-sm font-bold text-slate-300">휴진</span>
                  )}
                  {active ? (
                    <div className="flex items-center gap-2">
                      <select className="h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                        <option>12:00</option>
                      </select>
                      <span className="text-slate-400">~</span>
                      <select className="h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                        <option>13:00</option>
                      </select>
                    </div>
                  ) : (
                    <span className="text-sm font-bold text-slate-300">-</span>
                  )}
                  <span className={["ml-auto block h-8 w-12 rounded-full p-0.5", active ? "bg-teal-700" : "bg-slate-200"].join(" ")}>
                    <span className={["block h-7 w-7 rounded-full bg-white shadow-sm", active ? "ml-4" : "ml-0"].join(" ")} />
                  </span>
                </div>
              ))}
            </div>
            <button type="button" className="mt-4 h-11 rounded-lg bg-teal-700 px-6 text-sm font-extrabold text-white">저장</button>
          </DemoSection>

          <DemoSection title="의사별 근무시간">
            <label className="block">
              <span className="mb-2 block text-xs font-extrabold text-slate-500">수의사 선택</span>
              <select className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-800">
                <option>관리자</option>
                <option>김수의</option>
              </select>
            </label>
            <div className="mt-4 grid grid-cols-7 gap-1.5">
              {["월", "화", "수", "목", "금", "토", "일"].map((day, index) => (
                <button key={day} type="button" className={["h-11 rounded-lg text-sm font-extrabold", index === 0 ? "bg-teal-700 text-white" : "bg-slate-100 text-slate-500"].join(" ")}>
                  {day}
                </button>
              ))}
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {[
                ["출근 시간", "09:00"],
                ["퇴근 시간", "18:00"],
                ["점심 시작", "12:00"],
                ["점심 종료", "13:00"],
              ].map(([label, value]) => (
                <label key={label} className="block">
                  <span className="mb-2 block text-xs font-extrabold text-slate-400">{label}</span>
                  <select className="h-10 w-28 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-800">
                    <option>{value}</option>
                  </select>
                </label>
              ))}
            </div>
            <div className="mt-4 space-y-3">
              {["이 요일은 휴무입니다.", "점심 시간이 없습니다."].map((label) => (
                <label key={label} className="flex items-center gap-2 text-sm font-extrabold text-slate-700">
                  <span className="h-5 w-5 rounded border border-slate-300 bg-white" />
                  {label}
                </label>
              ))}
            </div>
            <button type="button" className="mt-4 h-11 rounded-lg bg-teal-700 px-6 text-sm font-extrabold text-white">저장</button>
          </DemoSection>

          <DemoSection title="특정일 휴진">
            <span className="mb-2 block text-xs font-extrabold text-slate-500">날짜 추가</span>
            <div className="grid grid-cols-[1fr_84px] gap-2">
              <div className="flex h-11 items-center justify-between rounded-lg border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-400">
                연도. 월. 일.
                <CalendarDays className="h-4 w-4 text-slate-500" />
              </div>
              <button type="button" className="flex h-11 items-center justify-center gap-1 rounded-lg bg-teal-700/30 text-sm font-extrabold text-white">
                <Plus className="h-4 w-4" />
                추가
              </button>
            </div>
            <p className="mt-4 text-xs font-extrabold text-slate-500">등록된 휴진일 (1)</p>
            <div className="mt-2 flex h-12 items-center justify-between rounded-lg bg-slate-50 px-4">
              <span className="text-sm font-extrabold tabular-nums text-slate-800">2026-06-30</span>
              <span className="text-lg font-extrabold text-slate-400">♲</span>
            </div>
          </DemoSection>

          <DemoSection title="원장">
            <div className="space-y-4">
              {directorCards.map((director, index) => (
                <div key={`${director.name}-${index}`} className="rounded-lg border border-slate-200 p-4">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="flex gap-3 text-slate-300">
                      <span className="text-lg">↑</span>
                      <span className="text-lg">↓</span>
                    </div>
                    <button type="button" className="text-xs font-extrabold text-slate-400">삭제</button>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label>
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">이름</span>
                      <input value={director.name} onChange={(event) => updateDirector(index, "name", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800" />
                    </label>
                    <label>
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">면허번호</span>
                      <input value={director.license} onChange={(event) => updateDirector(index, "license", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800" />
                    </label>
                    <label>
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">전문 진료</span>
                      <input value={director.specialty} onChange={(event) => updateDirector(index, "specialty", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800" />
                    </label>
                    <label>
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">학력</span>
                      <input value={director.education} onChange={(event) => updateDirector(index, "education", event.target.value)} className="h-11 w-full rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-800" />
                    </label>
                    <label className="sm:col-span-2">
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">소개글</span>
                      <textarea value={director.intro} onChange={(event) => updateDirector(index, "intro", event.target.value)} className="h-28 w-full resize-none rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-800" />
                    </label>
                    <div className="sm:col-span-2">
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">전문 분야</span>
                      <div className="grid grid-cols-[1fr_52px] gap-2">
                        <input readOnly placeholder="내과 진료, 노령동물 건강관리 ..." className="h-11 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold outline-none placeholder:text-slate-400" />
                        <button type="button" className="flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600">
                          <Plus className="h-5 w-5" />
                        </button>
                      </div>
                      <p className="mt-1 text-xs font-bold text-slate-400">태그 (최대 8개)</p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="mb-2 block text-xs font-extrabold text-slate-500">원장 사진 (드래그로 초점 조정)</span>
                      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-sm font-extrabold text-slate-400">
                        이미지 없음
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </DemoSection>
        </div>

        <aside className="xl:sticky xl:top-6 xl:self-start">
          <p className="mb-2 text-xs font-extrabold text-slate-400">보호자 화면 미리보기</p>
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-sm">
            <div className="p-7">
              <h2 className="text-xl font-extrabold text-slate-950">{hospitalInfo.name || "병원명"}</h2>
              <p className="mt-4 text-sm font-extrabold text-teal-700">{hospitalInfo.tagline || "한 줄 소개가 표시됩니다."}</p>
              <p className="mt-7 whitespace-pre-wrap text-sm font-bold leading-7 text-slate-600">{hospitalInfo.description || "소개 본문이 표시됩니다."}</p>
              <div className="mt-7 flex gap-2">
                {hospitalTags.map((tag) => (
                  <span key={tag} className="rounded-full bg-teal-50 px-3 py-1.5 text-xs font-extrabold text-teal-700">{tag}</span>
                ))}
              </div>
            </div>
            <div className="border-t border-slate-100 p-7">
              <div className="mb-5 flex items-center justify-between">
                <h3 className="text-lg font-extrabold text-slate-900">원장 소개</h3>
                <span className="text-sm font-extrabold text-slate-400">2명</span>
              </div>
              <div className="grid gap-5 sm:grid-cols-2">
                {directorCards.map(({ name, intro }) => (
                  <article key={name} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex h-56 items-center justify-center bg-teal-50/60 text-5xl font-black text-teal-700">
                      {name.trim().slice(0, 1) || "?"}
                    </div>
                    <div className="p-5">
                      <p className="text-base font-extrabold text-slate-900">{name || "원장명"}</p>
                      <p className={["mt-4 whitespace-pre-wrap text-sm font-extrabold", intro ? "text-slate-500" : "text-slate-300"].join(" ")}>
                        {intro || "소개글이 없습니다."}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function DemoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-5 text-lg font-extrabold text-slate-900">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function SettingsView() {
  return (
    <div className="flex h-full flex-col">
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold text-slate-900">설정</h1>
        <p className="mt-1 text-sm font-bold text-slate-500">계정 보안을 관리합니다.</p>
      </div>
      <div className="max-w-2xl space-y-4">
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-4">
            <h2 className="text-base font-extrabold text-slate-900">계정 및 보안</h2>
            <p className="mt-0.5 text-xs font-semibold text-slate-400">계정 정보 및 보안을 관리합니다.</p>
          </div>
          <div className="flex items-center gap-4 px-5 py-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50">
              <LockKeyhole className="h-5 w-5 text-blue-600" strokeWidth={2.2} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-slate-800">관리자 비밀번호 변경</p>
              <p className="mt-0.5 text-xs font-semibold text-slate-400">비밀번호를 변경해주세요.</p>
            </div>
            <button type="button" className="h-9 shrink-0 whitespace-nowrap rounded-lg border border-blue-200 bg-white px-4 text-sm font-extrabold text-blue-600 hover:bg-blue-50">
              비밀번호 변경
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

function DemoFloatingBar() {
  return (
    <div className="fixed bottom-5 left-1/2 z-[90] flex -translate-x-1/2 items-center gap-3 rounded-full border border-teal-100 bg-white/95 px-4 py-2 shadow-lg shadow-slate-900/10 backdrop-blur">
      <span className="whitespace-nowrap rounded-full bg-teal-50 px-3 py-1 text-xs font-extrabold text-teal-700">
        데모 페이지
      </span>
      <a
        href="/"
        className="whitespace-nowrap rounded-full bg-slate-900 px-4 py-2 text-xs font-extrabold text-white transition hover:bg-slate-700"
      >
        서비스 소개로 돌아가기
      </a>
    </div>
  );
}

export default function VetDemoPage() {
  const [activeMenu, setActiveMenu] = useState<VetMenu>("home");
  const content = useMemo(() => {
    switch (activeMenu) {
      case "emr":
        return <EmrView />;
      case "reservation":
        return <ReservationView />;
      case "patients":
        return <PatientsView />;
      case "hospital-manage":
        return <HospitalManageView />;
      case "settings":
        return <SettingsView />;
      default:
        return <HomeView />;
    }
  }, [activeMenu]);

  return (
    <VetLayout activeMenu={activeMenu} onNavigate={setActiveMenu}>
      {content}
      <DemoFloatingBar />
    </VetLayout>
  );
}
