import type { Language } from "./translations";

type Translator = (key: string) => string;

const knownTextKey: Record<string, string> = {
  정기검진: "schedule.categoryCheckup",
  일반진료: "schedule.categoryGeneral",
  일반: "schedule.categoryGeneral",
  "증상 상담": "schedule.categorySymptom",
  "어떤 증상 때문에 예약을 원하시나요?": "chatbot.initialQuestion",
  상담중: "chatbot.statusConsulting",
  진료완료: "chatbot.statusCompleted",
  예약대기: "schedule.statusPending",
  대기: "schedule.statusPending",
  예약확정: "schedule.statusConfirmed",
  예약취소: "schedule.statusCancelled",
  취소: "schedule.statusCancelled",
  "말씀해 주셔서 감사해요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요 🙏":
    "chatbot.readyToBookThanks",
  "증상 잘 알려주셨어요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요 🙏":
    "chatbot.readyToBookSymptom",
  "증상을 잘 알려주셨어요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요.":
    "chatbot.readyToBookSymptom",
  "조금 더 구체적으로 말씀해 주시거나, 아래 보기 중에서 골라 주세요 🙏":
    "chatbot.pickMoreSpecific",
  "일시적인 오류로 답변을 불러오지 못했어요. 잠시 후 다시 시도해주세요.":
    "chatbot.responseLoadError",
  "숨 쉬기 힘들어해요": "chatbot.triageRespiratory",
  "발작 / 경련해요": "chatbot.triageSeizure",
  쓰러졌어요: "chatbot.triageCollapse",
  "피가 나요": "chatbot.triageBleeding",
  "심장이 이상한 것 같아요": "chatbot.triageHeart",
  "못 걷거나 마비가 왔어요": "chatbot.triageMobility",
  "토하거나 설사해요": "chatbot.triageGi",
  "다쳤어요 (외상)": "chatbot.triageTrauma",
  "소변 / 배변 문제": "chatbot.triageUrinary",
  "기운 없고 잘 못 먹어요": "chatbot.triageLowEnergy",
};

const koFallback = (value: string, lang: Language) =>
  lang === "ko" ? value : undefined;

export const translateKnownText = (
  value: string | null | undefined,
  t: Translator,
  lang: Language,
) => {
  if (!value) return "";
  const key = knownTextKey[value.trim()];
  return key ? t(key) : koFallback(value, lang) ?? value;
};
