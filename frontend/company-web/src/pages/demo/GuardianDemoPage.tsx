import { useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  ChevronDown,
  Globe2,
  Send,
  X,
} from "lucide-react";
import petProfile from "../../assets/demo/profile-mangmang.png";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

type GuardianView = "home" | "hospitals" | "chatbot" | "reservations" | "mypage";
type Role = "assistant" | "user";
type MsgType = "text" | "slots" | "confirm" | "instructions";

interface ScriptItem {
  role: Role;
  type?: MsgType;
  text: string;
  options?: string[];
}

interface ChatMessage {
  id: number;
  role: Role;
  type?: MsgType;
  text: string;
}

interface DemoReservation {
  id: number;
  pet: string;
  date: string;
  hospital: string;
  doctor: string;
  type: string;
  memo: string;
  status: string;
  tone: string;
}

const navItems: Array<{ id: GuardianView; label: string }> = [
  { id: "home", label: "홈" },
  { id: "hospitals", label: "병원" },
  { id: "chatbot", label: "챗봇 상담" },
  { id: "reservations", label: "예약 내역" },
  { id: "mypage", label: "마이페이지" },
];

const pet = {
  name: "망망",
  species: "강아지",
  gender: "여아",
  image: petProfile,
};

const pets = [
  { id: 1, name: "망망", color: "bg-teal-50 text-teal-700" },
  { id: 2, name: "나비", color: "bg-amber-50 text-amber-700" },
  { id: 3, name: "몽이", color: "bg-blue-50 text-blue-600" },
];

const histories = [
  { id: 1, title: "구토, 설사", date: "2026-06-17", active: true },
  { id: 2, title: "피부 발진", date: "2026-06-11", active: false },
  { id: 3, title: "정기검진 문의", date: "2026-06-02", active: false },
];

const script: ScriptItem[] = [
  {
    role: "assistant",
    text: "안녕하세요.\n반려동물의 증상을 알려주시면 예약을 도와드릴게요.",
    options: ["구토", "설사", "피부", "기침", "식욕저하", "눈물"],
  },
  { role: "user", text: "구토" },
  {
    role: "assistant",
    text: "언제부터 구토가 있었나요?",
    options: ["오늘부터", "2~3일 전", "1주일 이상"],
  },
  { role: "user", text: "2~3일 전부터요" },
  {
    role: "assistant",
    text: "식욕이나 활력에도 변화가 있나요?",
    options: ["식욕이 없어요", "기운이 없어요", "별 차이 없어요"],
  },
  { role: "user", text: "식욕이 없어요" },
  {
    role: "assistant",
    type: "slots",
    text: "문진 내용을 정리했습니다. 준긴급 단계로 보고 오늘 중 진료를 권장드려요.",
  },
  { role: "user", text: "6월 18일 (목) 오전 10:00" },
  { role: "assistant", type: "confirm", text: "예약이 확정되었습니다." },
  { role: "assistant", type: "instructions", text: "내원 전 준비사항을 확인해주세요." },
];

const slots = [
  { label: "6월 18일 (목) 오전 10:00", date: "6월 18일 (목)", time: "오전 10:00", doctor: "김수의 원장", duration: "30분" },
  { label: "6월 18일 (목) 오후 2:00", date: "6월 18일 (목)", time: "오후 2:00", doctor: "김수의 원장", duration: "30분" },
  { label: "6월 19일 (금) 오전 9:30", date: "6월 19일 (금)", time: "오전 9:30", doctor: "박진료 원장", duration: "30분" },
];

function GuardianNavbar({
  activeView,
  onSelect,
}: {
  activeView: GuardianView;
  onSelect: (view: GuardianView) => void;
}) {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-100 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6">
        <button type="button" onClick={() => onSelect("home")} className="flex items-center">
          <img src={medipawSymbol} alt="MediPaw" className="h-9 w-auto" />
        </button>

        <nav className="hidden h-full items-center gap-8 lg:flex">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              className={[
                "flex h-full items-center border-b-2 px-1 text-sm font-bold transition",
                activeView === item.id
                  ? "border-teal-700 text-teal-700"
                  : "border-transparent text-slate-600 hover:text-teal-700",
              ].join(" ")}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-50 hover:text-blue-600"
            aria-label="언어 선택"
          >
            <Globe2 className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-full px-2 py-1 transition hover:bg-slate-50"
          >
            <span className="max-w-28 truncate text-sm font-bold text-slate-600">
              김보호자 님
            </span>
            <ChevronDown className="h-4 w-4 text-slate-400" />
          </button>
        </div>
      </div>

      <nav className="flex border-t border-slate-100 bg-white lg:hidden">
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            className={[
              "flex-1 px-2 py-3 text-xs font-bold",
              activeView === item.id ? "bg-teal-50 text-teal-700" : "text-slate-600",
            ].join(" ")}
          >
            {item.label}
          </button>
        ))}
      </nav>
    </header>
  );
}

function PageShell({
  title,
  description,
  rightAction,
  children,
}: {
  title: string;
  description: string;
  rightAction?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-[1200px] px-6 pb-8 pt-10">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        </div>
        {rightAction}
      </div>
      {children}
    </main>
  );
}

function HomeView({
  onSelect,
  onReserve,
}: {
  onSelect: (view: GuardianView) => void;
  onReserve: () => void;
}) {
  return (
    <PageShell
      title="내 반려동물"
      description="사랑하는 반려동물의 건강을 관리하고 예약해보세요."
      rightAction={
        <button
          type="button"
          className="inline-flex h-12 items-center justify-center rounded-xl bg-teal-700 px-5 text-sm font-extrabold text-white transition hover:bg-teal-800"
        >
          + 반려동물 등록
        </button>
      }
    >
      <section className="min-h-[620px] rounded-2xl border border-slate-100 bg-white p-8 shadow-sm">
        <p className="text-sm font-extrabold text-slate-500">등록된 반려동물 1마리</p>

        <article className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="mx-auto flex h-28 w-28 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white sm:mx-0">
              <img
                src={pet.image}
                alt={`${pet.name} 사진`}
                className="h-full w-full object-cover"
              />
            </div>

            <div className="min-w-0 flex-1">
              <h2 className="text-base font-black text-slate-950">{pet.name}</h2>
              <p className="mt-2 text-sm font-extrabold text-slate-500">
                {pet.species} · {pet.gender}
              </p>

              <div className="mt-5 border-t border-slate-200 pt-4">
                <div className="grid max-w-[760px] gap-2 md:grid-cols-3">
                  <button
                    type="button"
                    className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                  >
                    프로필 관리
                  </button>
                  <button
                    type="button"
                    onClick={onReserve}
                    className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                  >
                    예약하기
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelect("chatbot")}
                    className="inline-flex h-11 items-center justify-center rounded-lg bg-teal-700 px-3 text-sm font-extrabold text-white transition hover:bg-teal-800"
                  >
                    챗봇 상담
                  </button>
                </div>
              </div>
            </div>
          </div>
        </article>
      </section>
    </PageShell>
  );
}

function HospitalsView() {
  const doctors = [
    {
      name: "김수의 원장",
      initial: "김",
      description: "내과 진료와 건강검진을 담당합니다.",
      tags: ["내과", "건강검진"],
    },
    {
      name: "박진료 원장",
      initial: "박",
      description: "피부 질환과 예방접종 상담을 담당합니다.",
      tags: ["피부", "예방접종"],
    },
  ];

  return (
    <PageShell
      title="병원"
      description="다니는 동물병원을 선택하고 원장님을 확인하세요."
      rightAction={
        <button
          type="button"
          className="inline-flex h-12 min-w-[180px] items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-700 shadow-sm transition hover:border-slate-300"
        >
          MediPaw 동물병원
          <ChevronDown className="h-4 w-4 text-slate-400" />
        </button>
      }
    >
      <div className="space-y-8">
        <section className="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm">
          <div className="p-8">
            <h2 className="text-2xl font-black text-slate-950">MediPaw 동물병원</h2>
            <p className="mt-5 text-sm font-extrabold text-teal-700">
              보호자와 의료진이 함께 확인하는 반려동물 주치의 병원
            </p>
            <p className="mt-8 max-w-2xl text-sm font-semibold leading-6 text-slate-500">
              AI 문진으로 내원 전 증상을 정리하고, 담당 원장이 예약 전후 기록을 이어서 확인합니다.
              예방접종부터 만성질환 관리까지 한 곳에서 차분하게 돌볼 수 있어요.
            </p>

            <div className="mt-8 flex flex-wrap gap-2">
              {["AI 문진 연동", "예약 가능", "주치의 관리"].map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-teal-50 px-4 py-1.5 text-sm font-extrabold text-teal-700"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <div className="border-t border-slate-100 px-8 pb-8 pt-6">
            <div className="grid gap-3 md:grid-cols-3">
              <InfoBox
                title="진료시간"
                lines={["평일 09:00 ~ 18:00", "토요일 휴진", "일요일 휴진"]}
              />
              <InfoBox title="오시는 길" lines={["서울시 강남구 테스트로 1"]} />
              <InfoBox title="연락처" lines={["02-0000-0001"]} />
            </div>
          </div>
        </section>

        <section>
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-black text-slate-900">원장 소개</h2>
            <p className="text-sm font-extrabold text-slate-400">원장 2명</p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {doctors.map((doctor) => (
              <article
                key={doctor.name}
                className="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm"
              >
                <div className="relative flex h-56 items-end justify-center overflow-hidden bg-teal-50">
                  <span className="translate-y-8 text-[96px] font-black leading-none text-teal-700">
                    {doctor.initial}
                  </span>
                </div>
                <div className="p-5">
                  <h3 className="text-lg font-black text-slate-950">{doctor.name}</h3>
                  <p className="mt-2 text-sm font-semibold text-slate-500">{doctor.description}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {doctor.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-slate-100 px-3 py-1 text-xs font-extrabold text-slate-600"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </PageShell>
  );
}

function InfoBox({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="min-h-32 rounded-xl border border-slate-100 bg-slate-50 px-4 py-4">
      <p className="text-sm font-extrabold text-slate-400">{title}</p>
      <div className="mt-2 space-y-1">
        {lines.map((line) => (
          <p key={line} className="text-sm font-extrabold leading-6 text-slate-700">
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}

function AssistantBubble({ text }: { text: string }) {
  return (
    <div className="max-w-[82%] whitespace-pre-line rounded-3xl rounded-bl-lg bg-slate-100 px-5 py-4 text-sm font-semibold leading-6 text-slate-700">
      {text}
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="max-w-[82%] self-end whitespace-pre-line rounded-3xl rounded-br-lg bg-blue-600 px-5 py-4 text-sm font-semibold leading-6 text-white">
      {text}
    </div>
  );
}

function SlotsCard({ onSelect }: { onSelect: (label: string) => void }) {
  return (
    <div className="w-full overflow-hidden rounded-3xl rounded-bl-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap gap-2 px-5 pt-4">
        {["추천시간", "가장 가까운 시간"].map((label, index) => (
          <button
            key={label}
            type="button"
            className={[
              "rounded-full px-3 py-1.5 text-xs font-bold",
              index === 0 ? "bg-blue-600 text-white" : "border border-slate-200 text-slate-600",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>
      <ul className="divide-y divide-slate-100">
        {slots.map((slot) => (
          <li key={slot.label} className="flex items-center justify-between gap-3 px-5 py-4">
            <div className="min-w-0">
              <p className="text-sm font-extrabold text-slate-900">{slot.date}</p>
              <p className="mt-0.5 text-xs font-semibold text-slate-500">
                {slot.time}
                <span className="mx-1.5 text-slate-300">|</span>
                <span className="text-blue-600">{slot.duration} 예상</span>
                <span className="mx-1.5 text-slate-300">|</span>
                {slot.doctor}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onSelect(slot.label)}
              className="shrink-0 rounded-xl bg-blue-600 px-4 py-2 text-xs font-extrabold text-white transition hover:bg-blue-700"
            >
              선택
            </button>
          </li>
        ))}
      </ul>
      <div className="p-3">
        <button
          type="button"
          className="flex w-full items-center justify-center rounded-2xl border border-blue-200 bg-blue-50/60 px-4 py-3 text-xs font-extrabold text-blue-600"
        >
          가능한 날짜 직접 보기
        </button>
      </div>
    </div>
  );
}

function ConfirmationCard() {
  return (
    <div className="w-full rounded-3xl rounded-bl-lg border border-emerald-100 bg-white px-5 py-4 shadow-sm">
      <p className="text-sm font-extrabold text-emerald-600">예약 확정</p>
      <dl className="mt-3 space-y-2 text-sm font-semibold text-slate-700">
        <div>뽀삐</div>
        <div>6월 18일 (목) 오전 10:00</div>
        <div>예상 진료 시간 30분</div>
        <div>해피펫 동물병원</div>
      </dl>
      <p className="mt-3 border-t border-slate-100 pt-3 text-xs font-medium text-slate-400">
        예약 변경/취소는 예약 내역에서 가능합니다.
      </p>
    </div>
  );
}

function InstructionsCard() {
  return (
    <div className="w-full rounded-3xl rounded-bl-lg border border-slate-200 bg-slate-50 px-5 py-4 shadow-sm">
      <p className="text-sm font-extrabold text-slate-800">내원 전 준비사항</p>
      <ul className="mt-2.5 space-y-1.5">
        {["구토 횟수와 마지막 식사 시간을 기억해주세요.", "복용 중인 약이나 최근 사료 변경 이력을 알려주세요."].map((item) => (
          <li key={item} className="flex gap-2 text-sm font-semibold leading-6 text-slate-600">
            <span className="text-blue-500">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChatbotView() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [scriptIndex, setScriptIndex] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const nextId = useRef(0);

  const pushMessage = (item: ScriptItem) => {
    setMessages((prev) => [
      ...prev,
      { id: ++nextId.current, role: item.role, type: item.type, text: item.text },
    ]);
  };

  useEffect(() => {
    setIsTyping(true);
    const timer = window.setTimeout(() => {
      pushMessage(script[0]);
      setScriptIndex(1);
      setIsTyping(false);
    }, 500);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isTyping]);

  const sendOption = (text: string) => {
    if (isTyping || scriptIndex >= script.length) return;
    pushMessage({ role: "user", text });
    const next = scriptIndex + 1;
    setScriptIndex(next + 1);
    if (next < script.length) {
      setIsTyping(true);
      window.setTimeout(() => {
        pushMessage(script[next]);
        setIsTyping(false);
      }, 650);
    }
  };

  const currentMessage = messages[messages.length - 1];
  const quickReplies =
    currentMessage?.role === "assistant" && !currentMessage.type
      ? script.find((item) => item.text === currentMessage.text)?.options
      : undefined;

  return (
    <main className="mx-auto flex w-full max-w-[1200px] flex-col px-6 pb-6 pt-10 lg:h-[calc(100vh-7.25rem)] lg:min-h-0">
      <div className="mb-6 shrink-0">
        <h1 className="text-2xl font-bold text-slate-900">AI 챗봇 문진</h1>
        <p className="mt-0.5 text-sm text-slate-500">
          증상을 남기면 AI가 응급도와 예약 가능 시간을 정리합니다.
        </p>
      </div>

      <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm lg:min-h-0 lg:flex-1">
        <div className="grid lg:min-h-0 lg:flex-1 lg:grid-cols-[200px_200px_1fr]">
          <aside className="flex h-[220px] flex-col border-b border-slate-100 bg-slate-50/70 lg:h-auto lg:min-h-0 lg:border-b-0 lg:border-r">
            <div className="flex h-14 shrink-0 items-center justify-center border-b border-slate-100 px-3">
              <h2 className="text-center text-[15px] font-bold text-slate-900">반려동물</h2>
            </div>
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3">
              <div className="mt-4 space-y-2">
                {pets.map((pet, index) => (
                  <button
                    key={pet.id}
                    type="button"
                    className={[
                      "flex w-full items-center gap-2 rounded-2xl border p-2 text-left transition",
                      index === 0
                        ? "border-blue-200 bg-blue-50 shadow-sm"
                        : "border-transparent bg-white hover:bg-blue-50/60",
                    ].join(" ")}
                  >
                    <span className={`flex h-11 w-11 items-center justify-center rounded-full text-sm font-black ring-2 ring-white ${pet.color}`}>
                      {pet.name[0]}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-extrabold text-slate-900">
                      {pet.name}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          <aside className="flex h-[220px] flex-col border-b border-slate-100 bg-white lg:h-auto lg:min-h-0 lg:border-b-0 lg:border-r">
            <div className="flex h-14 shrink-0 items-center justify-center border-b border-slate-100 px-4">
              <h2 className="text-center text-[15px] font-bold text-slate-900">상담 기록</h2>
            </div>
            <div className="shrink-0 px-4 pt-6">
              <button type="button" className="flex h-10 w-full items-center justify-center rounded-xl bg-blue-600 px-4 text-sm font-bold text-white">
                새 상담
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
              <div className="mt-4 divide-y divide-slate-100 border-y border-slate-100">
                {histories.map((history) => (
                  <button
                    key={history.id}
                    type="button"
                    className={[
                      "block w-full border-l-2 px-1 py-3 pr-9 text-left transition",
                      history.active ? "border-blue-300 bg-blue-50" : "border-transparent bg-white hover:bg-blue-50/60",
                    ].join(" ")}
                  >
                    <span className="block truncate text-sm font-extrabold text-slate-900">
                      {history.title}
                    </span>
                    <span className="mt-2 block whitespace-nowrap text-[10px] font-bold text-slate-400">
                      {history.date}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          <section className="relative flex min-h-[480px] flex-col overflow-hidden bg-white lg:min-h-0">
            <div className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-100 px-5 sm:px-7">
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-base font-extrabold text-slate-950">
                  새 문진 - 2026-06-17
                </h2>
              </div>
              <label className="flex shrink-0 items-center gap-1.5">
                <span className="text-xs font-bold text-slate-400">병원</span>
                <select className="h-9 max-w-[170px] rounded-lg border border-slate-200 bg-white px-2 text-xs font-bold text-slate-700 outline-none">
                  <option>해피펫 동물병원</option>
                </select>
              </label>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5 sm:p-7">
              <div className="flex-1" />
              {messages.map((message) => {
                if (message.role === "user") return <UserBubble key={message.id} text={message.text} />;
                if (message.type === "slots") {
                  return (
                    <div key={message.id} className="max-w-[92%] space-y-3 self-start">
                      <AssistantBubble text={message.text} />
                      <SlotsCard onSelect={sendOption} />
                    </div>
                  );
                }
                if (message.type === "confirm") {
                  return (
                    <div key={message.id} className="max-w-[92%] space-y-3 self-start">
                      <AssistantBubble text={message.text} />
                      <ConfirmationCard />
                    </div>
                  );
                }
                if (message.type === "instructions") {
                  return (
                    <div key={message.id} className="max-w-[92%] space-y-3 self-start">
                      <AssistantBubble text={message.text} />
                      <InstructionsCard />
                    </div>
                  );
                }
                return <AssistantBubble key={message.id} text={message.text} />;
              })}

              {isTyping && (
                <div className="max-w-[82%] rounded-3xl rounded-bl-lg bg-slate-100 px-5 py-4 text-sm font-semibold leading-6 text-slate-700">
                  <span className="inline-flex items-center gap-1">
                    {[0, 1, 2].map((index) => (
                      <span
                        key={index}
                        className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400"
                        style={{ animationDelay: `${index * 0.15}s` }}
                      />
                    ))}
                  </span>
                </div>
              )}

              {quickReplies ? (
                <div className="flex flex-wrap gap-2">
                  {quickReplies.map((reply) => (
                    <button
                      key={reply}
                      type="button"
                      onClick={() => sendOption(reply)}
                      className="rounded-full border border-blue-200 bg-white px-4 py-2 text-xs font-extrabold text-blue-600 transition hover:bg-blue-50"
                    >
                      {reply}
                    </button>
                  ))}
                </div>
              ) : null}
              <div ref={scrollRef} />
            </div>

            <div className="border-t border-slate-100 p-3">
              <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5">
                <input
                  type="text"
                  disabled
                  placeholder="빠른 답변 버튼으로 데모를 진행해보세요"
                  className="flex-1 bg-transparent text-sm font-semibold text-slate-400 outline-none"
                />
                <button type="button" disabled className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600/40 text-white">
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function ReservationsView({ reservations }: { reservations: DemoReservation[] }) {
  const rows = [
    ...reservations,
    {
      id: 1,
      pet: "망망",
      date: "2026-06-11 14:00",
      hospital: "MediPaw 동물병원",
      doctor: "김수의",
      type: "정기검진",
      memo: "예방접종 일정 확인",
      status: "진료 완료",
      tone: "bg-emerald-50 text-emerald-700",
    },
  ];
  return (
    <PageShell title="예약 내역" description="예약 확정, 변경, 완료 상태를 확인합니다.">
      <section className="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-xs font-black text-slate-400">
            <tr>
              <th className="px-5 py-3">반려동물</th>
              <th className="px-5 py-3">예약 일시</th>
              <th className="px-5 py-3">병원</th>
              <th className="px-5 py-3">진료</th>
              <th className="px-5 py-3">상태</th>
              <th className="px-5 py-3">관리</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="px-5 py-4 font-extrabold text-slate-900">{row.pet}</td>
                <td className="px-5 py-4 font-semibold text-slate-600">{row.date}</td>
                <td className="px-5 py-4">
                  <p className="font-semibold text-slate-700">{row.hospital}</p>
                  <p className="mt-0.5 text-xs font-bold text-slate-400">{row.doctor} 원장</p>
                </td>
                <td className="px-5 py-4 font-semibold text-slate-600">{row.type}</td>
                <td className="px-5 py-4">
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${row.tone}`}>{row.status}</span>
                </td>
                <td className="px-5 py-4">
                  <button type="button" className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600">
                    상세 보기
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </PageShell>
  );
}

function ReservationModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (reservation: DemoReservation) => void;
}) {
  const [visitType, setVisitType] = useState("일반진료");
  const [doctor, setDoctor] = useState("김수의");
  const [time, setTime] = useState("11:00");
  const [memo, setMemo] = useState("");
  const times = ["11:00", "11:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00"];

  const submitReservation = () => {
    onConfirm({
      id: Date.now(),
      pet: "망망",
      date: `2026-06-18 ${time}`,
      hospital: "MediPaw 동물병원",
      doctor,
      type: visitType,
      memo,
      status: "예약 확정",
      tone: "bg-teal-50 text-teal-700",
    });
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 px-4 py-4">
      <section className="max-h-full w-full max-w-xl overflow-y-auto rounded-2xl bg-white shadow-2xl shadow-slate-900/20">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5 sm:px-6">
          <h2 className="text-lg font-extrabold text-slate-950">바로 예약</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-50 hover:text-slate-700"
            aria-label="예약 모달 닫기"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            submitReservation();
          }}
        >
          <div className="space-y-4 px-5 py-4 sm:px-6">
          <div className="flex items-center justify-center gap-3 py-1">
            <div className="h-10 w-10 shrink-0 overflow-hidden rounded-full bg-slate-100 shadow-sm">
              <img src={pet.image} alt="망망 사진" className="h-full w-full object-cover" />
            </div>
            <p className="text-lg font-extrabold text-slate-900">망망</p>
          </div>

            <FieldGroup title="진료 타입" required>
              <div className="flex gap-2">
                {["일반진료", "정기검진"].map((type) => (
                  <OptionButton
                    key={type}
                    selected={visitType === type}
                    onClick={() => setVisitType(type)}
                  >
                    {type}
                  </OptionButton>
                ))}
              </div>
            </FieldGroup>

            <FieldGroup title="병원" required>
              <button
                type="button"
                className="flex h-11 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 pr-3 text-left text-sm font-bold text-slate-900 outline-none transition focus:border-teal-400 focus:ring-4 focus:ring-teal-100"
              >
                MediPaw 동물병원
                <ChevronDown className="h-5 w-5 text-slate-400" />
              </button>
            </FieldGroup>

            <FieldGroup title="원장" required>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {["관리자", "김수의"].map((name) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setDoctor(name)}
                    className={[
                      "flex flex-col items-center gap-0.5 rounded-xl border px-2 py-2.5 text-center transition",
                      doctor === name
                        ? "border-teal-700 bg-teal-50"
                        : "border-slate-200 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    <span className="text-sm font-bold text-slate-900">{name}</span>
                  </button>
                ))}
              </div>
            </FieldGroup>

            <FieldGroup title="예약 날짜" required>
              <button
                type="button"
                className="flex h-11 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-900 outline-none transition focus:border-teal-400 focus:ring-4 focus:ring-teal-100"
              >
                2026.06.18
                <CalendarDays className="h-5 w-5 text-slate-400" />
              </button>
            </FieldGroup>

            <div>
              <h3 className="text-sm font-extrabold text-slate-900">가능한 시간</h3>
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
                {times.map((slot) => (
                  <button
                    key={slot}
                    type="button"
                    onClick={() => setTime(slot)}
                    className={[
                      "h-10 rounded-xl border text-sm font-extrabold transition",
                      time === slot
                        ? "border-teal-700 bg-teal-700 text-white"
                        : "border-teal-100 text-teal-700 hover:bg-teal-50",
                    ].join(" ")}
                  >
                    {slot}
                  </button>
                ))}
              </div>
            </div>

            <FieldGroup title="예약 메모" hint="선택 사항">
              <textarea
                value={memo}
                onChange={(event) => setMemo(event.target.value)}
                placeholder="검진 전 전달할 내용을 입력해주세요."
                rows={3}
                className="mt-1.5 w-full resize-none rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-teal-400 focus:ring-4 focus:ring-teal-100"
              />
            </FieldGroup>
          </div>

        <div className="flex justify-end gap-3 border-t border-slate-100 px-5 py-3.5 sm:px-6">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 items-center justify-center rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-600 transition hover:bg-slate-50"
          >
            취소
          </button>
          <button
            type="submit"
            className="inline-flex h-10 min-w-[112px] items-center justify-center rounded-xl bg-teal-700 px-4 text-sm font-bold text-white transition hover:bg-teal-800"
          >
            예약 확정
          </button>
        </div>
        </form>
      </section>
    </div>
  );
}

function FieldGroup({
  title,
  hint,
  required,
  children,
}: {
  title: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-sm font-extrabold text-slate-900">
        {title}
        {required ? <span className="ml-1 text-rose-500">*</span> : null}
        {hint ? <span className="ml-1 font-semibold text-slate-400">{`(${hint})`}</span> : null}
      </h3>
      {children}
    </div>
  );
}

function OptionButton({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "inline-flex h-10 flex-1 items-center justify-center rounded-xl text-sm font-bold transition",
        selected
          ? "bg-teal-700 text-white"
          : "border border-slate-200 text-slate-600 hover:bg-slate-50",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function MyPageView() {
  return (
    <PageShell
      title="마이페이지"
      description="보호자 계정 정보와 보안 설정을 관리합니다."
      rightAction={
        <button
          type="button"
          className="text-sm font-extrabold text-slate-400 transition hover:text-teal-700"
        >
          비밀번호 변경
        </button>
      }
    >
      <div className="space-y-6">
        <section className="rounded-2xl border border-slate-100 bg-white p-8 shadow-sm">
          <div className="flex flex-col gap-5 border-b border-slate-100 pb-6 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-base font-black text-slate-950">회원 정보</h2>
              <p className="mt-1 text-sm font-semibold text-slate-500">
                이름과 휴대폰 번호를 최신 정보로 유지해주세요.
              </p>
            </div>
            <button
              type="button"
              className="h-12 rounded-xl bg-teal-700 px-6 text-sm font-extrabold text-white transition hover:bg-teal-800"
            >
              정보 수정
            </button>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <ProfileInfoBox label="이름" value="김보호자" />
            <ProfileInfoBox label="휴대폰 번호" value="01022222222" />
            <ProfileInfoBox label="가입일" value="2026-06-16" />
          </div>
        </section>

        <section className="rounded-2xl border border-slate-100 bg-white p-8 shadow-sm">
          <div className="border-b border-slate-100 pb-6">
            <h2 className="text-base font-black text-slate-950">내 병원</h2>
            <p className="mt-1 text-sm font-semibold text-slate-500">
              다니는 동물병원을 등록하고 기본 병원을 설정하세요.
            </p>
          </div>

          <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50 px-4 py-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <p className="truncate text-sm font-black text-slate-900">MediPaw 동물병원</p>
                <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-extrabold text-teal-700">
                  기본
                </span>
              </div>
              <button type="button" className="text-xs font-extrabold text-slate-400 transition hover:text-slate-600">
                삭제
              </button>
            </div>
          </div>

          <div className="mt-6">
            <label htmlFor="guardian-demo-hospital-search" className="text-sm font-black text-slate-950">
              병원 추가
            </label>
            <div className="mt-3 flex gap-2">
              <input
                id="guardian-demo-hospital-search"
                type="text"
                disabled
                placeholder="병원 이름으로 검색"
                className="h-12 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-700 outline-none placeholder:text-slate-400"
              />
              <button
                type="button"
                className="h-12 rounded-xl bg-teal-700 px-6 text-sm font-extrabold text-white transition hover:bg-teal-800"
              >
                검색
              </button>
            </div>
          </div>
        </section>
      </div>
    </PageShell>
  );
}

function ProfileInfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-h-24 rounded-xl border border-slate-100 bg-slate-50 px-4 py-4">
      <p className="text-sm font-extrabold text-slate-400">{label}</p>
      <p className="mt-3 text-base font-black text-slate-950">{value}</p>
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

export default function GuardianDemoPage() {
  const [activeView, setActiveView] = useState<GuardianView>("home");
  const [isReservationModalOpen, setIsReservationModalOpen] = useState(false);
  const [reservations, setReservations] = useState<DemoReservation[]>([]);

  const confirmReservation = (reservation: DemoReservation) => {
    setReservations((current) => [reservation, ...current]);
    setIsReservationModalOpen(false);
    setActiveView("reservations");
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-950">
      <GuardianNavbar activeView={activeView} onSelect={setActiveView} />
      {activeView === "home" && (
        <HomeView
          onSelect={setActiveView}
          onReserve={() => setIsReservationModalOpen(true)}
        />
      )}
      {activeView === "hospitals" && <HospitalsView />}
      {activeView === "chatbot" && <ChatbotView />}
      {activeView === "reservations" && <ReservationsView reservations={reservations} />}
      {activeView === "mypage" && <MyPageView />}
      {isReservationModalOpen ? (
        <ReservationModal
          onClose={() => setIsReservationModalOpen(false)}
          onConfirm={confirmReservation}
        />
      ) : null}
      <DemoFloatingBar />
    </div>
  );
}
