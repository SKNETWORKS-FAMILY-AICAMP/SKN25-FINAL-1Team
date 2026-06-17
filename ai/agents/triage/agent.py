import json
import logging
import re

from ai.llm import (
    call_llm,
    call_llm_json,
    call_llm_structured,
)

logger = logging.getLogger(__name__)

from ai.agents.triage.prompts import (
    EXTRACT_FIELDS_PROMPT,
    QUESTION_PROMPT,
    FINAL_TRIAGE_PROMPT,
    CHAT_REPLY_PROMPT,
    OFF_TOPIC_PROMPT,
)

from ai.agents.triage.rules import (
    load_rules,
    select_next_question,
    find_question_for_field,
    get_field_schema,
    build_sections_guide,
    build_red_flag_guide,
    build_extract_schema,
)

# 문진 완료 안내 — 응급/일반 구분 없이 동일 문구 (보호자에게 경고문 안 보냄)
TRIAGE_COMPLETE_REPLY = "증상에 대해 자세히 말씀해 주셔서 감사합니다. 이제 예약을 도와드릴게요. 🐾"

from ai.agents.triage.scoring import (
    calculate_score,
    image_findings,
)

from ai.agents.triage.termination import (
    should_finish,
)


class TriageAgent:

    def __init__(self):

        self.rules = load_rules()

    # 질문 생성 결과(JSON) 파싱
    def _parse_question_json(self, raw: str) -> dict:
        text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(text)
            return {
                "question": data.get("question", "").strip(),
                "quick_replies": [str(x) for x in data.get("quick_replies", [])][:4],
            }
        except Exception:
            return {"question": raw.strip(), "quick_replies": []}

    # 한 턴 처리
    async def process_message(
        self,
        user_message: str,
        messages: list[dict],
        pet_info: dict,
        image_analysis: dict | None = None,
    ):

        # 직전 상태 복원
        prev = self._read_state(messages)

        # 이미지는 한 번 첨부되면 완료 요약까지 유지
        image_analysis = image_analysis or prev.get("image_analysis")

        # 정보 추출 (증분)
        extracted = await self._extract_fields(
            messages=messages,
            user_message=user_message,
            prev=prev,
        )

        # 대화 내용 질문 → 히스토리로 답변 (문진 상태 유지)
        if extracted.get("intent") == "recall":
            reply = await self._answer_from_history(messages, user_message)
            return self._side_reply(prev, reply)

        # 무관한 주제 → 가볍게 받고 증상으로 유도 (문진 상태 유지)
        if extracted.get("intent") == "off_topic":
            reply = await self._redirect_off_topic(user_message)
            return self._side_reply(prev, reply)

        section = extracted.get("section") or prev.get("section") or "GENERAL"

        fields = {
            **prev.get("fields", {}),
            **extracted.get("fields", {}),
        }

        observations = list(prev.get("observations", [])) + list(
            extracted.get("observations") or []
        )

        # red_flag는 한 번 켜지면 유지 (보충질문 턴에 풀리지 않게)
        red_flag = bool(extracted.get("red_flag", False)) or bool(prev.get("red_flag"))
        red_flag_chief = (
            extracted.get("red_flag_chief") or prev.get("red_flag_chief") or ""
        ).strip()

        asked = list(prev.get("asked_questions", []))
        question_count = prev.get("question_count", 0)

        # 응급도 채점
        score_result = calculate_score(
            rules=self.rules,
            section=section,
            fields=fields,
            red_flag=red_flag,
            image_analysis=image_analysis,
            gender=pet_info.get("gender"),
        )

        # 종료 판단
        finish = should_finish(
            rules=self.rules,
            section=section,
            fields=fields,
            red_flag=red_flag,
            question_count=question_count,
            score=score_result["score"],
        )

        next_question = (
            None
            if finish
            else select_next_question(self.rules, section, fields, asked)
        )

        # 진행/완료 상태 로그
        logger.info(
            "[triage] section=%s score=%s urgency=%s complete=%s q=%s",
            section,
            score_result["score"],
            score_result["urgency"],
            finish or next_question is None,
            question_count,
        )

        state = {
            "section": section,
            "fields": fields,
            "observations": observations,
            "asked_questions": asked,
            "question_count": question_count,
            "image_analysis": image_analysis,
        }

        # 응급 — 차트에 필요한 핵심정보만 짧게 보충 후 종료 (보호자에겐 응급 고지 안 함)
        if red_flag:

            state["red_flag"] = True
            state["red_flag_chief"] = red_flag_chief

            ef = self.rules.get("meta", {}).get("emergency_followup") or {}
            max_followups = ef.get("max_questions", 1)
            followup_count = prev.get("red_flag_followup_count", 0)

            missing = self._emergency_missing_fields(
                section, fields, red_flag_chief, observations
            )

            # 핵심정보가 비었고 보충 한도가 남았으면 한 가지만 더 묻는다
            if missing and followup_count < max_followups:

                target_q = find_question_for_field(self.rules, section, missing[0])

                if target_q is not None:

                    generated = await self._generate_question(
                        fields=fields,
                        question=target_q,
                        user_message=user_message,
                    )

                    asked.append(target_q.get("id"))
                    state["asked_questions"] = asked
                    state["red_flag_followup_count"] = followup_count + 1

                    return {
                        "section": section,
                        "fields": fields,
                        "red_flag": True,
                        "urgency": "RED",
                        "score": score_result["score"],
                        "is_complete": False,
                        "reply": generated["question"],
                        "quick_replies": generated["quick_replies"],
                        "state": state,
                    }

            # 핵심정보 충분/이미 보충함 → 요약 생성 후 종료 (차트 풍부화)
            summary = await self.finalize(
                messages=messages,
                pet_info=pet_info,
                vet_memo=None,
                image_analysis=image_analysis,
            )

            # CNN 소견을 의심질환에 병합 (일반 완료 경로와 동일)
            suspected = list(summary.get("suspected_conditions", []))
            _, image_suspected = image_findings(image_analysis)
            for name in image_suspected:
                if name not in suspected:
                    suspected.append(name)
            suspected = suspected[:3]  # 의심질환 최대 3개

            # 응급 주증상을 chief 맨 앞에 (상담 제목 우선순위)
            chief = list(summary.get("chief_complaints", []))
            if red_flag_chief and red_flag_chief not in chief:
                chief.insert(0, red_flag_chief)

            return {
                "section": section,
                "fields": fields,
                "red_flag": True,
                "urgency": "RED",
                "score": score_result["score"],
                "is_complete": True,
                "triage_summary": summary.get("triage_summary", ""),
                "chief_complaints": chief,
                "suspected_conditions": suspected,
                "reply": TRIAGE_COMPLETE_REPLY,
                "state": state,
            }

        # 문진 완료 → 요약/응급도 확정 → 스케줄 단계로
        if finish or next_question is None:

            summary = await self.finalize(
                messages=messages,
                pet_info=pet_info,
                vet_memo=None,
                image_analysis=image_analysis,
            )

            # CNN 소견을 의심질환에 병합
            suspected = list(summary.get("suspected_conditions", []))
            _, image_suspected = image_findings(image_analysis)
            for name in image_suspected:
                if name not in suspected:
                    suspected.append(name)
            suspected = suspected[:3]  # 의심질환 최대 3개

            return {
                "section": section,
                "fields": fields,
                "red_flag": False,
                "is_complete": True,
                "score": score_result["score"],
                "urgency": score_result["urgency"],
                "triage_summary": summary.get("triage_summary", ""),
                "chief_complaints": summary.get("chief_complaints", []),
                "suspected_conditions": suspected,
                "reply": TRIAGE_COMPLETE_REPLY,
                "state": state,
            }

        # 다음 질문 생성
        generated = await self._generate_question(
            fields=fields,
            question=next_question,
            user_message=user_message,
        )

        asked.append(next_question.get("id"))
        state["asked_questions"] = asked
        state["question_count"] = question_count + 1

        return {
            "section": section,
            "fields": fields,
            "red_flag": False,
            "is_complete": False,
            "score": score_result["score"],
            "urgency": score_result["urgency"],
            "reply": generated["question"],
            "quick_replies": generated["quick_replies"],
            "state": state,
        }

    # 응급 보충질문 대상 = 핵심필드 중 '이 섹션에 있고 + 아직 비어있는' 것
    def _emergency_missing_fields(
        self,
        section: str,
        fields: dict,
        red_flag_chief: str,
        observations: list,
    ):

        ef = self.rules.get("meta", {}).get("emergency_followup") or {}
        core = ef.get("core_fields", [])
        schema = get_field_schema(self.rules, section)

        missing = [f for f in core if f in schema and f not in fields]

        # 의식상태를 이미 말한 경우(레드플래그 주증상/관찰) 중복 질문 방지
        if "consciousness_level" in missing and self._consciousness_known(
            red_flag_chief, observations
        ):
            missing.remove("consciousness_level")

        return missing

    # 의식상태를 보호자가 이미 언급했는지
    @staticmethod
    def _consciousness_known(
        red_flag_chief: str,
        observations: list,
    ):

        blob = (red_flag_chief or "") + " " + " ".join(observations or [])
        return any(k in blob for k in ("의식", "기절", "무반응", "반응없", "반응 없"))

    # 최종 요약
    async def finalize(
        self,
        messages: list[dict],
        pet_info: dict,
        vet_memo: str | None,
        image_analysis: dict | None,
    ):

        prompt = FINAL_TRIAGE_PROMPT.format(
            pet_info=json.dumps(pet_info, ensure_ascii=False, default=str),
            vet_memo=vet_memo or "",
            image_analysis=json.dumps(image_analysis or {}, ensure_ascii=False, default=str),
            messages=json.dumps(messages, ensure_ascii=False, default=str),
        )

        return await call_llm_json(
            prompt=prompt,
            temperature=0.2,
        )

    # 직전 상태(meta) 복원
    def _read_state(
        self,
        messages: list,
    ):

        for msg in reversed(messages or []):

            if not isinstance(msg, dict):
                continue

            meta = msg.get("meta")

            if meta and "fields" in meta:
                return meta

        return {}

    # 직전에 챗봇이 한 질문
    def _last_question(
        self,
        messages: list,
    ):

        for msg in reversed(messages or []):

            if isinstance(msg, dict) and msg.get("role") == "assistant":
                return msg.get("content", "")

        return ""

    # 정보 추출 호출
    async def _extract_fields(
        self,
        messages: list,
        user_message: str,
        prev: dict,
    ):

        prompt = EXTRACT_FIELDS_PROMPT.format(
            sections_guide=build_sections_guide(self.rules),
            red_flag_guide=build_red_flag_guide(self.rules),
            state=json.dumps(prev, ensure_ascii=False),
            current_question=self._last_question(messages),
            user_message=user_message,
        )

        data = await call_llm_structured(
            prompt=prompt,
            schema=build_extract_schema(self.rules),
            temperature=0,
        )

        # 모르는 필드(null) 제거
        fields = data.get("fields") or {}
        data["fields"] = {k: v for k, v in fields.items() if v is not None}

        return data

    # 질문 생성 호출 (어떻게 물을지)
    async def _generate_question(
        self,
        fields: dict,
        question: dict,
        user_message: str,
    ):

        # 이미 확인된 필드는 제외 — 묶음 질문이 답한 항목을 다시 묻지 않게
        remaining = [f for f in question.get("extract_fields", []) if f not in fields]

        prompt = QUESTION_PROMPT.format(
            state=json.dumps(fields, ensure_ascii=False),
            user_message=user_message,
            target_fields= remaining[0] if remaining else "",
            goal=question.get("goal", ""),
            example_questions="\n".join(question.get("example_questions", [])),
        )

        raw = await call_llm(prompt=prompt, temperature=0.5)
        return self._parse_question_json(raw)

    # 문진 진행을 멈추지 않는 보조 답변 (recall/off_topic)
    def _side_reply(
        self,
        prev: dict,
        reply: str,
    ):

        return {
            "section": prev.get("section", "GENERAL"),
            "fields": prev.get("fields", {}),
            "red_flag": False,
            "is_complete": False,
            "reply": reply,
            "state": prev,
        }

    # 대화 히스토리 기반 답변
    async def _answer_from_history(
        self,
        messages: list,
        user_message: str,
    ):

        prompt = CHAT_REPLY_PROMPT.format(
            messages=json.dumps(messages, ensure_ascii=False, default=str),
            user_message=user_message,
        )

        return await call_llm(
            prompt=prompt,
            temperature=0.5,
        )

    # 무관한 주제 → 증상으로 유도
    async def _redirect_off_topic(
        self,
        user_message: str,
    ):

        prompt = OFF_TOPIC_PROMPT.format(
            user_message=user_message,
        )

        return await call_llm(
            prompt=prompt,
            temperature=0.5,
        )
