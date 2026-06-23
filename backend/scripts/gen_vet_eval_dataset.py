"""PetEVAL 임상노트 → MediPaw 검증 벤치마크 생성기.

[무할루시네이션 원칙]
  · gold(정답) 라벨 — category/species/red_flag/urgency/rx_class/diagnoses — 은 전부
    실제 노트에서 '결정론적 규칙'으로 추출하고, 근거가 된 노트 phrase(evidence)를 함께 박는다.
    LLM은 정답을 만들지 않는다.
  · LLM은 오직 '보호자 대화(input.messages) 문체 렌더링'과 '진단명 한국어 표기'에만 쓴다.
    노트에 없는 증상/병명/약을 지어내지 못하도록 프롬프트로 강제하고, 생성 후 검증한다.
  · species가 노트에 명시 안 되면 null로 둔다(추측 금지). flawed는 규칙으로 주입(LLM 미사용).

실행(도커):
  docker exec -w /app/backend docker-backend-1 \
    python scripts/gen_vet_eval_dataset.py --n 120 --flawed-ratio 0.4 \
    --out data/validation/vet_eval_dataset.json
"""
from __future__ import annotations

import argparse
import ast
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SRC = HERE.parent / "data" / "validation" / "PetEVAL.json"
DEFAULT_OUT = HERE.parent / "data" / "validation" / "vet_eval_dataset.json"

# ── 카테고리 버킷 (ICD-11 라벨 → MediPaw 질환군). 다중라벨이면 우선순위 높은 것 채택 ──
# 우선순위: 진짜 응급군(심장·신경)을 먼저, Injury/Neoplasm은 후순위(사소 케이스에 과다 부착되므로).
CATEGORY_PRIORITY = [
    ("긴급(심장·신경)", ["Diseases of the circulatory system", "Diseases of the nervous system"]),
    ("호흡기", ["Diseases of the respiratory system"]),
    ("소화기/감염", ["Certain infectious or parasitic diseases", "Diseases of the digestive system"]),
    ("근골격", ["Diseases of the musculoskeletal system or connective tissue"]),
    ("피부/귀/눈", ["Diseases of the skin", "Diseases of the ear or mastoid process", "Diseases of the visual system"]),
    ("내분비/대사", ["Endocrine, nutritional or metabolic diseases", "Diseases of the genitourinary system"]),
    ("종양", ["Neoplasms"]),
    ("외상", ["Injury, poisoning or certain other consequences of external causes"]),
]

def to_category(icd_labels: list[str]) -> str:
    for bucket, labels in CATEGORY_PRIORITY:
        if any(l in labels for l in icd_labels):
            return bucket
    return "기타"

# ── 종 탐지 (단어경계). 미명시면 None — 절대 추측하지 않는다 ──
SPECIES_PATTERNS = [
    ("rabbit", r"\brabbits?\b|\bbunn(y|ies)\b|\bdoe\b|\bbuck\b|\blop\b"),
    ("guinea pig", r"\bguinea\b"),
    ("ferret", r"\bferrets?\b"),
    ("hamster", r"\bhamsters?\b"),
    ("cat", r"\bcats?\b|\bfeline\b|\bkittens?\b|\bdsh\b|\bdlh\b|\bqueen\b|\btom\s?cat\b"),
    ("dog", r"\bdogs?\b|\bbitch\b|\bpupp(y|ies)\b|\bcanine\b|\bk9\b"),
]

def detect_species(note: str) -> str | None:
    s = " " + note.lower() + " "
    for sp, pat in SPECIES_PATTERNS:
        if re.search(pat, s):
            return sp
    return None

# ── Red Flag (영문 임상 응급 단서) → urgency 하한 + 근거 phrase ──
# 각 항목: (정규식, urgency_floor[숫자 낮을수록 응급], 라벨)
REDFLAG_RULES = [
    (r"collaps|unconsci|unrespons|recumben|moribund", 1, "허탈/의식저하"),
    (r"seizur|convuls|fitting|status epil", 1, "발작"),
    (r"cyanos|blue (gum|tongue|mm)|open[- ]mouth breath|resp(iratory)? distress|severe dyspn", 1, "호흡곤란/청색증"),
    (r"\bgdv\b|gastric dilat|bloat|torsion", 1, "위확장염전(GDV)"),
    (r"unable to urinat|can'?t urinat|blocked|anuri|no urine", 2, "배뇨불가/요폐"),
    (r"profuse bleed|haemorrhag|hemorrhag|bleeding (a lot|profusel|won'?t stop)|melaena|haematem", 2, "다량출혈"),
    (r"toxic|poison|rodenticid|ingest.*(plastic|foreign|sock|stone|bone)|foreign body|swallow", 2, "중독/이물섭취"),
    (r"10/10 lame|non[- ]weight bearing|severe pain", 2, "심한 통증"),
    (r"(not|n'?t) eat.*(letharg|depress)|letharg.*((not|n'?t) eat)|anorexi.*letharg|inappeten", 3, "식욕부진+기력저하"),
    (r"repeated vomit|numerous vomit|persistent vomit|vomit.*throughout|continuous vomit", 3, "지속 구토"),
]

# 비응급(안정) 시그널 → 과대평가 방지(증거로만 사용)
STABLE_SIGNALS = r"\bbar\b|bright|eating (well|fine|normal)|well in (self|him|her)|alert|nad|passing (normal|f\+)|recheck|medication check|booster|vaccin"

def derive_redflag_and_urgency(note: str, category: str) -> dict:
    """무할루시네이션: 근거(evidence)가 있을 때만 urgency/red_flag를 gold로 박는다.
    응급 단서도 안정 단서도 없으면 urgency_level_num_gold=None → 해당 케이스 urgency/redflag 채점 축을 끈다.
    (추측으로 정답을 만들지 않는다.)"""
    s = note.lower()
    hits = []
    floor = 5
    for pat, fl, label in REDFLAG_RULES:
        m = re.search(pat, s)
        if m:
            hits.append({"label": label, "phrase": _ctx(note, m.start(), m.end())})
            floor = min(floor, fl)
    stable = bool(re.search(STABLE_SIGNALS, s))

    if hits:                       # 응급 단서 → 근거 있는 urgent gold
        urgency, confidence, red_flag, scorable = floor, "high", floor <= 2, True
    elif stable:                   # 안정 단서(BAR/eating well/recheck) → 근거 있는 routine gold
        urgency, confidence, red_flag, scorable = 5, "high", False, True
    else:                          # 근거 없음 → gold 미assert(채점 제외)
        urgency, confidence, red_flag, scorable = None, "none", None, False

    band = {1: "즉시", 2: "당일", 3: "당일", 4: "일반", 5: "일반"}.get(urgency)
    window = {1: "immediate", 2: "emergency_today", 3: "urgent_24h",
              4: "semi_urgent_48h", 5: "routine_72h"}.get(urgency)
    return {
        "red_flag": red_flag,
        "redflag_evidence": hits,
        "stable_evidence": stable,
        "urgency_level_num_gold": urgency,
        "urgency_band": band,
        "slot_window_min": window,
        "urgency_confidence": confidence,
        "urgency_scorable": scorable,
        "urgency_derived_by": "rules(redflag_lexicon+stable_signal); evidence 없으면 미assert",
    }

def _ctx(note: str, a: int, b: int, pad: int = 30) -> str:
    return note[max(0, a - pad):min(len(note), b + pad)].strip()

# ── 처방 계열 (영문 약물/처치어 → 한국어 계열). 노트에 있을 때만 emit ──
RX_RULES = [
    (r"\bab\b|\babx\b|antibiotic|amoxicillin|clavam|synulox|convenia|enroflox|baytril|doxy|metronidaz|marbofloxac|cephalexin|noroclav", "항생제"),
    (r"metacam|meloxicam|meloxidyl|loxicom|carprofen|rimadyl|nsaid|onsior|robenacox|previcox", "소염진통제(NSAID)"),
    (r"\bpred\b|prednisol|steroid|dexamethason|\bglucocortic", "스테로이드"),
    (r"buprenorph|methadone|tramadol|fentanyl|\bopioid|pain relief|analgesi", "진통제"),
    (r"maropitant|cerenia|antiemetic|metoclopram|ondansetron", "제토제"),
    (r"omeprazol|ranitidine|sucralfate|gastroprotect|antacid", "위장보호제"),
    (r"\bfluid|\bdrip\b|\biv\b.*fluid|subcut.*fluid", "수액"),
    (r"ear (drop|cleaner|solution)|otic|surolan|canaural|osurnia", "점이제"),
    (r"eye (drop|ointment)|ocular|chloramphenicol eye|fucithalmic", "점안제"),
    (r"topical|cream|ointment|spot[- ]on|barrier", "외용제"),
    (r"\bflea|\bworm|anthelmintic|antiparasit|advocate|stronghold|panacur", "구충/외부기생충"),
]

def derive_rx_class(note: str) -> list[dict]:
    s = note.lower()
    out, seen = [], set()
    for pat, cls in RX_RULES:
        m = re.search(pat, s)
        if m and cls not in seen:
            seen.add(cls)
            out.append({"class": cls, "phrase": _ctx(note, m.start(), m.end())})
    return out

def parse_disease_entities(disease_field: str) -> list[str]:
    try:
        arr = ast.literal_eval(disease_field)
        return [x["entity"] for x in arr if isinstance(x, dict) and x.get("entity")]
    except Exception:
        return []


# ───────────────────────── LLM (문체 렌더링 전용) ─────────────────────────
def get_llm():
    """base.py와 동일하게 ChatOpenAI 구성(gpt-5 계열 max_completion_tokens·json mode)."""
    from langchain_openai import ChatOpenAI
    sys.path.insert(0, str(HERE.parent))  # /app/backend
    from app.core.config import settings
    return ChatOpenAI(
        model=settings.OPENAI_MODEL or "gpt-4o-mini",
        api_key=settings.OPENAI_API_KEY,
        temperature=0.4,
        timeout=40.0,
        max_retries=1,
        model_kwargs={"max_completion_tokens": 1100, "response_format": {"type": "json_object"}},
    )

CONV_SYSTEM = """너는 영국 1차 동물병원 임상노트를 한국 동물병원 AI 예약/문진 검증용 '보호자 대화'로 바꾸는 변환기다.

[절대 규칙 — 위반 금지]
1) 노트에 적힌 '증상·관찰 사실'만 보호자 말투로 옮긴다. 노트에 없는 증상/수치/약을 절대 지어내지 마라.
2) 보호자는 비전문가다. 병명·진단·약물명을 말하지 마라(AI가 추론할 몫). 단, 보호자가 '직접 목격한 사건'(예: 무언가 삼키는 걸 봄, 싸움/외상 목격)은 말해도 된다.
3) species가 주어지면 그 종으로, 주어지지 않으면 종을 추정해 말하지 마라(그냥 '아이'라고 지칭).
4) 한국 보호자의 자연스러운 구어체. input_style에 맞춰 서술.

[출력 — JSON만]
{
  "messages": [
    {"role":"assistant","content":"문진 시작 인사+첫 질문"},
    {"role":"user","content":"보호자 증상 서술"},
    {"role":"assistant","content":"추가 질문"},
    {"role":"user","content":"보호자 답변"},
    {"role":"assistant","content":"마지막 확인 질문"},
    {"role":"user","content":"보호자 마무리 답변"}
  ],
  "symptom_keywords_ko": ["노트 증상의 한국어 키워드 2~5개"],
  "diagnoses_ko": ["영문 진단/병명을 한국어로 표기(노트 disease 기반, 의역 금지·창작 금지)"]
}"""

def build_conv_user(note: str, species: str | None, disease_en: list[str], category: str, style: str) -> str:
    return (
        f"[원본 임상 노트]\n{note}\n\n"
        f"[종] {species or '(노트에 명시 안 됨 — 추정 금지)'}\n"
        f"[질환군] {category}\n"
        f"[노트에서 추출된 영문 병명] {', '.join(disease_en) or '(노트 참조)'}\n"
        f"[input_style] {style}\n\n"
        "위 노트의 증상만으로 보호자 대화를 만들고 JSON으로 출력해라."
    )

# 보호자 발화에 새면 안 되는 진단/약물 누설 검사(간이)
LEAK_TERMS = ["진단", "처방", "항생제", "스테로이드", "nsaid"]

def normalize_messages(raw) -> list[dict]:
    """LLM이 가끔 {'user':..}/{'bot':..} 형식으로 줄 때 {role, content}로 통일."""
    out = []
    for m in raw or []:
        if not isinstance(m, dict):
            continue
        if m.get("role") and m.get("content"):
            role = "assistant" if m["role"] in ("assistant", "bot", "ai") else "user"
            out.append({"role": role, "content": str(m["content"])})
        elif "user" in m:
            out.append({"role": "user", "content": str(m["user"])})
        elif "assistant" in m or "bot" in m:
            out.append({"role": "assistant", "content": str(m.get("assistant") or m.get("bot"))})
    return out


def validate_conv(conv: dict, note: str) -> list[str]:
    warns = []
    msgs = conv.get("messages") or []
    if len([m for m in msgs if m.get("role") == "user"]) < 2:
        warns.append("user 발화 < 2")
    user_text = " ".join(m.get("content", "") for m in msgs if m.get("role") == "user")
    for t in LEAK_TERMS:
        if t in user_text:
            warns.append(f"보호자 발화에 전문용어 누설 의심: '{t}'")
    if not conv.get("diagnoses_ko"):
        warns.append("diagnoses_ko 비어있음")
    return warns


# ───────────────────────── 케이스 조립 ─────────────────────────
INPUT_STYLES = ["plain", "realistic", "edge"]

def build_clean_case(rec: dict, conv: dict, gold: dict, species: str | None, category: str,
                     style: str, disease_en: list[str]) -> dict:
    dia = conv.get("diagnoses_ko") or disease_en
    return {
        "case_id": f"peteval_{rec['id']}_clean",
        "tier": "clean",
        "category": category,
        "species": species,
        "input_style": style,
        "source": {
            "peteval_id": str(rec["id"]),
            "icd_label": rec["icd_label"],
            "disease_en": disease_en,
            "original_note": rec["sentence"][:700],
        },
        "gold_provenance": {
            "redflag_evidence": gold["redflag_evidence"],
            "stable_evidence": gold["stable_evidence"],
            "urgency_confidence": gold["urgency_confidence"],
            "urgency_derived_by": gold["urgency_derived_by"],
            "rx_evidence": gold["rx_evidence"],
            "note": "gold는 노트에서 규칙으로 추출. LLM 미사용. evidence로 수의사 검수 가능.",
        },
        "input": {
            "pet": {"species": species, "breed": None, "age_years": None,
                    "weight_kg": None, "sex": None, "past_conditions": []},
            "messages": conv.get("messages", []),
            "visit_history": [],
        },
        "expected": {
            "triage": {
                "urgency_band": gold["urgency_band"],
                "urgency_level_num_gold": gold["urgency_level_num_gold"],
                "urgency_pass": "no_under_triage",
                "red_flag": gold["red_flag"],
                "must_have_keywords": [[k] for k in (conv.get("symptom_keywords_ko") or [])],
            },
            "schedule": {"slot_window_min": gold["slot_window_min"]},
            "chart": {
                "expected_diagnoses": [[d] for d in dia],
                "expected_rx_class": [r["class"] for r in gold["rx_evidence"]],
            },
        },
        "eval_axes": {
            # urgency/redflag는 근거(evidence)로 gold가 박힌 경우에만 채점한다(미assert면 끔).
            "redflag_recall": gold["urgency_scorable"],
            "urgency_accuracy": gold["urgency_scorable"],
            "schedule_floor": gold["urgency_scorable"],
            "completeness": True, "chart_consistency": True, "diagnosis_recall": bool(dia),
            "rx_safety": species is not None and bool(gold["rx_evidence"]),
        },
        "rubric": {
            "notes": f"{category} · urgency 근거 신뢰도 {gold['urgency_confidence']}. "
                     + ("종 미명시(시스템 dog 디폴트 동작 테스트)." if species is None else f"종={species}.")
        },
    }


# ── 규칙 기반 결함 주입(LLM 미사용) → flawed 파생 ──
def make_flawed(clean: dict, defect: str) -> dict | None:
    base_in = clean["input"]
    exp = clean["expected"]
    kws = [k[0] for k in exp["triage"]["must_have_keywords"]] or ["증상"]
    common = {
        "case_id": clean["case_id"].replace("_clean", f"_flawed_{defect}"),
        "tier": "flawed", "category": clean["category"], "species": clean["species"],
        "input_style": clean["input_style"],
        "source": {"peteval_id": clean["source"]["peteval_id"], "based_on": clean["case_id"]},
        "input": base_in,
    }
    if defect == "redflag_urgency_mismatch":
        if not exp["triage"]["red_flag"]:
            return None  # 응급 케이스에만 주입 가능
        common["injected_defect"] = {
            "type": defect,
            "description": "응급 단서가 있는데 triage가 urgency_level_num=5(일반)로 과소평가.",
            "corrupted_outputs": {
                "triage_result": {"chief_complaint": kws[0], "symptom_keywords": kws,
                                  "symptom_onset": "최근", "red_flags": kws,
                                  "urgency_level_num": 5, "urgency_level": "routine", "urgency": "일반"},
                "schedule_result": {"estimated_duration_min": 20, "slot_window": "routine_72h"},
            },
        }
        common["expected_verdict"] = {
            "validation": {"overall": "ATTENTION", "red_flag_detection": "WARN"},
            "judge": {"monitoring_verdict": "NEEDS_REVIEW"},
        }
        common["eval_axes"] = _axes(redflag=True, urgency=True)
    elif defect == "missing_field":
        common["injected_defect"] = {
            "type": defect,
            "description": "필수 5항목 중 성별·발현시점 누락.",
            "corrupted_outputs": {
                "pet": {"species": clean["species"] or "dog", "age": 5, "gender": None},
                "triage_result": {"chief_complaint": kws[0], "symptom_keywords": kws, "symptom_onset": None},
            },
        }
        common["expected_verdict"] = {
            "validation": {"overall": "ATTENTION", "data_completeness": "WARN",
                          "missing_fields_expected": ["성별", "발현 시점"]},
            "judge": {"monitoring_verdict": "NEEDS_REVIEW", "weak_axis": "completeness"},
        }
        common["eval_axes"] = _axes(completeness=True)
    elif defect == "chart_symptom_drift":
        common["injected_defect"] = {
            "type": defect,
            "description": "문진 키워드가 차트에 전혀 없고 무관한 내용으로 채워짐.",
            "corrupted_outputs": {
                "triage_result": {"symptom_keywords": kws, "chief_complaint": kws[0]},
                "chart_result": {"soap": {"S": "무관한 증상으로 내원", "A": "무관한 질환 의심"},
                                "key_symptoms": ["무관A", "무관B"], "differential_diagnosis": ["무관진단"]},
            },
        }
        common["expected_verdict"] = {
            "validation": {"overall": "ATTENTION", "workflow_consistency": "WARN", "overlap_pct_expected": 0},
            "judge": {"monitoring_verdict": "NEEDS_REVIEW", "weak_axis": "structuring_quality"},
        }
        common["eval_axes"] = _axes(chart=True)
    elif defect == "rx_safety":
        sp = clean["species"]
        if sp is None:
            return None  # 종 모르면 약물 금기 판정 불가
        diag = ([d[0] for d in clean["expected"]["chart"]["expected_diagnoses"]] or ["감염성 질환"])[0]
        if sp == "cat":
            meds = [{"drug": "아세트아미노펜", "dose": "100mg", "route": "경구", "frequency": "BID", "duration": "5일"}]
            viol = [{"type": "species_contraindication", "target": "아세트아미노펜", "reason": "고양이 절대 금기(치명적)"}]
            desc = "고양이에 아세트아미노펜 처방(절대 금기)."
        elif sp in ("rabbit", "guinea pig", "hamster"):
            meds = [{"drug": "아목시실린", "dose": "15mg/kg", "route": "경구", "frequency": "BID", "duration": "7일"}]
            viol = [{"type": "species_contraindication", "target": "아목시실린(경구)",
                     "reason": f"{sp} 경구 페니실린계 금기(장내세균총 붕괴→장독혈증 위험)"}]
            desc = f"{sp}에 경구 페니실린계 처방(종 금기)."
        else:  # dog 등 → 진단-처방 불일치
            meds = [{"drug": "프레드니솔론", "dose": "5mg", "route": "경구", "frequency": "BID", "duration": "7일"}]
            viol = [{"type": "diagnosis_rx_mismatch", "target": "스테로이드 단독(항생제 없음)",
                     "reason": f"'{diag}'에 항생제 없이 스테로이드 단독 — 감염 시 악화 위험"}]
            desc = f"'{diag}' 진단에 스테로이드 단독 처방(진단-처방 불일치)."
        common["injected_defect"] = {
            "type": defect, "subtypes": [v["type"] for v in viol], "description": desc,
            "corrupted_outputs": {
                "pet": {"species": sp},
                "chart_result": {"soap": {"A": f"{diag} 의심"},
                                 "prescription_draft": {"diagnosis": diag, "medications": meds, "cautions": []}},
            },
        }
        common["expected_verdict"] = {
            "rx_safety": {"verdict": "UNSAFE", "violations": viol},
            "validation": {"overall": "ATTENTION",
                           "_note": "현재 validation.py에 rx 검사 축이 없어 미탐지(=리펙토링으로 추가해야 잡힘)."},
            "judge": {"monitoring_verdict": "NEEDS_REVIEW"},
        }
        common["eval_axes"] = _axes(rx=True)
    else:
        return None
    return common

def _axes(redflag=False, urgency=False, schedule=False, completeness=False, chart=False, diagnosis=False, rx=False):
    return {"redflag_recall": redflag, "urgency_accuracy": urgency, "schedule_floor": schedule,
            "completeness": completeness, "chart_consistency": chart, "diagnosis_recall": diagnosis, "rx_safety": rx}


DEFECT_TYPES = ["redflag_urgency_mismatch", "missing_field", "chart_symptom_drift", "rx_safety"]

def derive_flawed(clean_cases: list[dict], n_flawed: int) -> list[dict]:
    """결함 유형 4종에 쿼터를 균등 배분해 flawed 케이스 생성. 주입 가능한 clean이 부족한
    유형(redflag=응급 clean만, rx_safety=종 명시 clean만)은 가능한 만큼만, 잔여는 다른 유형으로 채움."""
    per = max(1, n_flawed // len(DEFECT_TYPES))
    pools = {d: [c for c in clean_cases if make_flawed(c, d)] for d in DEFECT_TYPES}
    for d in pools:
        random.shuffle(pools[d])
    fl, used = [], set()
    # 1차: 유형별 쿼터
    for d in DEFECT_TYPES:
        cnt = 0
        for c in pools[d]:
            if cnt >= per or len(fl) >= n_flawed:
                break
            key = (c["case_id"], d)
            if key in used:
                continue
            fl.append(make_flawed(c, d)); used.add(key); cnt += 1
    # 2차: 잔여를 라운드로빈으로 채움
    di = 0
    while len(fl) < n_flawed:
        d = DEFECT_TYPES[di % len(DEFECT_TYPES)]; di += 1
        added = False
        for c in pools[d]:
            key = (c["case_id"], d)
            if key not in used:
                fl.append(make_flawed(c, d)); used.add(key); added = True; break
        if not added and di % len(DEFECT_TYPES) == 0 and not any(
                (c["case_id"], dd) not in used for dd in DEFECT_TYPES for c in pools[dd]):
            break  # 더 만들 후보 없음
    return fl


def _assemble_output(cases: list[dict], clean_cases: list[dict], fl: list[dict], warns: list[str]) -> dict:
    return {
        "metadata": {
            "name": "MediPaw 검증 벤치마크",
            "version": "1.0.0",
            "generated_from": "PetEVAL (SAVSNET, Apache-2.0)",
            "counts": {"total": len(cases), "clean": len(clean_cases), "flawed": len(fl)},
            "gold_policy": "category/species/red_flag/urgency/rx_class는 노트 규칙추출(LLM 미사용)+evidence. LLM은 대화문체·진단 한국어표기만.",
            "by_category": dict(Counter(c["category"] for c in cases)),
            "by_species": dict(Counter(str(c.get("species")) for c in cases)),
            "by_tier": dict(Counter(c["tier"] for c in cases)),
            "by_defect": dict(Counter(c["injected_defect"]["type"] for c in fl)),
            "low_confidence_urgency": sum(1 for c in clean_cases
                                          if c.get("gold_provenance", {}).get("urgency_confidence") == "low"),
            "generation_warnings": warns[:50],
        },
        "cases": cases,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--n", type=int, default=120, help="clean 케이스 목표 수")
    ap.add_argument("--flawed-ratio", type=float, default=0.4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 gold 추출만(빠른 점검)")
    ap.add_argument("--from-clean", default=None,
                    help="기존 생성 JSON에서 clean 케이스를 재사용해 flawed만 재구성(LLM 재호출 없음)")
    args = ap.parse_args()
    random.seed(args.seed)

    # ── 재사용 모드: 기존 clean으로 flawed만 다시 만든다(비싼 LLM 생성 스킵) ──
    if args.from_clean:
        prev = json.loads(Path(args.from_clean).read_text())
        clean_cases = [c for c in prev["cases"] if c["tier"] == "clean"]
        fl = derive_flawed(clean_cases, int(len(clean_cases) * args.flawed_ratio))
        cases = clean_cases + fl
        out = _assemble_output(cases, clean_cases, fl, prev["metadata"].get("generation_warnings", []))
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"\n✓ (재구성) {len(cases)}건 → {args.out} · clean={len(clean_cases)} flawed={len(fl)}", file=sys.stderr)
        return

    data = json.loads(Path(args.src).read_text())
    valid = [d for d in data if d.get("disease") and d["disease"] not in ("[]", "")
             and d.get("icd_label") and len(d["icd_label"]) > 0
             and d.get("sentence") and len(d["sentence"]) >= 300]

    # 층화 표집: (1) 희귀종(토끼·이그조틱)과 (2) 응급근거 보유 노트를 우선 포함해
    # '모든 소동물 커버 + 응급 케이스 충분'을 보장. 근거는 모두 실제 노트에 있음(추측 아님).
    REDFLAG_ANY = re.compile("|".join(p for p, _, _ in REDFLAG_RULES))
    for d in valid:
        d["_cat"] = to_category(d["icd_label"])
        d["_sp"] = detect_species(d["sentence"])
        d["_rare"] = d["_sp"] not in (None, "dog", "cat")
        d["_urgent"] = bool(REDFLAG_ANY.search(d["sentence"].lower()))
    n = max(args.n, 1)
    rare = [d for d in valid if d["_rare"]]                                   # 전부 포함(희귀종)
    urgent = [d for d in valid if d["_urgent"] and not d["_rare"]]            # 응급근거
    routine = [d for d in valid if not d["_urgent"] and not d["_rare"]]       # 비응급(안정/미상)
    random.shuffle(rare); random.shuffle(urgent); random.shuffle(routine)
    urgent_quota = max(0, int(n * 0.35) - len(rare))                          # 응급 ~35% 상한
    pool = rare + urgent[:urgent_quota]
    pool += routine[: max(0, n - len(pool))]
    if len(pool) < n:                                                        # 모자라면 응급으로 채움
        pool += urgent[urgent_quota: urgent_quota + (n - len(pool))]
    random.shuffle(pool)
    pool = pool[:n]

    llm = None if args.dry_run else get_llm()
    cases, warns_total = [], []
    for i, rec in enumerate(pool):
        cat, sp = rec["_cat"], rec["_sp"]
        dis_en = parse_disease_entities(rec["disease"])
        gold = derive_redflag_and_urgency(rec["sentence"], cat)
        gold["rx_evidence"] = derive_rx_class(rec["sentence"])
        style = random.choices(INPUT_STYLES, weights=[50, 35, 15])[0]
        if args.dry_run:
            conv = {"messages": [], "symptom_keywords_ko": [], "diagnoses_ko": dis_en}
        else:
            from langchain_core.messages import SystemMessage, HumanMessage
            resp = llm.invoke([SystemMessage(content=CONV_SYSTEM),
                               HumanMessage(content=build_conv_user(rec["sentence"], sp, dis_en, cat, style))])
            try:
                conv = json.loads(resp.content)
            except Exception as e:
                warns_total.append(f"{rec['id']}: conv JSON 파싱 실패 {e}")
                continue
            conv["messages"] = normalize_messages(conv.get("messages"))
            w = validate_conv(conv, rec["sentence"])
            if w:
                warns_total.append(f"{rec['id']}: " + "; ".join(w))
        cases.append(build_clean_case(rec, conv, gold, sp, cat, style, dis_en))
        print(f"  [{i+1}/{len(pool)}] {rec['id']} {cat} sp={sp} urg={gold['urgency_level_num_gold']}({gold['urgency_confidence']})", file=sys.stderr)

    # flawed 파생 (규칙 주입, LLM 미사용) — 결함 유형별 쿼터로 균형 배분
    clean_cases = list(cases)
    fl = derive_flawed(clean_cases, int(len(clean_cases) * args.flawed_ratio))
    cases.extend(fl)

    out = _assemble_output(cases, clean_cases, fl, warns_total)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n✓ {len(cases)}건 저장 → {args.out}", file=sys.stderr)
    print(f"  clean={len(clean_cases)} flawed={len(fl)} warnings={len(warns_total)} "
          f"low_conf_urgency={out['metadata']['low_confidence_urgency']}", file=sys.stderr)


if __name__ == "__main__":
    main()
