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
    build_sections_guide,
    build_red_flag_guide,
    build_extract_schema,
    get_red_flag_message,
)

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

        red_flag = bool(extracted.get("red_flag", False))
        red_flag_chief = (extracted.get("red_flag_chief") or "").strip()

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

        # 응급 종료
        if red_flag:
            return {
                "section": section,
                "fields": fields,
                "red_flag": True,
                "urgency": "RED",
                "score": score_result["score"],
                "is_complete": True,
                "chief_complaints": [red_flag_chief] if red_flag_chief else [],
                "reply": get_red_flag_message(self.rules),
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
                "reply": "문진이 완료되었습니다.",
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
            target_fields=", ".join(remaining),
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
