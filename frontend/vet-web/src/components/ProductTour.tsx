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

const STORAGE_KEY = "medipaw.vet.productTour.v1";
const START_EVENT = "medipaw:vet-tour:start";

const steps: TourStep[] = [
  {
    id: "dashboard-summary",
    route: "/home",
    target: "vet-dashboard-summary",
    title: "오늘 진료 현황을 빠르게 봅니다",
    description: "대기, 응급, 완료 현황을 요약 카드로 확인하고 하루 업무 흐름을 잡을 수 있습니다.",
  },
  {
    id: "dashboard-schedule",
    route: "/home",
    target: "vet-dashboard-schedule",
    title: "오늘 일정 흐름을 확인합니다",
    description: "진료실과 수의사 기준으로 예약과 진료 일정을 타임라인에서 확인합니다.",
  },
  {
    id: "reservation",
    route: "/reservation",
    target: "vet-reservation",
    title: "예약을 일간, 주간, 월간으로 관리합니다",
    description: "예약 추가, 날짜 이동, 상태 필터, 일정 상세 확인을 예약 관리 화면에서 처리합니다.",
  },
  {
    id: "emr-queue",
    route: "/emr",
    target: "vet-emr-queue",
    title: "접수 / 대기에서 오늘 환자를 선택합니다",
    description: "날짜와 담당 수의사를 바꾸며 진료 대기·완료 환자를 확인하고, 환자를 선택하면 오른쪽 패널들이 같은 환자 기준으로 채워집니다.",
  },
  {
    id: "emr-history",
    route: "/emr",
    target: "vet-emr-history",
    title: "문진과 히스토리를 먼저 검토합니다",
    description: "보호자가 남긴 사전 문진, 첨부 파일, 경과 보고와 과거 진료 기록을 한 패널에서 확인해 진료 전 맥락을 빠르게 잡습니다.",
  },
  {
    id: "emr-chart",
    route: "/emr",
    target: "vet-emr-chart",
    title: "진료 기록과 첨부를 바로 작성합니다",
    description: "SOAP 메모를 입력하고 사진·PDF·영상 파일을 함께 올립니다. 오늘 진료 화면에서만 수정 가능하고, 조회 날짜에서는 읽기 전용으로 전환됩니다.",
  },
  {
    id: "emr-prescription",
    route: "/emr",
    target: "vet-emr-prescription",
    title: "처방 입력과 미리보기를 이어서 처리합니다",
    description: "약명을 검색해 처방을 추가하고 형태, 용량, 용법, 기간, 필수 여부를 조정합니다. 자동 생성과 처방전 미리보기까지 같은 영역에서 끝냅니다.",
  },
  {
    id: "patients",
    route: "/patients",
    target: "vet-patients",
    title: "환자 기록을 조회하고 관리합니다",
    description: "환자 목록을 검색하고 상세 기록으로 들어가 과거 내원 정보를 확인할 수 있습니다.",
  },
  {
    id: "hospital",
    route: "/hospital-manage",
    target: "vet-hospital",
    title: "보호자에게 보이는 병원 정보를 관리합니다",
    description: "병원 소개, 진료시간, 의료진 정보와 보호자 화면 미리보기를 함께 확인하며 수정합니다.",
  },
  {
    id: "settings",
    route: "/settings",
    target: "vet-settings",
    title: "병원과 계정 설정을 관리합니다",
    description: "계정 보안과 병원 운영에 필요한 설정을 이 영역에서 관리합니다.",
  },
];

export function startVetProductTour() {
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
    if ((location.pathname === "/home" || location.pathname === "/dashboard") && !hasCompletedTour()) {
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
          className="pointer-events-none absolute rounded-lg border-2 border-blue-400 bg-white/10 shadow-[0_0_0_9999px_rgba(15,23,42,0.15)]"
          style={targetRect}
        />
      )}
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="vet-tour-title"
        className="absolute w-[min(360px,calc(100vw-32px))] rounded-xl border border-slate-100 bg-white p-5 shadow-2xl shadow-slate-950/20"
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
        <h2 id="vet-tour-title" className="text-lg font-extrabold text-slate-950">
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
            className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-extrabold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            이전
          </button>
          <button
            type="button"
            onClick={() => (isLast ? close() : moveTo(activeIndex + 1))}
            className="h-10 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white transition hover:bg-blue-700"
          >
            {isLast ? "완료" : "다음"}
          </button>
        </div>
      </section>
    </div>
  );
};

export default ProductTour;
