import type { Language } from "./translations";

type Translator = (key: string) => string;

const knownTextKey: Record<string, string> = {
  정기검진: "schedule.categoryCheckup",
  일반진료: "schedule.categoryGeneral",
  일반: "schedule.categoryGeneral",
  "증상 상담": "schedule.categorySymptom",
  "어떤 증상 때문에 예약을 원하시나요?": "chatbot.initialQuestion",
  구토: "chatbot.symptomVomiting",
  설사: "chatbot.symptomDiarrhea",
  피부: "chatbot.symptomSkin",
  기침: "chatbot.symptomCough",
  식욕저하: "chatbot.symptomLowAppetite",
  눈물: "chatbot.symptomTears",
  절뚝거림: "chatbot.symptomLimping",
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
  "위 시간 중 하나를 선택해주세요.": "chatbot.selectSlotPrompt",
  "첨부파일을 보냈습니다.": "chatbot.attachmentSent",
  "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.":
    "chatbot.responseDelayed",
  "응답을 불러오지 못했습니다.": "chatbot.responseLoadError",
  "메시지를 전송하지 못했습니다.": "chatbot.sendFailed",
  "잠시만요, 예약 가능한 시간을 확인하고 있어요 ⏳":
    "chatbot.checkingSlots",
  "예약 시간을 계산하는 데 시간이 걸리고 있어요. 아래에서 날짜를 선택해 가능한 시간을 확인해주세요. 📅":
    "chatbot.slotsLoadSlow",
  "예약 가능한 시간을 불러오지 못했어요. 예약 페이지에서 직접 예약해주세요.":
    "chatbot.slotsLoadError",
  "예약 가능한 시간을 찾았어요. 편한 시간을 선택해주세요. 🗓️":
    "chatbot.slotsFound",
  "지금 바로 추천드릴 시간이 없어요. 아래에서 직접 날짜를 선택해주세요. 📅":
    "chatbot.noSlotsPickDate",
  "예약 시간 확인 중 오류가 발생했어요. 예약 페이지에서 직접 예약해주세요.":
    "chatbot.slotCheckError",
  "예약 시간 확인 중 오류가 발생했어요. 아래에서 날짜를 선택해 가능한 시간을 다시 확인해주세요. 📅":
    "chatbot.slotCheckRetry",
  "예약을 처리하고 있어요...": "chatbot.processingBooking",
  "문진 예약 데이터가 존재하지 않습니다. 처음부터 상담을 진행해주세요.":
    "chatbot.noTriageData",
  "예약일까지 증상 변화를 모니터링할게요. 증상이 변하면 여기에 알려주세요.":
    "chatbot.monitoring",
  "예약 중 오류가 발생했어요. 아래 시간에서 다시 선택해주세요.":
    "chatbot.bookingError",
  "경과가 기록되었어요. 담당 수의사에게 전달됩니다.":
    "chatbot.followupRecorded",
  "기록에 실패했어요. 다시 시도해주세요.": "chatbot.recordFailed",
  "문진 데이터가 없습니다. 처음부터 상담을 다시 진행해주세요.":
    "chatbot.noTriageDataRestart",
  "이전 경과 보고를 이어서 진행할 수 있어요. 증상 변화나 사진을 보내주세요. 📸":
    "chatbot.restoreFollowup",
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
