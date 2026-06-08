import type { LucideIcon } from "lucide-react";
import {
  Bot,
  CalendarCheck,
  ClipboardList,
  FileText,
  HeartPulse,
  ImagePlus,
  LayoutDashboard,
  MessageCircle,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from "lucide-react";

export interface IconTextItem {
  title: string;
  text: string;
  Icon: LucideIcon;
}

export interface ModuleCard {
  eyebrow: string;
  title: string;
  Icon: LucideIcon;
  items: string[];
}

export const marqueeItems = [
  "AI 문진",
  "Red Flag 표시",
  "예약 우선순위",
  "SOAP 초안",
  "Follow-up",
  "병원 대시보드",
  "보호자 상담",
  "진료 흐름 자동화",
];

export const workflowSteps: IconTextItem[] = [
  {
    title: "보호자 입력",
    text: "일상어 증상, 사진, 반려동물 정보를 자연스럽게 수집합니다.",
    Icon: MessageCircle,
  },
  {
    title: "AI 구조화",
    text: "문진 내용을 주증상, 발생 시점, 위험 신호 후보로 정리합니다.",
    Icon: Bot,
  },
  {
    title: "예약/차트 초안",
    text: "예약 흐름과 SOAP 형식 EMR 초안을 진료 전 준비합니다.",
    Icon: ClipboardList,
  },
  {
    title: "수의사 검토",
    text: "최종 판단과 수정, 승인 권한은 항상 수의사에게 남깁니다.",
    Icon: Stethoscope,
  },
];

export const moduleCards: ModuleCard[] = [
  {
    eyebrow: "Guardian Web",
    title: "보호자가 증상을 쉽게 남기고 예약까지 이어갑니다.",
    Icon: UserRound,
    items: ["반려동물 등록", "AI 챗봇 문진", "증상 이미지 업로드", "진료 예약 신청", "Follow-up 기록"],
  },
  {
    eyebrow: "Veterinarian Web",
    title: "병원은 예약, 환자, EMR 흐름을 한 화면에서 봅니다.",
    Icon: LayoutDashboard,
    items: ["오늘의 진료 현황", "예약 관리", "환자 목록", "EMR 작성", "알림"],
  },
  {
    eyebrow: "AI Guardrails",
    title: "AI 산출물은 초안과 표시로 제한하고 검토 근거를 남깁니다.",
    Icon: ShieldCheck,
    items: ["응급 신호 감지", "문진-차트 일관성", "검증 가능한 근거", "수의사 승인 중심", "Human-in-the-Loop"],
  },
];

export const dashboardRows = [
  { name: "호흡 이상", status: "Red Flag", color: "text-red-600 bg-red-50 border-red-100" },
  { name: "반복 구토", status: "확인 필요", color: "text-orange-600 bg-orange-50 border-orange-100" },
  { name: "피부 가려움", status: "일반", color: "text-green-700 bg-green-50 border-green-100" },
];

export const dashboardMetrics = [
  { label: "오늘 예약", value: "12건", Icon: CalendarCheck },
  { label: "차트 초안", value: "5건", Icon: FileText },
  { label: "이미지 문진", value: "3건", Icon: ImagePlus },
  { label: "검토 알림", value: "2건", Icon: HeartPulse },
];

export const safetyPrinciples = [
  ["초안", "SOAP 기록은 바로 확정되지 않고 수의사가 수정할 수 있는 초안으로 제공됩니다."],
  ["표시", "Red Flag는 진단명이 아니라 검토가 필요한 신호로만 표시됩니다."],
  ["검토", "문진 원문, 이미지, 요약 근거를 함께 보여줘 독립적인 검토가 가능하게 합니다."],
];
