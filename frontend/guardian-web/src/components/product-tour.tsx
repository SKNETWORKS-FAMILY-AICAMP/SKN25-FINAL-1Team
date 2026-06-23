import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useLocation, useNavigate } from "react-router-dom";

interface TourStep {
  id: string;
  route: string;
  target: string;
  title: string;
  description: string;
}

interface TargetRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const STORAGE_KEY = "medipaw.guardian.productTour.v1";
const START_EVENT = "medipaw:guardian-tour:start";

const steps: TourStep[] = [
  {
    id: "home",
    route: "/home",
    target: "guardian-home",
    title: "홈에서 반려동물을 확인해요",
    description: "등록된 반려동물, 상세 정보, 상담과 예약 진입을 한 화면에서 시작할 수 있습니다.",
  },
  {
    id: "hospitals",
    route: "/hospitals",
    target: "guardian-hospitals",
    title: "다니는 병원을 관리해요",
    description: "연결된 병원의 진료시간, 연락처, 의료진 정보를 확인하고 병원을 전환할 수 있습니다.",
  },
  {
    id: "chatbot",
    route: "/chatbot",
    target: "guardian-chatbot",
    title: "챗봇 상담으로 예약까지 이어가요",
    description: "증상 상담, 병원 안내, 예약 추천을 대화 흐름 안에서 처리할 수 있습니다.",
  },
  {
    id: "reservations",
    route: "/reservations",
    target: "guardian-reservations",
    title: "예약 내역을 확인해요",
    description: "예정된 예약과 지난 예약을 확인하고, 가능한 예약은 변경하거나 취소할 수 있습니다.",
  },
  {
    id: "mypage",
    route: "/mypage",
    target: "guardian-mypage",
    title: "내 정보와 병원 연결을 관리해요",
    description: "보호자 정보, 비밀번호, 연결 병원 정보를 마이페이지에서 정리할 수 있습니다.",
  },
];

export function startGuardianProductTour() {
  window.dispatchEvent(new Event(START_EVENT));
}

function hasCompletedTour() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "done";
  } catch {
    return true;
  }
}

function completeTour() {
  try {
    window.localStorage.setItem(STORAGE_KEY, "done");
  } catch {
    // localStorage를 사용할 수 없는 환경에서는 현재 세션에서만 닫힌다.
  }
}

function getTargetRect(target: string): TargetRect | null {
  const element = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!element) return null;

  element.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;

  const margin = 8;
  return {
    top: Math.max(8, rect.top - margin),
    left: Math.max(8, rect.left - margin),
    width: Math.min(window.innerWidth - 16, rect.width + margin * 2),
    height: Math.min(window.innerHeight - 16, rect.height + margin * 2),
  };
}

function getTooltipStyle(rect: TargetRect | null): CSSProperties {
  if (!rect || window.innerWidth < 768) {
    return {
      left: "50%",
      top: "50%",
      transform: "translate(-50%, -50%)",
    };
  }

  const tooltipWidth = 360;
  const gap = 14;
  const left = Math.min(
    Math.max(16, rect.left + rect.width + gap),
    window.innerWidth - tooltipWidth - 16,
  );
  const belowTop = rect.top + rect.height + gap;
  const top =
    belowTop + 220 < window.innerHeight
      ? belowTop
      : Math.max(16, rect.top - 220 - gap);

  return { left, top };
}

const ProductTour = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null);

  const activeStep = steps[activeIndex];
  const isLast = activeIndex === steps.length - 1;

  const refreshTarget = useCallback(() => {
    if (!activeStep) return;
    window.setTimeout(() => setTargetRect(getTargetRect(activeStep.target)), 80);
  }, [activeStep]);

  const start = useCallback(() => {
    setActiveIndex(0);
    setIsOpen(true);
    if (location.pathname !== steps[0].route) {
      navigate(steps[0].route);
    }
  }, [location.pathname, navigate]);

  const close = useCallback(() => {
    completeTour();
    setIsOpen(false);
  }, []);

  const moveTo = useCallback(
    (nextIndex: number) => {
      const nextStep = steps[nextIndex];
      if (!nextStep) return;
      setActiveIndex(nextIndex);
      if (location.pathname !== nextStep.route) {
        navigate(nextStep.route);
      }
    },
    [location.pathname, navigate],
  );

  useEffect(() => {
    const handleStart = () => start();
    window.addEventListener(START_EVENT, handleStart);
    return () => window.removeEventListener(START_EVENT, handleStart);
  }, [start]);

  useEffect(() => {
    if (location.pathname === "/home" && !hasCompletedTour()) {
      window.setTimeout(() => start(), 600);
    }
  }, [location.pathname, start]);

  useEffect(() => {
    if (!isOpen) return;
    refreshTarget();

    const handleResize = () => refreshTarget();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [isOpen, location.pathname, refreshTarget]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "Enter" || event.key === "ArrowRight") {
        event.preventDefault();
        if (isLast) close();
        else moveTo(activeIndex + 1);
      }
      if (event.key === "ArrowLeft" && activeIndex > 0) {
        event.preventDefault();
        moveTo(activeIndex - 1);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, close, isLast, isOpen, moveTo]);

  const tooltipStyle = useMemo(() => getTooltipStyle(targetRect), [targetRect]);

  if (!isOpen || !activeStep) return null;

  return (
    <div className="fixed inset-0 z-[1000]">
      <div className="absolute inset-0 bg-slate-950/55" />
      {targetRect && (
        <div
          className="pointer-events-none absolute rounded-2xl border-2 border-blue-400 bg-white/10 shadow-[0_0_0_9999px_rgba(15,23,42,0.15)]"
          style={targetRect}
        />
      )}
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="guardian-tour-title"
        className="absolute w-[min(360px,calc(100vw-32px))] rounded-2xl border border-slate-100 bg-white p-5 shadow-2xl shadow-slate-950/20"
        style={tooltipStyle}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-extrabold text-blue-600">
            {activeIndex + 1} / {steps.length}
          </span>
          <button
            type="button"
            onClick={close}
            className="text-xs font-extrabold text-slate-400 hover:text-slate-700"
          >
            건너뛰기
          </button>
        </div>
        <h2 id="guardian-tour-title" className="text-lg font-extrabold text-slate-950">
          {activeStep.title}
        </h2>
        <p className="mt-2 text-sm font-semibold leading-6 text-slate-600">
          {activeStep.description}
        </p>
        <div className="mt-5 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => moveTo(activeIndex - 1)}
            disabled={activeIndex === 0}
            className="h-10 rounded-xl border border-slate-200 px-4 text-sm font-extrabold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            이전
          </button>
          <button
            type="button"
            onClick={() => (isLast ? close() : moveTo(activeIndex + 1))}
            className="h-10 rounded-xl bg-blue-600 px-5 text-sm font-extrabold text-white transition hover:bg-blue-700"
          >
            {isLast ? "완료" : "다음"}
          </button>
        </div>
      </section>
    </div>
  );
};

export default ProductTour;
