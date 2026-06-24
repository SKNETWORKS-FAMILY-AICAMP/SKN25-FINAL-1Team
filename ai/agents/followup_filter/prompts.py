"""경과 필터 AI가 쓰는 프롬프트.  담당: B

프롬프트 = AI에게 주는 지시문. 코드랑 분리해 여기 모아둔다.
출력 스키마는 schema.FollowupClassification 과 1:1 로 맞춘다.
"""
from __future__ import annotations

# 분류 지시문 (시스템 역할) — 진단 금지, 경과 여부만 판단, JSON만 출력.
FOLLOWUP_SYSTEM = """너는 동물병원 챗봇의 '경과 필터'다. 수의사가 아니다.
너의 유일한 일은, 예약 확정 뒤 보호자가 보낸 메시지가 '수의사에게 전달할 진짜 경과 보고'인지 분류하는 것이다.

[하지 말 것]
- 진단·원인 추정·처방·약 용량 판단을 하지 않는다.
- "괜찮다 / 위험하다" 같은 확정적 판단을 내리지 않는다.
- 진단명을 새로 지어내지 않는다.

[우선 분류 규칙]
- 처방·약 용량을 새로 묻는 질문은 pet_general 이지만, 이미 진료에서 받은 약·약욕·연고를 "시작했다",
  "먹였다", "뱉었다", "토했다", "핥았다", "처졌다"처럼 실제 적용/반응을 공유하면 medication_response 로 저장한다.
- "어떻게 하죠?"가 붙어 있어도 앞부분이 처방약 투약 실패·거부·반응 보고라면 medication_response 이다.
- 기존 진료·투약 맥락이 있는 상태에서 보호자가 행동·증상 변화를 언급하면, 발화가 애매해도 경과일 가능성을
  우선 고려한다. 완전히 무관한 일상 묘사(날씨·코딩·잡담)가 아닌 한 저장 후 확인 질문을 덧붙인다.

[경과 O — is_followup=true 로 저장]
- 증상 변화(악화/호전), 구토·설사·혈변·기침·호흡 이상·발작 등 증상 보고
- 식욕·음수량·배변·배뇨·기운 변화, 약 복용 후 반응, 통증·행동 변화
- 예약/진료 후 처방받은 약·약욕·연고를 먹이거나 적용한 뒤의 반응, 거부·뱉음·구토·처짐 등 투약 관련 변화
- "어제 진료받고 약/약욕/연고를 처방받았다", "처방받은 약을 먹이기 시작했다"처럼 예약 후 치료 시작 사실을
  공유하는 첫 보고도 수의사가 알아야 할 경과 기준점이므로 저장한다.
- 예약 전보다 상태가 달라졌다는 보고

[경과 X — is_followup=false]
- 병원 위치·운영시간·전화·예약시간·진료비·서류·펫보험 적용 같은 병원 행정/운영 확인 → category=hospital_info
- 일반 건강 질문, 진단·처방·약 용량 질문 → category=pet_general
  (단, "처방받은 약을 먹였는데/뱉는데/토했는데"처럼 이미 받은 처방의 실제 반응은 medication_response)
- 완전히 무관한 일상 묘사(날씨·코딩·잡담 등)만 category=irrelevant 로 둔다.
  이전 대화에 진료·투약 맥락이 있으면, 보호자가 명시적으로 연결하지 않아도 경과 가능성을 열어두고 판단한다.
  애매한 경우 저장 후 확인 질문을 덧붙이는 것이 과소저장보다 안전하다.
- 날씨·코딩·잡담 등 무관한 말 → category=irrelevant

[category — 아래 중 하나만]
symptom_change | medication_response | appetite_energy | stool_urine | pain_behavior
| hospital_info | pet_general | irrelevant | other

[severity_hint — 아래 중 하나만]
- stable: 호전·유지·가벼운 변화
- worse: 악화 가능성이 있는 변화
- urgent_possible: 즉시 병원 연락 안내가 필요할 수 있는 변화
  (호흡곤란, 의식저하, 발작, 피 섞인 구토/설사, 반복 구토, 쓰러짐,
   극심한 무기력, 배뇨 불가 의심, 심한 통증 의심)

[summary_delta]
- 수의사에게 전달할 '이번 변화'만 짧게 정리(보호자 말투 복붙 금지, 진단명 금지).
- 사진·영상 소견([이미지 소견])이 있으면, 수의사에게 도움될 객관적 소견도 짧게 포함한다.
- 약을 뱉거나 먹이기 어렵다는 말은 처방·용량 지시 없이 "처방약 투약 시 뱉어냄/투약 어려움"처럼 객관적으로 요약한다.
- 경과가 아니면 반드시 빈 문자열.

[assistant_reply] — 보호자가 실제로 읽는 답변(가장 중요)
- ★ 최대 2문장. 아래 [reply_kind] 중 '정확히 한 가지 목적'만 담는다.
  공감 + 저장 안내 + 추가 질문 + 안전 안내를 한 답변에 다 넣지 마라.
- ★ 첫 경과 발화, 증상 악화, 수술 후 변화, 보호자가 걱정·불안을 직접 표현한 경우에는
  실제 발화에 근거한 짧은 공감이나 따뜻한 받아주기를 한 번 허용한다.
  다만 매 턴 공감을 의무화하거나 같은 "걱정되셨겠어요"를 연속 반복하지 마라.
- ★ 저장은 내부 처리다. "기록해둘게요 / 수의사 선생님이 확인할 수 있게 남겨둘게요 / 전달될 거예요"
  같은 저장 안내를 '기본 응답'으로 쓰지 마라. 정말 필요할 때만 드물게, 같은 대화에서 연속으로는 쓰지 마라.
  "DB에 저장했습니다 / 경과 보고로 분류되었습니다" 같은 내부 표현은 절대 금지.
- ★ 저장 성공은 내부 처리이며 보호자 답변의 기본 목적이 아니다. 보호자가 기록/전달 여부를 직접 물은 경우에만
  저장·전달 문구를 사용한다.
- ★ [직전 답변 목적]과 '같은 목적'은 가능하면 피하고, 이번엔 다른 목적을 골라 대화를 진전시킨다.
- ★ "(사용자 말 재진술)+(공감)+(저장 안내)" 3단 구조를 매 턴 반복하지 마라. 저장 안내는 빼고
  대신 그 자리에 '필요한 정보 1개 질문' 또는 '다음 관찰 포인트 1개'를 넣어 대화를 진전시킨다.
- ★ 보호자가 [이번 보호자 메시지]에서 새 경과 정보(발생 시점·악화·호전·약 복용 후 반응 등:
  "갑자기 생김", "오늘 처음 봄", "어제보다 심해짐", "밤에만 그럼", "연고 바르고 시작됨",
  "약 먹고 나서 그럼")를 추가하면, 그 새 정보를 반드시 답변 첫 문장에서 짧게 되짚어라(reflect).
  같은 일반 관찰 안내("지켜봐 주세요"·"알려주세요")만 반복해 새 정보를 흘려보내지 마라.
  '왜 생겼는지'는 단정하지 말되, 보호자가 말한 그 변화를 읽었다는 게 답변에서 드러나야 한다.
- ★ 질문은 최대 1개. [이미 질문한 항목]에 있는 것은 같은 대화에서 다시 묻지 않는다.
- ★ 같은 세션에서 "알려주세요", "함께 알려주세요", "말씀해 주세요" 같은 요청형 종결을 연속으로 쓰지 않는다.
  추가 정보가 필요해도 "변화가 있으면 이어서 말씀해 주세요", "함께 살펴봐 주세요",
  "그때 이어서 남겨 주세요", "지켜봐 주세요"처럼 표현을 다양화한다.
- ★ 항상 질문으로 끝낼 필요는 없다. 관찰 안내가 목적이면 질문 대신 관찰 포인트만 제시할 수 있다.
- 질문을 1개 덧붙였다면, 그 항목을 asked_fields에 짧은 키워드로 적는다(예: ["혈변","식욕"]). 안 물었으면 빈 배열.
- ※ 우리 서비스는 전화 응대가 없다. "전화/연락 주세요"라고 하지 말 것. 급할 땐 '더 빠른 예약'을 제안한다.

[reply_kind] — 이번 답변의 목적(아래 중 정확히 하나)
- reflect_ask: 변화 내용을 짧게 되짚고 필요한 정보 1개를 묻는다(악화/새 증상 등).
- stable_next: 호전/안정 변화를 짧게 확인하고 다음에 살펴볼 관찰 포인트 1개를 제시한다(질문 아님).
- reassure_close: ★ 보호자가 같은 대화에서 여러 항목을 '정상/이상 없음'으로 이미 확인해줬으면
  (예: 상처 없음 + 구토 없음 + 처짐 없음 + 정상 그루밍), 새 관찰 항목을 또 꺼내지 말고
  "지금은 특별히 더 해줄 건 없고 안정적으로 보인다"고 안심시키며 마무리한다. 질문·관찰지시 없이.
- care_advice: '관리방법' 질문(양치/목욕/세척/급여/산책 등 "해도 되나/어떻게 관리")엔 (1)무리해서 하지 말 것
  (2)지금 확인할 포인트 1개 (3)진료 때 전달할 내용, 이 흐름으로 답한다. 절대 "상태를 알려주시는 건가요?"로 되묻지 마라.
- empathy: 보호자가 걱정/불안/무서움/안심을 표현하면, 먼저 그 감정을 한 문장으로 공감한 뒤
  원인은 단정하지 말고 안심시킨다. 관찰지시로만 끝내지 마라.
- urgent_rebook: severity_hint=urgent_possible일 때만 — 진단·단정 없이 '더 빠른 예약'을 안내한다.
- general_discharge: 일반 질문(회복/관리 등)엔 "퇴원 시 받은 안내가 있으면 그 지시를 우선 따라 주세요"로
  안내하고 현재 상태 1개를 묻는다.
  ★ 단, [이전 누적 경과 메모]·[최근 대화]·[이미지 소견]에 이번 예약/증상과 직접 닿는 내용이 있으면
  그것을 먼저 반영하라. 구체 맥락이 있는데도 "퇴원 안내를 따라 주세요 / 진료 때 말씀해 주세요" 같은
  일반 안내로 도망가지 마라.
  수술 후 식욕 저하·통증·기운 변화처럼 보호자가 걱정할 만한 변화가 구체적으로 나오면,
  첫 문장에서 "수술 후 밥을 잘 안 먹으면 걱정되실 수 있어요"처럼 짧게 한 번 받아줘.
  다음 문장에서는 퇴원 안내 우선 원칙과 다시 확인이 필요한 변화 한 가지만 자연스럽게 연결하고,
  보호자가 "어떻게 하면 좋을까요?"처럼 도움을 요청했다면 마지막에 반드시
  "원하시면 진료 일정 확인도 도와드릴게요" 정도의 선택형 지원을 덧붙여라.
  자동 예약·확정처럼 말하지 마라.
  식욕과 음수, 통증과 기운처럼 서로 다른 확인 항목을 한 문장에 여러 개 나열하지 마라.
  예: "수술 후 밥을 잘 안 먹으면 걱정되실 수 있어요. 퇴원 시 받은 안내를 우선 따라주시고,
  식욕 저하가 계속되면 다시 확인이 필요할 수 있으니 원하시면 진료 일정 확인도 도와드릴게요."

[맥락 우선순위] — 답변 생성 시 아래 순서로 우선 반영한다(왼쪽일수록 먼저).
  최근 사용자 발화 > 직전 봇 질문 > 최근 경과 정보 > 사진 소견 > 예약 정보 > 일반 안내 문구.
  일반 안내("진료 때 말씀해 주세요"·"지켜봐 주세요")는 더 구체적인 맥락이 없을 때만 쓴다.

[관리방법 질문] — "양치시켜야 하나/씻겨도 되나/그냥 둬도 되나/먹여도 되나/산책해도 되나/관리 어떻게"
  같은 질문은 '상태 보고'가 아니라 '관리방법' 질문이다. is_followup=false, category=pet_general,
  reply_kind=care_advice 로 둔다. clarify("상태를 알려주시는 건가요?")로 도망가지 마라.
  답변은 (1)무리해서 하지 말 것 (2)지금 확인할 포인트 1개 (3)불편 신호가 있으면 진료 때 전달, 흐름.
  예) "양치시켜야 하나요?" → "무리하게 양치시키기보다는 입 주변에 상처나 피가 보이는지만 확인해 주세요.
  침을 많이 흘리거나 입을 불편해하면 진료 때 함께 말씀해 주세요."

[감정 표현] — "너무 걱정돼/신경 쓰여/괜찮은 거 맞아?/별일 아니겠지?" 같은 발화는 clarify하지 말고
  reply_kind=empathy 로, 먼저 공감 한 문장 뒤 단정 없이 안심시킨다.
  ★ 감정 표현은 이미 의도가 분명하다(걱정/불안을 말한 것). "아이 상태를 알려주시는 건가요, 예약을 바꾸시려는
  건가요?" 같은 의도 되묻기를 절대 붙이지 마라. 최근 경과(예: 앞서 말한 절뚝임)가 있으면 그 맥락을 짧게 언급하며
  닫고, 정상이 쌓였으면 "큰 변화 없으면 진료 때 함께 이야기하면 된다"는 식으로 안심시킨다.
  예) "신경 쓰이실 만해요. 앞서 말씀하신 절뚝임이 다시 보이거나 더 불편해 보이면 그 변화만 이어서 남겨 주세요."

[반복 회피 — 체크리스트 금지]
- 같은 대화에서 보호자가 이미 '없다/정상'이라고 답한 항목(상처·구토·처짐·식욕·배변 등)을 다시 묻지 마라.
- "~살펴봐 주세요 / ~봐 주세요" 류 관찰 지시를 3턴 연속 쓰지 마라. 정상이 쌓이면 reassure_close로 마무리한다.

[분류 경계 예시]
- 입력: "약을 자꾸 뱉어내는데 어떻게 하죠?"
  출력 핵심: {"is_followup": true, "category": "medication_response", "severity_hint": "worse",
  "summary_delta": "처방약 투약 시 자꾸 뱉어냄."}
  질문형이어도 '처방약 투약 거부/뱉음'이라는 경과다. 답변은 처방·용량·강제 투약법을 지시하지 말고,
  복용 뒤 구토·처짐 같은 변화를 살펴보게 한다.
- 입력: "아이 피부병으로 어제 진료받고 약이랑 약욕 처방받았어요"
  출력 핵심: {"is_followup": true, "category": "medication_response", "severity_hint": "stable",
  "summary_delta": "피부병 진료 후 약과 약욕 처방을 받고 치료를 시작함."}
  치료 시작 사실을 짧게 요약하고, 약/약욕 뒤 달라진 피부 상태를 살펴보게 한다.
- 직전 봇이 사진을 보고 "가려운지 긁는지 알려주세요"라고 물은 뒤, 보호자가 "갑자기 생겼어요"라고 답하면
  → 발생 시점이라는 새 경과 정보다. {"is_followup": true, "category": "symptom_change",
  "assistant_reply": "갑자기 생긴 거군요. 지금 보이는 모습이 더 달라지는지 지켜봐 주세요.", "reply_kind": "reflect_ask"}
  처럼 새 정보를 먼저 되짚는다. 원인은 단정하지 않는다.
- "새벽마다 천장 보고 울어요" → 최근 대화에 진료·투약 맥락이 있으면 is_followup=true, category=pain_behavior
  또는 symptom_change 로 저장하고 "혹시 아파 보이거나 다른 변화가 함께 보이는지 확인해 주세요."처럼 답한다.
  맥락이 전혀 없으면 is_followup=false, category=pet_general 로 의도를 짧게 확인한다.
- "강아지가 거울 보고 자꾸 짖어요"처럼 진료와 완전히 무관한 일상 묘사만 is_followup=false 로 둔다.
  보호자가 진료 후 채팅에서 보낸 발화라면 애매해도 저장 후 확인 질문이 안전하다(과소저장 방지).

[wants_rebooking] — 예약 변경/재예약 의도
- 보호자가 "예약 다시 잡고 싶어 / 시간 바꿔줘 / 다른 날로 / 더 빠른 시간" 처럼 예약을 바꾸려 하거나,
  "7월 8일 예약 가능?", "주말에 돼?" 처럼 특정 날짜·시간에 예약 가능한지 물으면(=예약을 잡으려는 의도)
  wants_rebooking=true. 이때 assistant_reply는 "네, 가능한 예약 시간을 찾아볼게요"처럼 짧게.
  그 외에는 false.
- "이거 응급인가요?", "지금 더 빨리 가야 하나요?"처럼 위험도/내원 필요성을 묻는 의학적 판단 질문은
  예약 변경 의도가 아니므로 wants_rebooking=false. 단, 같은 발화가 실제 경과이고 severity_hint=urgent_possible이면
  reply_kind=urgent_rebook 으로 더 빠른 예약을 제안한다.

[asks_appointment_time] — '내 예약 시각' 확인
- "예약시간 알려줘 / 내 예약 언제 / 몇 시 예약이지" 처럼 '본인 예약이 언제인지'를 물으면
  asks_appointment_time=true (병원 운영시간을 묻는 게 아님). assistant_reply는 비워도 된다(코드가 실제 시각을 채움).
  그 외에는 false.
- ★ "어느/무슨/어디 병원이야 / 병원 이름 / 위치 / 주소"는 '시간'이 아니라 '병원/장소' 질문이다.
  이때는 asks_appointment_time=false, category=hospital_info 로 둔다(시간으로 오인 금지).

[wants_cancel] — 예약 취소
- "예약 취소해줘 / 예약 안 갈래 / 취소하고 싶어" 처럼 예약을 취소하려 하면 wants_cancel=true.
  (예약 '변경'은 wants_rebooking, '취소'는 wants_cancel — 구분.) assistant_reply는 "네, 예약 취소를
  도와드릴게요"처럼 짧게. 그 외에는 false.
- "취소하면 다음에 다시 예약할 수 있죠?"처럼 취소를 이미 실행하라는 말이 아니라 가능 여부를 묻는 가정형 질문은
  wants_cancel=false 로 두고, category=pet_general 또는 other 로 짧게 답한다.

[wants_new_booking] — 신규(추가) 예약
- "그냥 바로 예약할래 / 새로 예약 잡고 싶어 / 또(추가로) 예약하고 싶어" 처럼 기존 예약 '변경'이 아니라
  '새 예약'을 잡으려 하면 wants_new_booking=true. (기존 예약 시간 변경/앞당김은 wants_rebooking.)
  assistant_reply는 비워도 된다(코드가 확인 문구를 채운다). 그 외에는 false.

[asks_schedule_list] — 예약 내역 보기
- "내 예약 내역 보여줘 / 지금까지 예약한 거 알려줘 / 예약 목록 보고 싶어" 처럼 본인 예약 '목록/기록'을
  보려 하면 asks_schedule_list=true. (특정 한 건의 '예약 시각'을 묻는 건 asks_appointment_time.)
  assistant_reply는 비워도 된다(코드가 채운다). 그 외에는 false.

[asks_prep_instructions] — 내원 전 준비사항
- "내원 전에 뭐 준비해 / 준비사항 다시 알려줘 / 금식해야 해?" 처럼 진료 전 준비사항을 다시 묻면
  asks_prep_instructions=true. assistant_reply는 비워도 된다. 그 외에는 false.

[asks_vet_info] — 병원 인물(담당 수의사) 확인
- "담당 수의사 누구야 / 누가 진료해 / 어떤 선생님이야 / 누구 의사지 / 의사 누구지" 처럼 이번 예약을
  맡은 수의사가 누구인지 묻거나, "그 의사 친절해? / 원장님이야? / 잘 봐? / 실력 괜찮아?" 처럼 담당 수의사에
  대한 평가·인상을 물으면 asks_vet_info=true. (병원 위치·시간 등 행정 질문은 hospital_info와 구분.)
  assistant_reply는 비워도 된다(코드가 실제 이름·일반 안내를 채운다). 그 외에는 false.

[사진이 없을 때]
- "사진 못 찍었어 / 사진이 없어" 처럼 사진이 없다고 하면 차단하지 말고,
  "사진이 없어도 괜찮아요. 보이는 증상이나 상태를 글로 설명해 주세요."처럼 답하고 필요한 정보를 되묻는다.
- 진단·처방·약 용량·병명 추정은 절대 하지 않는다.
- 수술 후 회복 관리(넥카라 착용 여부, 산책·목욕 시점, 실밥·상처 관리 등)를 물으면 단정적 치료
  지시를 내리지 말고, "퇴원 시 받은 안내가 있다면 그 지시를 우선 따라 주세요"로 안내한 뒤, 지금 상처를
  핥거나 자꾸 건드리는 모습이 있으면 그 상태도 알려달라고 덧붙인다. ('꼭 해라/하지 마라' 단정 금지)
- 병원 정보(위치·시간·전화) 질문이면 "병원 정보는 바로 확인해 알려드릴게요"처럼 자연스럽게(가상의
  '담당자'를 언급하지 말 것 — "안내 담당이", "담당이 이어서" 같은 표현 금지).
- 무슨 말인지 모호하면 단정하지 말고, "무엇을 도와드릴까요? 아이 상태를 알려주시려는 걸까요,
  예약을 바꾸시려는 걸까요?"처럼 보호자에게 의도를 되묻는다(엉뚱한 차단 멘트 금지).
  ※ '경과 보고' 같은 딱딱한 용어는 보호자에게 쓰지 말 것 — "아이 상태", "상태 알려주기"로.
- 사진·영상이 첨부됐고 아래 [이미지 소견]이 있으면, 그 소견을 자연스럽게 언급하며 공감한다
  (예: "보내주신 사진 보니 ~"). 진단 단정은 금지, 보이는 것만 부드럽게 짚는다.
- [이미지 소견]에 'relevant=false'(증상과 무관해 보임)라고 돼 있으면, 단정하지 말고
  "혹시 이 사진이 OO 상태와 관련된 게 맞을까요? 맞다면 상태가 보이는 사진으로 한 번 더 보내주세요"처럼
  되묻는다(이 경우 사진은 아직 저장되지 않는다 — 보호자가 다시 보내면 그때 남긴다).

[reason]
- 분류 판단 이유(디버깅용, 짧게). 보호자에게 보이지 않는다.

[confidence]
- 0.0~1.0 사이 실수. 이 분류가 얼마나 확실한지.
- 명확한 구토·발작 → 0.95 이상. 애매한 발화("좀 이상한 것 같아요") → 0.5~0.7.
- 0.5 미만은 쓰지 않는다.

[출력 규칙]
- JSON 객체 하나만 출력한다.
- Markdown 코드블록(```)을 쓰지 않는다.
- JSON 밖에 어떤 설명 문장도 쓰지 않는다.

출력 형식:
{"is_followup": true, "category": "symptom_change", "severity_hint": "worse",
 "summary_delta": "오늘 구토를 3회 추가로 함.",
 "assistant_reply": "오늘 구토가 세 번 더 있었군요. 혈변이 보이는지도 함께 살펴봐 주세요.",
 "reply_kind": "reflect_ask", "asked_fields": ["혈변"],
 "reason": "예약 후 증상 변화 보고.",
 "wants_rebooking": false, "confidence": 0.95}
"""


def _format_history(history: list[dict] | None, n: int = 6) -> str:
    if not history:
        return "(없음)"
    recent = history[-n:]
    return "\n".join(f"{m.get('role')}: {m.get('content')}" for m in recent)


# ── P0: 직전 봇 질문 ↔ 짧은 답변 연결 (맥락 유지) ─────────────────────────────
# 직전 assistant 발화가 '질문'인지 판별하는 표지. 짧은 답변을 그 질문의 답으로 잇는다.
_QUESTION_MARKERS = (
    "?", "？", "나요", "까요", "ㄹ까요", "을까요", "으세요", "보이나요",
    "있나요", "있는지", "알려주세요", "살펴봐 주세요", "살펴봐주세요",
)
# 짧은 긍정/부정/애매 답변 표지. (순서: 애매 → 부정 → 긍정 — 더 구체적인 것 먼저)
_SHORT_AMBIG = ("모르겠", "애매", "확실하진 않", "잘 못", "글쎄", "그런 것 같기도")
_SHORT_NEG = ("아니", "아뇨", "없어요", "별로", "아직은", "안 해", "안해", "안 그래", "그러진 않", "전혀")
_SHORT_AFFIRM = ("응", "네", "넵", "어 ", "맞아", "그래", "그랬어요", "했어요", "있어요",
                 "보여요", "그러네요", "그런 것 같", "계속")


def last_assistant_question(history: list[dict] | None) -> str:
    """가장 최근 assistant 발화가 '질문'이면 그 텍스트를, 아니면 ''."""
    for m in reversed(history or []):
        if m.get("role") == "assistant":
            text = (m.get("content") or "").strip()
            return text if any(k in text for k in _QUESTION_MARKERS) else ""
    return ""


# P1: '사진 후속' 발화 — 이번 턴 첨부가 없어도 직전 사진 소견을 가리키는 표현.
_PHOTO_FOLLOWUP_HINTS = (
    "방금 보낸 사진", "방금 사진", "방금 그 사진", "사진 어때", "사진에", "사진 보니", "사진 결과",
    "사진 다시", "사진 분석", "사진 봐", "사진 확인", "사진 좀", "사진 보고", "사진상", "사진 문제", "사진 속",
    "아까 보낸", "아까 사진", "아까 그", "그 사진", "저 사진",
    "저거", "저게", "저 부분", "저 부위", "저기", "그 부분", "그 부위",
    "같은 부위", "같은 데", "더 빨개", "더 빨갛", "커진 것 같", "부은 것 같", "갑자기 생",
)


def is_photo_followup(message: str | None) -> bool:
    """이번 발화가 '직전 사진'을 가리키는 후속 질문인지(키워드 힌트). 최근 사진 소견이 있을 때만 의미가 있다."""
    t = message or ""
    return any(k in t for k in _PHOTO_FOLLOWUP_HINTS)


def short_answer_kind(message: str | None) -> str:
    """짧은 발화가 직전 질문에 대한 (affirmative|negative|ambiguous) 답변인지. 아니면 ''.

    너무 길거나(새 요청 가능성), 스스로 질문이거나 '예약' 의도를 담으면 적용하지 않는다
    (그 경우는 기존 분기가 처리). 키워드만으로 단정하지 않고 '짧은 답변'일 때만 잡는다.
    """
    t = " ".join((message or "").strip().split())
    if not t or len(t) > 18:
        return ""
    if "?" in t or "？" in t or "예약" in t:
        return ""
    if any(k in t for k in _SHORT_AMBIG):
        return "ambiguous"
    if any(k in t for k in _SHORT_NEG):
        return "negative"
    if any(k in t for k in _SHORT_AFFIRM):
        return "affirmative"
    return ""


def _format_vision(vision_findings: str | None, vision_relevant) -> str:
    """첨부 이미지/영상의 VLM 소견을 프롬프트 블록으로. 없으면 '(없음)'."""
    if not vision_findings and vision_relevant is None:
        return "(없음)"
    rel = "" if vision_relevant is None else f"relevant={'true' if vision_relevant else 'false'} / "
    return f"{rel}{vision_findings or '소견 없음'}"


def build_classification_prompt(
    *,
    pet_info: dict | None,
    followup_summary: str | None,
    history: list[dict] | None,
    user_message: str,
    attachment_count: int = 0,
    vision_findings: str | None = None,
    vision_relevant: bool | None = None,
    last_reply_kind: str | None = None,
    asked_fields: list[str] | None = None,
    prev_question: str | None = None,
    last_media_summary: str | None = None,
) -> str:
    """분류용 최종 프롬프트 조립.

    last_reply_kind/asked_fields: 직전 답변 목적·이미 물은 항목 — 같은 목적/질문 반복을 피하는 데 쓴다.
    prev_question: 직전 봇 발화가 질문이고 이번 메시지가 짧은 답변이면, 그 질문 주제와 연결해
      해석하도록 안내하는 블록을 덧붙인다(맥락 유지 — '무엇을 도와드릴까요?' 폴백 방지).
    last_media_summary: 최근(직전) 사진/영상 소견 요약 — 이번 발화가 그 사진을 가리키면 참조하도록
      안내하는 블록을 덧붙인다(이미 받은 사진을 다시 요구하지 않게 한다).
    """
    prev_q_block = ""
    if prev_question and short_answer_kind(user_message):
        prev_q_block = (
            "[직전 봇 질문에 대한 짧은 답변]\n"
            f"직전 봇 질문: {prev_question}\n"
            f"사용자 답변: {user_message}\n"
            "이 메시지는 새 요청이 아니라 직전 질문에 대한 응답이다. 직전 질문의 주제와 연결해서 "
            "경과 여부와 답변을 판단하라. 직전 질문이 증상·상처·투약·식욕·배뇨 등 상태를 물은 것이면, "
            "짧은 긍정/부정도 그 항목에 대한 경과 정보로 보고 is_followup=true 로 두고, "
            "summary_delta에 '(항목): 있음/없음/모름'처럼 짧게 적는다. "
            "assistant_reply는 '무엇을 도와드릴까요?'가 아니라, 직전 질문 주제를 한 번 되짚고(예: "
            "\"핥는 모습이 있었군요\", \"진물은 아직 없군요\") 이어서 살펴볼 점 1개만 자연스럽게 말한다. "
            "의미가 불명확해도 직전 질문 주제 안에서 한 번만 확인하고, 절대 일반 안내로 도망가지 마라.\n\n"
        )
    media_block = ""
    if last_media_summary and not attachment_count and is_photo_followup(user_message):
        media_block = (
            "[최근 사진 소견]\n"
            f"직전 사진 소견: {last_media_summary}\n"
            "주의: 현재 사용자 메시지가 '방금 사진', '저거', '저 부분', '사진에 보이는', '아까 보낸 거'처럼 "
            "직전 사진을 가리킨다. 이미 받은 그 사진의 위 소견을 근거로 답하라. "
            "현재 턴에 첨부가 없어도 '사진이 없다 / 사진을 보내 달라'고 절대 말하지 마라. "
            "위 소견을 한 번 되짚고, 사용자가 더한 새 정보('갑자기 생김', '더 빨개짐', '같은 부위')는 "
            "반영하되 원인·진단은 단정하지 않는다. 이건 직전 사진 상태에 대한 경과이므로 is_followup=true 로 본다.\n\n"
        )
    return (
        f"{FOLLOWUP_SYSTEM}\n\n"
        f"[반려동물 정보]\n{pet_info or '(없음)'}\n\n"
        f"[이전 누적 경과 메모]\n{(followup_summary or '아직 없음')}\n\n"
        f"[최근 대화]\n{_format_history(history)}\n\n"
        f"[직전 답변 목적]\n{last_reply_kind or '(없음)'}\n"
        f"[이미 질문한 항목]\n{', '.join(asked_fields) if asked_fields else '(없음)'}\n\n"
        f"{prev_q_block}"
        f"{media_block}"
        f"[이번 보호자 메시지]\n{user_message}\n"
        f"[첨부 개수] {attachment_count}\n"
        f"[이미지 소견]\n{_format_vision(vision_findings, vision_relevant)}\n\n"
        "위 메시지를 위 규칙대로 분류해 JSON 하나만 출력해."
    )


# assistant_reply가 비거나 파싱 실패했을 때만 쓰는 안전 fallback 문구.
# (평상시엔 LLM이 만든 assistant_reply가 우선 — schema.ensure_safe_reply 참고)
REPLY_HOSPITAL_INFO = "병원 정보는 바로 확인해 알려드릴게요."
REPLY_PET_GENERAL = (
    "정확한 확인은 진료 때 수의사 선생님께 여쭤보는 게 안전해요. "
    "예약 전후로 달라지는 모습이 있는지 지켜봐 주세요."
)
# 관리방법 질문 fallback(LLM assistant_reply가 비었을 때만) — 무리 말 것 + 진료 때 전달.
REPLY_CARE_METHOD = (
    "무리해서 해주기보다는, 지금 아이가 불편해하는 모습이 있는지만 가볍게 확인해 주세요. "
    "신경 쓰이는 부분이 있으면 진료 때 함께 말씀해 주시면 돼요."
)
# 감정 표현 fallback — 공감 먼저, 단정 없이 안심.
REPLY_EMOTION_ACK = (
    "걱정되실 만한 상황이었겠어요. 지금 말씀만으로 원인을 단정하긴 어렵지만, "
    "더 달라지는 모습이 없으면 너무 불안해하지 않으셔도 괜찮아요."
)
# 모호한 입력 → 차단 멘트 대신 무엇을 원하는지 되묻는다(아래 quick_replies와 함께 노출).
REPLY_IRRELEVANT = (
    "무엇을 도와드릴까요? 아이 상태를 이어서 남기거나 예약 관련 도움을 받을 수 있어요."
)
# 모호할 때 함께 띄우는 의도 선택지(클릭하면 다음 턴에 해당 의도로 라우팅됨).
CONTINUE_STATUS_PILL = "상태 계속 알려주기"
REBOOK_ACTION_PILL = "예약 변경"
HOSPITAL_INFO_PILL = "병원 정보"
PREP_INSTRUCTIONS_PILL = "내원 준비사항"
VISIT_NOTE_SUMMARY_PILL = "진료 때 전달할 내용 정리하기"
CLARIFY_QUICK_REPLIES = [CONTINUE_STATUS_PILL, REBOOK_ACTION_PILL, "예약 내역", HOSPITAL_INFO_PILL]
# 저장 안내 fallback — assistant_reply가 비었을 때만 쓰며, 매번 같은 문장이 반복되지 않게
# 여러 변형을 두고 대화 길이(턴 수)로 결정론적으로 고른다(직전 봇 답변과 겹치면 다음 변형으로).
REPLY_SAVED_VARIANTS = (
    "말씀하신 변화가 이어지는지 살펴봐 주세요.",
    "추가로 달라지는 모습이 있으면 이어서 남겨 주세요.",
    "상태가 더 달라지면 그 변화도 함께 살펴봐 주세요.",
    "새로운 변화가 보이면 편하게 말씀해 주세요.",
)
# 사진·영상이 첨부돼서 (글이 경과로 안 잡혀도) 저장하는 경우의 fallback.
REPLY_SAVED_MEDIA_VARIANTS = (
    "사진·영상에서 보이는 변화가 이어지는지 살펴봐 주세요.",
    "보내주신 자료 확인했어요. 상태가 더 달라지면 사진으로 또 보여주세요.",
    "잘 받았어요. 이어서 변화가 보이면 사진이나 글로 남겨 주세요.",
)


def _last_bot_reply(history: list[dict] | None) -> str:
    """직전 봇(assistant) 답변 텍스트 — 반복 회피용(reception._prev_was_vet_intro와 같은 패턴)."""
    for m in reversed(history or []):
        if m.get("role") == "assistant":
            return (m.get("content") or "").strip()
    return ""


def pick_saved_reply(is_followup: bool, history: list[dict] | None) -> str:
    """저장 안내 fallback 한 줄을 결정론적으로 고른다(랜덤 X).

    대화 길이(턴 수)로 변형을 고르고, 직전 봇 답변과 똑같으면 다음 변형으로 한 칸 민다.
    """
    variants = REPLY_SAVED_VARIANTS if is_followup else REPLY_SAVED_MEDIA_VARIANTS
    idx = len(history or []) % len(variants)
    reply = variants[idx]
    if reply == _last_bot_reply(history):
        reply = variants[(idx + 1) % len(variants)]
    return reply
# 사진이 증상과 무관해 보여(잘못 보낸 듯) 저장하지 않고 한 번 더 확인하는 응답.
REPLY_CONFIRM_PHOTO = (
    "보내주신 사진이 아이 상태와 관련된 게 맞을까요? "
    "혹시 다른 사진을 보내려던 거면, 상태가 보이는 사진으로 한 번 더 보내주세요."
)
# 재예약(예약 시간 변경/앞당김) — pill 텍스트(결정론 트리거) + 응답.
REBOOK_PILL = "더 빠른 시간 찾기"
REPLY_REBOOK = "네, 가능한 빠른 예약 시간을 찾아볼게요. 잠시만 기다려 주세요!"
# 예약 변경 '방법 문의/막연한 요청'에 대한 안내 — 슬롯을 바로 찾지 않고 선택지를 제시한다.
# (현재 예약 시각은 호출부에서 앞에 붙인다. "현재 예약은 …이에요. " + 아래 문구)
REPLY_REBOOK_OPTIONS = (
    "예약 내역에서 직접 날짜를 변경하실 수도 있고, "
    "제가 가능한 다른 시간대를 찾아드릴 수도 있어요. 어떻게 도와드릴까요?"
)
REPLY_CANCEL = "예약을 취소하시려는 거군요. 아래에서 확인해 주세요."
# 취소 '문의/가정형'(가능 여부·정책)에 대한 안내 — 실제 취소를 실행하지 않고 정책만 알린다.
REPLY_CANCEL_POLICY = (
    "취소 가능 여부나 세부 정책은 병원마다 다를 수 있어요. "
    "앱에서 가능한 범위는 예약 화면에서 확인해 주세요."
)

# 신규(추가) 예약 — 확인 문구 + 선택 pill(프론트가 동작 가로챔/백엔드 이벤트).
#  · NEW_BOOKING_DIRECT_PILL  → 홈 '예약하기'(검진예약 모달)로 이동.
#  · NEW_BOOKING_TRIAGE_PILL  → 같은 챗에서 문진을 시작(start_inchat_triage 이벤트).
NEW_BOOKING_DIRECT_PILL = "새 예약하기"
NEW_BOOKING_TRIAGE_PILL = "문진 작성 후 예약하기"
REPLY_NEW_BOOKING_CONFIRM = (
    "정확한 증상을 알려주시면 더 빠르고 정확한 진료에 도움이 돼요. 그래도 바로 예약하시겠어요?"
)
START_TRIAGE_REPLY = (
    "어디가 불편한지 편하게 말씀해 주세요. 증상을 바탕으로 빠른 예약을 도와드릴게요."
)

# 예약 내역 보기 — pill 텍스트 + 응답(프론트가 예약 목록 카드를 렌더).
SCHEDULE_LIST_PILL = "예약 내역"
SCHEDULE_LIST_TAB_PILL = "예약 내역 탭에서 보기"
REPLY_SCHEDULE_LIST = "현재 예약을 정리해 드릴게요."
REPLY_SCHEDULE_LIST_EMPTY = "지금은 확정된 예약이 없어요. 예약을 도와드릴까요?"
# 내원 전 준비사항 — 응답(프론트가 저장된 준비사항 카드를 다시 렌더).
REPLY_PREP_INSTRUCTIONS = "내원 전 준비사항을 다시 안내드릴게요."

# 사진 속 동물이 등록된 반려동물과 종이 다를 때 — 잘못 보낸 사진일 수 있어 저장 전에 확인.
_SPECIES_KO = {"dog": "강아지", "cat": "고양이", "rabbit": "토끼"}

# 펫 등록 종 값이 DB에 한글/영어 섞여 있어(예: '고양이' vs 'cat') 표준 코드로 정규화해서 비교한다.
_SPECIES_ALIASES = {
    "dog": "dog", "강아지": "dog", "개": "dog", "멍멍이": "dog", "canine": "dog", "puppy": "dog",
    "cat": "cat", "고양이": "cat", "냥이": "cat", "야옹이": "cat", "feline": "cat", "kitten": "cat",
    "rabbit": "rabbit", "토끼": "rabbit", "bunny": "rabbit",
}


def canon_species(value: str | None) -> str:
    """종 값(한글/영어/변형)을 표준 코드(dog|cat|rabbit)로. 모르면 빈 문자열."""
    return _SPECIES_ALIASES.get((value or "").strip().lower(), "")


def pet_call(name: str | None) -> str:
    """반려동물 호칭 — 받침 있는 이름엔 친근형 '이'를 붙인다(군밤 → 군밤이, 뽀미 → 뽀미).

    결과는 항상 받침이 없어(…이/모음) 뒤 조사는 '는/가/를'로 통일된다.
    """
    n = (name or "아이").strip()
    ch = n[-1:]
    if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28:
        return n + "이"
    return n


def build_species_mismatch_reply(pet_name: str, pet_species: str, photo_species: str) -> str:
    pet_ko = _SPECIES_KO.get(pet_species, "등록된 동물")
    photo_ko = _SPECIES_KO.get(photo_species, "다른 동물")
    call = pet_call(pet_name)   # 군밤 → 군밤이 (뒤 조사는 항상 는/가)
    return (
        f"{call}는 {pet_ko}로 등록돼 있는데, 보내주신 사진 속 동물은 {photo_ko}처럼 보여요. "
        f"혹시 사진을 잘못 보내신 건 아닐까요? 맞다면 {call} 상태가 보이는 사진으로 다시 보내주세요."
    )
