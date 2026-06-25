"""MediPaw 제출/시연용 데모 데이터 시드 스크립트.

실제 운영처럼 보이도록 운영진·동물병원·수의사·보호자·반려동물·예약·문진(triage)·
채팅·경과기록(followup)·진료기록(EMR)을 서로 FK로 자연스럽게 이어 채운다.

────────────────────────────────────────────────────────────────────────
실행 방법
    cd backend
    # 로컬 dev DB(docker-db, localhost:5432)에 시드
    python scripts/seed_demo_data.py

    # demo 데이터만 전부 삭제(teardown)하고 종료
    python scripts/seed_demo_data.py --reset-demo

    # 운영(RDS) 등 비-로컬 DB에 강제로 실행해야 할 때만(권장하지 않음)
    ALLOW_DEMO_SEED=1 python scripts/seed_demo_data.py
────────────────────────────────────────────────────────────────────────
안전장치
  * RDS(운영) 호스트로 보이면 무조건 중단한다.
  * 로컬(localhost/127.0.0.1/docker db) 이 아니면 ALLOW_DEMO_SEED=1 없이는 중단한다.
  * 삭제·재생성은 "데모 마커"가 붙은 행에만 적용된다. 실제 사용자 데이터는 건드리지 않는다.
        - 운영진:  admin_userDB.loginid LIKE '%@medipaw.demo'
        - 보호자:  userDB.loginid       LIKE '%@medipaw.demo'
        - 병원:    hospitalDB.business_number LIKE 'DEMO-%'
        - 수의사:  소속 병원이 데모 병원인 doctorDB
  * 매 실행은 "데모 마커 행만 삭제 후 동일하게 재생성" → 여러 번 돌려도 중복이 쌓이지 않음(멱등).

비밀번호는 app.core.security.hash_password(bcrypt) 로 해시 저장한다.
원문 초기 비밀번호는 실행 마지막에 계정 표로 출력된다(시연 로그인용).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.models.chat_history import ChatHistory
from app.models.doctor import Doctor
from app.models.doctor_profile import DoctorProfile
from app.models.emr import EMR
from app.models.followup import Followup
from app.models.guardian import Guardian
from app.models.guardian_hospital import GuardianHospital
from app.models.hospital import Hospital
from app.models.hospital_profile import HospitalProfile
from app.models.master import CategoryMaster, TriageMaster
from app.models.pet import Pet
from app.models.schedule import Schedule
from app.models.triage_result import TriageResult
from app.models.user import User
from app.models.vet_schedule import (
    HospitalClosedDate,
    HospitalWeeklySchedule,
    VetWeeklySchedule,
)

# ── 데모 마커/상수 ────────────────────────────────────────────────────────
DEMO_DOMAIN = "medipaw.demo"
DEMO_BIZ_PREFIX = "DEMO-"           # 병원 business_number 마커
DEMO_LICENSE_PREFIX = "DEMO-V-"     # 수의사 license_number 마커

PW_ADMIN = "DemoAdmin123!"
PW_GUARDIAN = "DemoGuardian123!"
PW_VET_INITIAL = "DemoVet123!"      # 병원(수의사웹) 계정 초기 비밀번호 → 첫 로그인 시 변경 필요

DEFAULT_DURATION_MIN = 30
KST = timezone(timedelta(hours=9))

# 결정적 생성(여러 번 실행해도 동일한 데이터/카운트가 나오도록)
RNG = random.Random(20260624)

DATABASE_URL = os.environ.get("DATABASE_URL", settings.DATABASE_URL)


def _to_async_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        .replace("postgresql://", "postgresql+asyncpg://")
    )


def _guard_environment() -> None:
    """운영 DB 오염 방지. 로컬이 아니면 ALLOW_DEMO_SEED=1 없이는 중단."""
    host = (urlparse(DATABASE_URL.replace("+asyncpg", "").replace("+psycopg2", "")).hostname or "").lower()
    if "rds.amazonaws.com" in host or host.endswith(".rds.amazonaws.com"):
        sys.exit(f"[중단] 운영(RDS)로 보이는 호스트입니다: {host}. 데모 시드는 dev/demo 전용입니다.")
    local_hosts = {"localhost", "127.0.0.1", "::1", "db", "postgres", "medipaw-db"}
    if host not in local_hosts and os.environ.get("ALLOW_DEMO_SEED") != "1":
        sys.exit(
            f"[중단] 비-로컬 DB 호스트({host})입니다. 의도한 경우에만 "
            "ALLOW_DEMO_SEED=1 환경변수와 함께 실행하세요."
        )
    print(f"[seed_demo] 대상 DB host = {host or '(local socket)'}")


# ── 병원 정의 ────────────────────────────────────────────────────────────
# 스키마에 전용 컬럼이 없는 항목(진료가능동물/주의사항/예약·취소정책/진료과목/응급여부)은
# 가장 가까운 기존 필드(hospital_profile.intro / features JSON)에 자연스럽게 녹인다.
HOSPITALS = [
    {
        "biz": "DEMO-0001",
        "name": "메디포동물병원",
        "login": f"medipaw-demo@{DEMO_DOMAIN}",
        "address": "서울특별시 강남구 테헤란로 123 메디포빌딩 2층",
        "phone": "02-555-0001",
        "owner_email": f"medipaw-demo@{DEMO_DOMAIN}",
        "tagline": "강남 24시 신뢰 동물병원, 내과·외과 종합진료",
        "emergency": True,
        "departments": ["내과", "외과", "치과", "영상의학과"],
        "species": ["강아지", "고양이"],
        "intro": (
            "메디포동물병원은 강아지·고양이 종합진료를 제공하는 1차 진료 병원입니다. "
            "내과·외과·치과·영상의학 진료가 가능하며 응급 진료를 운영합니다. "
            "예약 정책: 진료 전날까지 예약/변경 가능, 당일 예약은 전화 문의. "
            "취소/변경 정책: 예약 2시간 전까지 무료 변경·취소, 이후는 전화 안내. "
            "주의사항: 내원 시 리드줄/이동장을 반드시 사용해 주세요."
        ),
        "features": ["24시 응급", "내과", "외과", "치과", "영상의학", "강아지", "고양이"],
        "weekday_hours": (time(9, 0), time(20, 0), time(13, 0), time(14, 0)),
        "sat_hours": (time(9, 0), time(15, 0), None, None),
        "sun_open": False,
        "closed_dates": ["__new_year__"],
    },
    {
        "biz": "DEMO-0002",
        "name": "해피펫동물병원",
        "login": f"happypet-demo@{DEMO_DOMAIN}",
        "address": "경기도 성남시 분당구 정자일로 200 1층",
        "phone": "031-700-0002",
        "owner_email": f"happypet-demo@{DEMO_DOMAIN}",
        "tagline": "분당 가족 같은 동네 동물병원",
        "emergency": False,
        "departments": ["내과", "피부과", "예방의학"],
        "species": ["강아지", "고양이", "토끼", "햄스터"],
        "intro": (
            "해피펫동물병원은 강아지·고양이는 물론 토끼·햄스터 등 소동물 진료가 가능한 동네 병원입니다. "
            "피부과·내과·예방접종 상담에 강점이 있습니다. 응급 진료는 운영하지 않으며 주간 진료만 진행합니다. "
            "예약 정책: 모든 진료는 예약제로 운영합니다. "
            "취소/변경 정책: 예약 전날까지 자유롭게 변경/취소 가능. "
            "주의사항: 소동물은 이동 스트레스가 크니 전용 케이지로 내원해 주세요."
        ),
        "features": ["피부과 특화", "소동물 진료", "예방접종", "토끼", "햄스터"],
        "weekday_hours": (time(9, 30), time(18, 30), time(12, 30), time(13, 30)),
        "sat_hours": (time(9, 30), time(13, 0), None, None),
        "sun_open": False,
        "closed_dates": [],
    },
    {
        "biz": "DEMO-0003",
        "name": "라온동물메디컬센터",
        "login": f"raon-demo@{DEMO_DOMAIN}",
        "address": "부산광역시 해운대구 센텀중앙로 55 메디컬타워 3층",
        "phone": "051-700-0003",
        "owner_email": f"raon-demo@{DEMO_DOMAIN}",
        "tagline": "부산 센텀 외과·정형외과 전문 메디컬센터",
        "emergency": True,
        "departments": ["외과", "정형외과", "내과", "비뇨기과"],
        "species": ["강아지", "고양이"],
        "intro": (
            "라온동물메디컬센터는 외과·정형외과 수술과 비뇨기 질환 진료에 특화된 2차 진료 의뢰 병원입니다. "
            "수술 후 회복 관리와 재활을 함께 제공하며 응급 수술 대응이 가능합니다. "
            "예약 정책: 수술/검사 진료는 사전 예약 및 사전 상담이 필요합니다. "
            "취소/변경 정책: 수술 예약은 3일 전까지 변경 가능, 이후 보증금 정책 적용. "
            "주의사항: 수술 전 8시간 금식 안내를 꼭 확인해 주세요."
        ),
        "features": ["외과 전문", "정형외과", "재활", "응급 수술", "비뇨기과"],
        "weekday_hours": (time(9, 0), time(19, 0), time(13, 0), time(14, 0)),
        "sat_hours": (time(9, 0), time(14, 0), None, None),
        "sun_open": False,
        "closed_dates": [],
    },
    {
        "biz": "DEMO-0004",
        "name": "온유24시동물병원",
        "login": f"onyu-demo@{DEMO_DOMAIN}",
        "address": "인천광역시 연수구 송도과학로 30 1~2층",
        "phone": "032-700-0004",
        "owner_email": f"onyu-demo@{DEMO_DOMAIN}",
        "tagline": "송도 24시간 응급 + 특수동물 진료",
        "emergency": True,
        "departments": ["내과", "응급의학과", "특수동물진료", "치과"],
        "species": ["강아지", "고양이", "토끼", "햄스터", "고슴도치", "앵무새"],
        "intro": (
            "온유24시동물병원은 24시간 응급 진료와 함께 토끼·햄스터·고슴도치·앵무새 등 특수동물(이그조틱) "
            "진료가 가능한 병원입니다. 야간/주말 응급 대응 체계를 갖추고 있습니다. "
            "예약 정책: 일반 진료는 예약 권장, 응급은 24시간 워크인 가능. "
            "취소/변경 정책: 예약 1시간 전까지 변경/취소 가능. "
            "주의사항: 특수동물은 종에 따라 진료 가능 시간이 다를 수 있어 전화 확인을 권장합니다."
        ),
        "features": ["24시 응급", "특수동물", "고슴도치", "앵무새", "야간진료"],
        "weekday_hours": (time(0, 0), time(23, 59), time(13, 0), time(14, 0)),
        "sat_hours": (time(0, 0), time(23, 59), None, None),
        "sun_open": True,
        "closed_dates": [],
    },
]

# ── 수의사 정의(병원 biz → 수의사 목록) ─────────────────────────────────
DOCTORS = {
    "DEMO-0001": [
        {"name": "김메디", "specialty": "내과", "edu": "서울대학교 수의학과 졸업",
         "areas": ["소화기 내과", "내분비"], "career": "내과 진료 12년", "days": [0, 1, 2, 3, 4]},
        {"name": "이도윤", "specialty": "외과", "edu": "건국대학교 수의학과 졸업",
         "areas": ["연부조직 외과", "중성화"], "career": "외과 진료 9년", "days": [0, 2, 4, 5]},
        {"name": "박서연", "specialty": "치과", "edu": "경북대학교 수의학과 졸업",
         "areas": ["치과", "구강외과"], "career": "치과 진료 7년", "days": [1, 3, 4]},
    ],
    "DEMO-0002": [
        {"name": "최하늘", "specialty": "피부과", "edu": "전남대학교 수의학과 졸업",
         "areas": ["피부과", "알레르기"], "career": "피부과 진료 10년", "days": [0, 1, 2, 3, 4, 5]},
        {"name": "정유진", "specialty": "내과", "edu": "충북대학교 수의학과 졸업",
         "areas": ["일반 내과", "예방의학"], "career": "내과 진료 6년", "days": [0, 1, 3, 4]},
    ],
    "DEMO-0003": [
        {"name": "강태현", "specialty": "정형외과", "edu": "서울대학교 수의학과 졸업",
         "areas": ["정형외과", "재활"], "career": "정형외과 수술 15년", "days": [0, 1, 2, 3, 4]},
        {"name": "윤소라", "specialty": "외과", "edu": "건국대학교 수의학과 졸업",
         "areas": ["연부조직 외과", "종양외과"], "career": "외과 수술 11년", "days": [0, 2, 3, 4, 5]},
        {"name": "한지우", "specialty": "비뇨기과", "edu": "경상대학교 수의학과 졸업",
         "areas": ["비뇨기", "내과"], "career": "내과·비뇨기 진료 8년", "days": [1, 2, 4]},
    ],
    "DEMO-0004": [
        {"name": "오은상", "specialty": "응급의학과", "edu": "충남대학교 수의학과 졸업",
         "areas": ["응급의학", "중환자 관리"], "career": "응급 진료 13년", "days": [0, 1, 2, 3, 4, 5, 6]},
        {"name": "임가람", "specialty": "특수동물진료", "edu": "전북대학교 수의학과 졸업",
         "areas": ["이그조틱(토끼/설치류)", "조류"], "career": "특수동물 진료 9년", "days": [1, 2, 3, 4, 5]},
        {"name": "신예준", "specialty": "내과", "edu": "제주대학교 수의학과 졸업",
         "areas": ["일반 내과", "치과"], "career": "내과 진료 5년", "days": [0, 2, 4, 6]},
    ],
}

# ── 보호자 정의(실제 운영처럼 다수 자동 생성) ───────────────────────────
# 첫 12명은 기존에 안내한 g01~g12 계정과 동일한 이름을 유지(시연 연속성).
DEFAULT_GUARDIAN_COUNT = 85   # --guardians 로 조절. 2자리 패딩이라 1~99 권장.

_FIXED_GUARDIANS = [
    "김보호", "이수민", "박지호", "최아람", "정민재", "강예린",
    "윤도현", "한소율", "오태경", "임채원", "신준호", "배유나",
]
_SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서",
             "신", "권", "황", "안", "송", "전", "홍", "고", "문", "양", "손", "배", "백", "허", "남"]
_GIVEN = ["민준", "서연", "도윤", "하은", "지호", "수아", "예준", "지유", "주원", "서윤", "건우",
          "채원", "현우", "다은", "우진", "유나", "지훈", "하린", "선우", "서아", "준서", "지아",
          "연우", "아윤", "시우", "예린", "민재", "소율", "태경", "채은", "준호", "유진", "도현",
          "하늘", "은상", "가람", "소라", "지우", "나윤", "재윤", "수빈", "예나", "지안", "윤서"]
_CITY_DISTRICTS = [
    "서울특별시 강남구 역삼동", "서울특별시 서초구 반포동", "서울특별시 마포구 합정동",
    "서울특별시 송파구 잠실동", "서울특별시 노원구 상계동", "경기도 성남시 분당구 정자동",
    "경기도 수원시 영통구 이의동", "경기도 고양시 일산동구 백석동", "경기도 용인시 수지구",
    "인천광역시 연수구 송도동", "인천광역시 남동구 구월동", "부산광역시 해운대구 우동",
    "부산광역시 수영구 광안동", "대구광역시 수성구 범어동", "대전광역시 유성구 봉명동",
    "광주광역시 서구 치평동", "울산광역시 남구 삼산동", "세종특별자치시 도담동",
]


def build_guardian_profiles(n: int) -> list[tuple[str, str, str]]:
    """(이름, 전화, 주소) n개를 결정적으로 생성. 첫 12명은 고정 이름 유지."""
    rng = random.Random(20260625)
    profiles: list[tuple[str, str, str]] = []
    for i in range(n):
        if i < len(_FIXED_GUARDIANS):
            name = _FIXED_GUARDIANS[i]
        else:
            name = rng.choice(_SURNAMES) + rng.choice(_GIVEN)
        phone = f"010-{2000 + i:04d}-{rng.randint(1000, 9999)}"
        addr = rng.choice(_CITY_DISTRICTS) + f" {rng.randint(1, 199)}-{rng.randint(1, 30)}"
        profiles.append((name, phone, addr))
    return profiles

# ── 반려동물 풀(종별 후보) ──────────────────────────────────────────────
PET_POOL = {
    "강아지": {"species": "dog",
             "breeds": ["말티즈", "푸들", "포메라니안", "비숑프리제", "시츄", "웰시코기", "골든리트리버",
                        "진돗개", "닥스훈트", "치와와", "요크셔테리어", "보더콜리", "사모예드", "믹스견"],
             "names": ["토리", "콩이", "보리", "초코", "몽이", "두부", "별이", "단추", "복실", "햇살",
                       "초롱", "라떼", "감자", "구름", "보름", "후추", "마루", "젤리", "사랑", "방울"],
             "weight": (2.5, 19.0)},
    "고양이": {"species": "cat",
             "breeds": ["코리안숏헤어", "러시안블루", "스코티시폴드", "먼치킨", "페르시안", "샴",
                        "뱅갈", "노르웨이숲", "아메리칸숏헤어", "랙돌", "믹스묘"],
             "names": ["나비", "치즈", "모카", "까미", "루나", "삼색이", "호두", "코코", "보리",
                       "구름", "양말", "젤리", "참치", "꼬미", "달이", "흰둥", "레오"],
             "weight": (2.8, 7.5)},
    "토끼": {"species": "rabbit",
            "breeds": ["네덜란드 드워프", "롭이어", "라이언헤드", "렉스", "믹스"],
            "names": ["당근", "뭉치", "흰둥", "토토", "복실", "달콩", "마요"], "weight": (1.0, 3.0)},
    "햄스터": {"species": "hamster",
             "breeds": ["골든햄스터", "드워프햄스터", "로보로브스키", "정글리안"],
             "names": ["햄찌", "도토리", "콩알", "치즈볼", "꼬물", "단추"], "weight": (0.03, 0.22)},
    "고슴도치": {"species": "hedgehog", "breeds": ["피그미", "알비노"],
              "names": ["가시", "밤톨", "뾰족", "송이", "고슴"], "weight": (0.3, 0.65)},
    "앵무새": {"species": "parrot",
            "breeds": ["코카투", "왕관앵무", "사랑앵무", "회색앵무", "모란앵무"],
            "names": ["초롱", "방울", "삐약", "하루", "노랑", "파랑"], "weight": (0.05, 1.0)},
}

# 종 분포 가중치(현실적 비율: 개/고양이 多, 특수동물 少지만 충분히 등장)
SPECIES_KR = list(PET_POOL.keys())          # [강아지, 고양이, 토끼, 햄스터, 고슴도치, 앵무새]
SPECIES_WEIGHTS = [36, 30, 13, 9, 5, 7]

# 보호자 기본병원 배정 가중치 — 메디포(index 0)에 집중. (HOSPITALS 순서와 1:1)
GUARDIAN_HOSP_WEIGHTS = [0.55, 0.16, 0.15, 0.14]
# 병원별 예약량 가중치 — 메디포는 꽉, 나머지는 가볍게. (HOSPITALS 순서와 1:1)
HOSP_APPT_WEIGHTS = [1.0, 0.35, 0.35, 0.35]


# ── placeholder 이미지 URL ────────────────────────────────────────────────
# 이미지 업로드(브라우저→S3 직접 PUT)는 S3 버킷 CORS가 로컬 origin을 막아 로컬에선 실패한다.
# 그래서 데모 사진은 공개 placeholder 이미지 URL을 필드에 직접 넣는다(프론트는 전체 URL을 <img src>로 그대로 표시).
# 외부 서비스라 인터넷 연결이 필요하며, URL만 바꾸면 사내 S3/CloudFront 이미지로 교체 가능.
_PET_PHOTO_KW = {"dog": "dog", "cat": "cat", "rabbit": "rabbit",
                 "hamster": "hamster", "hedgehog": "hedgehog", "parrot": "parrot,bird"}


def hospital_banner_url(idx: int) -> str:
    # Lorem Picsum: 매우 안정적, seed로 결정적. 와이드 배너.
    return f"https://picsum.photos/seed/medipaw-hosp{idx}/1200/420"


def doctor_avatar_url(n: int) -> str:
    # pravatar: 실제 인물 초상(원장 프로필용). img 1~70.
    return f"https://i.pravatar.cc/400?img={(n % 70) + 1}"


def pet_photo_url(species: str, lock: int) -> str:
    # LoremFlickr: 종별 실제 동물 사진, lock으로 결정적.
    kw = _PET_PHOTO_KW.get(species, "pet")
    return f"https://loremflickr.com/400/400/{kw}?lock={lock}"

PET_NOTES_BITS = {
    "allergy": ["없음", "닭고기 알러지 의심", "특정 사료 알러지 있음", "없음", "없음"],
    "history": ["특이 병력 없음", "작년 슬개골 탈구 진단 이력", "유선종양 제거 수술 이력",
                "만성 신장 관리 중", "특이 병력 없음", "외이염 재발 이력"],
    "meds": ["복용 약 없음", "관절 영양제 급여 중", "처방 사료 급여 중",
             "복용 약 없음", "심장약 복용 중"],
    "note": ["겁이 많아 진료 시 보정 필요", "사람을 잘 따름", "낯선 환경에서 예민함",
             "특이사항 없음", "간식 유도 시 협조적"],
}

# ── 문진/상담 케이스 템플릿 ─────────────────────────────────────────────
# urgency: (level, num) — 1 RED / 2 ORANGE / 3 YELLOW / 4 GREEN
# 진단 확정 표현은 피하고 "의심/상담/문진 요약" 수준으로만 작성한다.
CASES = [
    {
        "key": "vomit", "species": ["dog", "cat"], "complaint": "구토와 식욕 저하",
        "keywords": ["구토", "식욕저하", "물 소량 섭취"], "urgency": ("YELLOW", 3),
        "suspected": ["급성 위장관 자극 의심", "식이 관련 위장염 가능성"],
        "summary": "어제부터 구토 2회, 식욕 저하, 물 소량 섭취. 발열·무기력 소견 없음.",
        "action": "내과", "checkup": False,
        "red_flags": [],
        "chat": [
            ("user", "토리 어제부터 구토를 두 번 했고 밥을 잘 안 먹어요."),
            ("assistant", "걱정되시겠어요. 정확한 안내를 위해 구토 횟수, 마지막 식사 시간, 물 섭취 여부를 알려주세요."),
            ("user", "마지막 식사는 어제 저녁이고 물은 조금 마셨어요."),
            ("assistant", "확인했어요. 예약 전까지 구토 횟수와 활력 변화를 기록해 주세요. 구토에 피가 섞이거나 축 늘어지면 바로 내원이 필요합니다."),
        ],
        "followups": [
            "오늘은 구토는 없고 밥을 조금 먹었어요.",
            "물은 잘 마시는데 사료는 아직 절반만 먹어요.",
        ],
        "vet_memo": "보호자 문진상 어제부터 구토 2회·식욕 저하. 탈수 경미, 활력 양호. 위장관 자극 가능성으로 식이 조절 및 경과 관찰 권고.",
    },
    {
        "key": "diarrhea", "species": ["dog", "cat"], "complaint": "설사 증상",
        "keywords": ["설사", "묽은 변", "잦은 배변"], "urgency": ("YELLOW", 3),
        "suspected": ["장염 의심", "식이 변화 관련 설사 가능성"],
        "summary": "이틀째 묽은 변, 하루 3~4회 배변. 혈변·구토 동반 없음, 활력 보통.",
        "action": "내과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "콩이가 이틀째 설사를 해요. 변이 너무 묽어요."),
            ("assistant", "배변 횟수와 변에 피나 점액이 섞였는지, 사료를 최근에 바꾸셨는지 알려주세요."),
            ("user", "하루 서너 번이고 피는 없어요. 사료는 일주일 전에 바꿨어요."),
            ("assistant", "사료 변경이 원인일 수 있어요. 탈수 예방을 위해 물을 자주 주시고, 혈변이나 무기력이 보이면 바로 알려주세요."),
        ],
        "followups": ["변이 어제보다 단단해졌어요.", "설사 횟수가 하루 한 번으로 줄었어요."],
        "vet_memo": "이틀째 묽은 변, 혈변 없음. 사료 변경 이력. 식이성 장염 가능성으로 처방식 및 수분 보충 권고.",
    },
    {
        "key": "skin", "species": ["dog", "cat", "hedgehog"], "complaint": "피부 가려움과 발진",
        "keywords": ["피부 가려움", "발진", "긁음"], "urgency": ("GREEN", 4),
        "suspected": ["알레르기성 피부염 의심", "표재성 피부 감염 가능성"],
        "summary": "최근 일주일 배·겨드랑이 부위 발적과 가려움. 탈모 경미, 진물 없음.",
        "action": "피부과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "보리가 자꾸 배를 긁어서 빨갛게 됐어요."),
            ("assistant", "가려워하는 부위와 시작 시기, 진물이나 딱지가 있는지 알려주세요. 사진이 있으면 첨부해 주세요."),
            ("user", "배랑 겨드랑이 쪽이고 일주일쯤 됐어요. 진물은 없어요."),
            ("assistant", "알레르기성 피부 반응일 수 있어요. 긁지 않도록 관리하시고 진료 시 정확히 살펴보겠습니다."),
        ],
        "followups": ["사진처럼 피부가 더 빨개진 것 같아요.", "약 바르고 나서 긁는 게 줄었어요."],
        "vet_memo": "배·겨드랑이 발적과 소양감, 진물 없음. 알레르기성 피부염 가능성으로 외용 처치 및 관리 안내.",
    },
    {
        "key": "ear", "species": ["dog", "cat"], "complaint": "귀 냄새와 귀를 자주 긁음",
        "keywords": ["귀 냄새", "외이염 의심", "귀 긁음"], "urgency": ("GREEN", 4),
        "suspected": ["외이염 의심"],
        "summary": "며칠째 귀에서 냄새가 나고 머리를 자주 턴다. 갈색 귀지 증가.",
        "action": "피부과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "초코 귀에서 냄새가 나고 자꾸 머리를 털어요."),
            ("assistant", "귀지 색과 양, 귀를 만질 때 통증 반응이 있는지 알려주세요."),
            ("user", "갈색 귀지가 많아졌고 만지면 싫어해요."),
            ("assistant", "외이염이 의심됩니다. 면봉으로 깊이 닦지 마시고 진료 때 귀 검사를 받아보세요."),
        ],
        "followups": ["귀 세정 후 냄새가 조금 줄었어요.", "아직 머리를 가끔 털어요."],
        "vet_memo": "갈색 이구 증가, 두부 진탕(head shaking). 외이염 의심으로 이도 검사 및 세정 처치.",
    },
    {
        "key": "cough", "species": ["dog", "cat"], "complaint": "기침이 잦음",
        "keywords": ["기침", "캑캑거림"], "urgency": ("YELLOW", 3),
        "suspected": ["상부 호흡기 자극 의심", "기관 자극 가능성"],
        "summary": "사흘째 마른기침, 흥분 시 심해짐. 호흡곤란·청색증 없음.",
        "action": "내과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "몽이가 사흘째 캑캑거리는 기침을 해요."),
            ("assistant", "기침이 마른기침인지, 운동이나 흥분 후 심해지는지, 호흡이 가쁜지 알려주세요."),
            ("user", "마른기침이고 흥분하면 더 해요. 숨차 보이진 않아요."),
            ("assistant", "호흡기 자극일 수 있어요. 흥분을 줄여주시고 호흡이 가빠지면 바로 알려주세요."),
        ],
        "followups": ["기침 횟수가 줄었어요.", "밤에 가끔 기침해요."],
        "vet_memo": "3일째 마른기침, 호흡곤란 없음. 상부 호흡기 자극 가능성으로 흉부 청진 및 경과 관찰.",
    },
    {
        "key": "limp", "species": ["dog", "cat", "rabbit"], "complaint": "뒷다리를 절뚝거림",
        "keywords": ["절뚝거림", "보행 이상", "뒷다리"], "urgency": ("YELLOW", 3),
        "suspected": ["슬개골 관련 보행 이상 의심", "연부조직 손상 가능성"],
        "summary": "어제부터 산책 후 왼쪽 뒷다리를 들고 절뚝거림. 부종·개방창 없음.",
        "action": "정형외과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "별이가 산책 다녀온 뒤로 뒷다리를 절뚝거려요."),
            ("assistant", "어느 쪽 다리인지, 다리를 완전히 들고 있는지, 만질 때 아파하는지 알려주세요."),
            ("user", "왼쪽 뒷다리고 가끔 들어요. 만지면 살짝 피해요."),
            ("assistant", "관절이나 근육 문제일 수 있어요. 무리한 점프를 피하게 하시고 진료 때 보행 검사를 받아보세요."),
        ],
        "followups": ["절뚝거림은 조금 줄었어요.", "계단 오를 때만 살짝 절어요."],
        "vet_memo": "좌측 후지 간헐적 거상, 부종 없음. 슬개골/연부조직 평가 필요로 보행·촉진 검사 권고.",
    },
    {
        "key": "dental_post", "species": ["dog", "cat"], "complaint": "발치 후 경과 확인",
        "keywords": ["발치 후", "구강 관리"], "urgency": ("GREEN", 4),
        "suspected": ["발치 부위 정상 회복 과정 관찰"],
        "summary": "치아 발치 후 3일째 경과. 식사량 회복 중, 출혈·부종 없음.",
        "action": "치과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "지난주 발치하고 나서 잘 회복되는지 확인하고 싶어요."),
            ("assistant", "식사는 잘 하는지, 입 주변 부종이나 출혈, 침을 흘리는 증상이 있는지 알려주세요."),
            ("user", "부드러운 사료는 잘 먹고 출혈은 없어요."),
            ("assistant", "회복이 순조로워 보여요. 딱딱한 간식은 잠시 피하시고 예정된 재진 때 확인하겠습니다."),
        ],
        "followups": ["부드러운 사료는 잘 먹어요.", "입 냄새가 줄어든 것 같아요."],
        "vet_memo": "발치 후 3일째, 발치창 출혈/부종 없음. 식이 양호. 정상 회복 과정으로 판단, 연식 급여 유지 안내.",
    },
    {
        "key": "post_surgery", "species": ["dog", "cat"], "complaint": "수술 후 회복 경과",
        "keywords": ["수술 후", "봉합부", "회복"], "urgency": ("ORANGE", 2),
        "suspected": ["수술 부위 회복 경과 관찰 필요"],
        "summary": "복부 수술 후 4일째. 봉합부 약간 붉음, 핥음 방지 필요. 식욕 회복 중.",
        "action": "외과", "checkup": False, "red_flags": ["봉합부 발적"],
        "chat": [
            ("user", "수술하고 나서 봉합부가 좀 빨간 것 같아 걱정돼요."),
            ("assistant", "봉합부에서 진물이나 벌어짐이 있는지, 핥거나 긁지는 않는지 알려주세요. 사진이 있으면 도움이 됩니다."),
            ("user", "진물은 없는데 자꾸 핥으려고 해요."),
            ("assistant", "넥카라를 유지해 핥지 않게 해주세요. 봉합부가 벌어지거나 진물이 보이면 바로 내원이 필요합니다."),
        ],
        "followups": ["넥카라 씌우니까 안 핥아요.", "봉합부 붉은 기가 조금 가라앉았어요.", "약 먹이고 나서 졸려 보여요."],
        "vet_memo": "개복 수술 후 4일째, 봉합부 경미한 발적·진물 없음. 자가 손상 방지(E-collar) 유지, 재발적 시 재내원 안내.",
    },
    {
        "key": "cystitis", "species": ["dog", "cat"], "complaint": "혈뇨와 잦은 배뇨",
        "keywords": ["혈뇨", "빈뇨", "배뇨 통증"], "urgency": ("ORANGE", 2),
        "suspected": ["방광염 의심", "하부 요로 질환 가능성"],
        "summary": "어제부터 소변에 붉은 기, 화장실을 자주 가지만 소변량 적음.",
        "action": "비뇨기과", "checkup": False, "red_flags": ["혈뇨", "배뇨 곤란"],
        "chat": [
            ("user", "까미가 소변을 자주 보러 가는데 양은 적고 붉은 색이 보여요."),
            ("assistant", "소변을 볼 때 힘들어하거나 우는지, 마지막 정상 배뇨가 언제였는지 알려주세요. 수컷이라면 소변이 아예 안 나오면 응급입니다."),
            ("user", "끙끙대면서 보고 양은 적어요. 오늘 아침엔 봤어요."),
            ("assistant", "방광염이 의심됩니다. 물을 자주 마시게 하시고, 소변이 전혀 안 나오면 즉시 내원해 주세요."),
        ],
        "followups": ["소변 색은 어제보다 옅어졌어요.", "화장실 가는 횟수가 줄었어요."],
        "vet_memo": "혈뇨·빈뇨·잔뇨감. 하부요로 질환(방광염) 의심으로 요검사 및 영상 검사 권고. 요폐 징후 시 응급 안내.",
    },
    {
        "key": "vaccine", "species": ["dog", "cat", "rabbit", "parrot"], "complaint": "예방접종 상담",
        "keywords": ["예방접종", "백신 상담"], "urgency": ("GREEN", 4),
        "suspected": ["예방접종 일정 상담"],
        "summary": "예방접종 시기 및 종류 상담 요청. 현재 특이 증상 없음.",
        "action": "예방의학", "checkup": True, "red_flags": [],
        "chat": [
            ("user", "예방접종 시기가 됐는지 상담받고 싶어요."),
            ("assistant", "마지막 접종일과 접종 종류를 알려주시면 다음 일정을 안내해 드릴게요."),
            ("user", "작년 이맘때 종합백신 맞았어요."),
            ("assistant", "추가 접종 시기가 맞아 보여요. 접종 전 건강 상태 확인을 위해 내원 일정을 잡아드리겠습니다."),
        ],
        "followups": ["접종 후 컨디션 괜찮아요.", "주사 맞은 부위는 부어 있지 않아요."],
        "vet_memo": "예방접종 상담. 접종력 확인 후 추가 접종 일정 안내. 접종 전 신체검사 예정.",
    },
    {
        "key": "checkup", "species": ["dog", "cat", "rabbit"], "complaint": "건강검진 희망",
        "keywords": ["건강검진", "정기검진"], "urgency": ("GREEN", 4),
        "suspected": ["정기 건강검진"],
        "summary": "특이 증상 없이 정기 건강검진 희망. 노령 진입으로 혈액검사 상담.",
        "action": "건강검진", "checkup": True, "red_flags": [],
        "chat": [
            ("user", "특별한 증상은 없는데 정기 건강검진을 받고 싶어요."),
            ("assistant", "나이와 최근 검진 이력을 알려주시면 적합한 검진 항목을 안내해 드릴게요."),
            ("user", "이제 8살이고 작년엔 검진 안 했어요."),
            ("assistant", "노령 진입 시기라 기본 혈액검사와 신체검사를 권장드려요. 검진 예약을 도와드리겠습니다."),
        ],
        "followups": ["검진 전 금식 잘 시켰어요.", "컨디션은 평소와 같아요."],
        "vet_memo": "무증상 정기검진 희망. 노령 기본 패널(혈액/소변/신체검사) 권고.",
    },
    {
        "key": "foreign_body", "species": ["dog", "cat"], "complaint": "이물 섭취 의심",
        "keywords": ["이물 섭취", "삼킴", "구토 시도"], "urgency": ("RED", 1),
        "suspected": ["이물 섭취 의심 — 응급 평가 필요"],
        "summary": "장난감 일부를 삼킨 것으로 의심. 헛구역질 반복, 침 흘림.",
        "action": "응급의학과", "checkup": False, "red_flags": ["이물 섭취 의심", "반복 구역질"],
        "chat": [
            ("user", "두부가 장난감 조각을 삼킨 것 같아요. 자꾸 헛구역질을 해요."),
            ("assistant", "지금 호흡은 정상인가요? 삼킨 물질의 종류와 크기, 삼킨 시각을 알려주세요. 호흡곤란이 있으면 바로 병원으로 와주세요."),
            ("user", "숨은 쉬는데 계속 켁켁대고 침을 흘려요. 30분쯤 전이에요."),
            ("assistant", "이물 섭취가 의심되는 응급 상황입니다. 억지로 토하게 하지 마시고 가까운 응급 진료가 가능한 병원으로 즉시 내원해 주세요."),
        ],
        "followups": ["병원 가는 중이에요.", "X-ray 찍고 경과 보기로 했어요."],
        "vet_memo": "이물 섭취 의심, 반복적 구역질·유연. 응급 영상검사 시행 권고. 내시경/수술 가능성 사전 설명.",
    },
    {
        "key": "senior_anorexia", "species": ["dog"], "complaint": "노령견 식욕 저하",
        "keywords": ["노령견", "식욕 저하", "활력 감소"], "urgency": ("ORANGE", 2),
        "suspected": ["노령성 식욕 부진 — 기저질환 확인 필요"],
        "summary": "13세 노령견, 3일째 식사량 절반 이하, 활력 감소. 구토 없음.",
        "action": "내과", "checkup": False, "red_flags": ["지속 식욕 저하"],
        "chat": [
            ("user", "우리 강아지가 13살인데 며칠째 밥을 잘 안 먹고 기운이 없어요."),
            ("assistant", "물은 마시는지, 체중 변화나 구토·설사가 있는지, 평소 복용 약이 있는지 알려주세요."),
            ("user", "물은 조금 마시고 약은 심장약 먹고 있어요."),
            ("assistant", "노령에서 식욕 저하는 기저질환 신호일 수 있어요. 빠른 시일 내 혈액검사를 포함한 진료를 권장드립니다."),
        ],
        "followups": ["오늘은 간식은 조금 먹었어요.", "여전히 사료는 잘 안 먹어요."],
        "vet_memo": "13세령, 3일간 식욕 저하·활력 감소, 심장약 복용 중. 노령 기저질환 감별 위해 혈액·영상 검사 권고.",
    },
    {
        "key": "cat_urination", "species": ["cat"], "complaint": "고양이 배뇨 이상",
        "keywords": ["배뇨 이상", "화장실 들락거림", "소변량 감소"], "urgency": ("ORANGE", 2),
        "suspected": ["고양이 하부요로 질환(FLUTD) 의심"],
        "summary": "수컷 고양이, 화장실을 반복해서 들락거리지만 소변량 적음. 통증성 발성.",
        "action": "비뇨기과", "checkup": False, "red_flags": ["요폐 의심", "수컷 배뇨 곤란"],
        "chat": [
            ("user", "수컷 고양이인데 화장실을 계속 들락거리는데 소변은 거의 안 나와요."),
            ("assistant", "마지막으로 소변을 정상적으로 본 게 언제인가요? 배를 만지면 아파하거나 우는지 알려주세요. 수컷의 요폐는 응급입니다."),
            ("user", "어제 저녁 이후로 거의 못 본 것 같고 끙끙대요."),
            ("assistant", "요도 폐색이 의심되는 응급 상황일 수 있어요. 지체하지 마시고 바로 내원해 주세요."),
        ],
        "followups": ["병원에서 처치받고 소변 나왔어요.", "처방식으로 바꿨어요."],
        "vet_memo": "수컷 묘 빈뇨·잔뇨·통증성 발성. FLUTD/요도폐색 의심으로 즉각 평가. 카테터 처치 가능성 설명.",
    },
    {
        "key": "rabbit_anorexia", "species": ["rabbit"], "complaint": "토끼 식욕 부진",
        "keywords": ["토끼", "식욕 부진", "변 감소"], "urgency": ("ORANGE", 2),
        "suspected": ["토끼 위장정체(GI stasis) 의심"],
        "summary": "토끼가 하루 넘게 건초를 안 먹고 변이 거의 없음. 웅크림.",
        "action": "특수동물진료", "checkup": False, "red_flags": ["토끼 식이 중단", "변 생산 중단"],
        "chat": [
            ("user", "토끼가 어제부터 건초를 안 먹고 똥도 거의 안 싸요."),
            ("assistant", "마지막으로 먹은 시간과 변 크기 변화, 웅크리거나 이갈이를 하는지 알려주세요. 토끼의 식이 중단은 빠른 진료가 필요합니다."),
            ("user", "어제 아침 이후로 거의 안 먹고 웅크려 있어요."),
            ("assistant", "토끼 위장정체가 의심됩니다. 특수동물 진료가 가능한 병원으로 빠르게 내원해 주세요."),
        ],
        "followups": ["병원에서 처치 후 건초를 조금 먹어요.", "변이 다시 나오기 시작했어요."],
        "vet_memo": "토끼 24시간 이상 식이/배변 중단, 웅크림. GI stasis 의심으로 수액·위장운동 촉진 처치 및 영상 검사.",
    },
    {
        "key": "hamster_wound", "species": ["hamster"], "complaint": "햄스터 피부 상처",
        "keywords": ["햄스터", "피부 상처", "긁음"], "urgency": ("YELLOW", 3),
        "suspected": ["피부 외상/국소 감염 가능성"],
        "summary": "햄스터 옆구리에 작은 상처와 털 빠짐. 활력은 보통.",
        "action": "특수동물진료", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "햄스터 옆구리에 상처가 생기고 털이 빠졌어요."),
            ("assistant", "상처 크기와 진물 여부, 케이지 환경(쳇바퀴/바닥재)을 알려주세요. 사진이 있으면 첨부해 주세요."),
            ("user", "작은 상처고 진물은 조금 있어요. 쳇바퀴를 많이 타요."),
            ("assistant", "마찰성 상처나 국소 감염일 수 있어요. 환경을 점검하시고 특수동물 진료에서 확인받아 보세요."),
        ],
        "followups": ["상처 부위가 마르기 시작했어요.", "털 빠진 곳이 더 번지진 않았어요."],
        "vet_memo": "햄스터 측복부 표재성 상처·국소 탈모, 경미한 삼출. 외상/마찰 가능성으로 환경 교정 및 국소 처치.",
    },
    {
        "key": "parrot_feather", "species": ["parrot"], "complaint": "앵무새 깃털 빠짐",
        "keywords": ["앵무새", "깃털 빠짐", "깃털 뽑기"], "urgency": ("YELLOW", 3),
        "suspected": ["깃털 손상/행동성 깃털 뽑기 가능성"],
        "summary": "앵무새 가슴 깃털이 부분적으로 빠지고 스스로 깃털을 뽑는 행동 관찰.",
        "action": "특수동물진료", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "앵무새가 가슴 깃털을 자꾸 뽑고 빠진 자리가 생겼어요."),
            ("assistant", "빠진 부위와 시작 시기, 환경 변화(조도/스트레스)나 피부 발적이 있는지 알려주세요."),
            ("user", "가슴 쪽이고 2주쯤 됐어요. 최근에 케이지 위치를 옮겼어요."),
            ("assistant", "환경 변화로 인한 행동성 깃털 뽑기 가능성도 있어요. 조류 진료가 가능한 병원에서 피부와 행동을 함께 살펴보세요."),
        ],
        "followups": ["케이지 자리 돌려놓으니 조금 나아졌어요.", "아직 가끔 깃털을 만져요."],
        "vet_memo": "흉부 부분 탈우(脫羽)·자가 깃털 손상, 환경 변화 이력. 피부/행동 원인 감별 위해 검사 및 환경 상담.",
    },
    # ── 추가: 지식인 Q&A / 실제 문진 스타일 케이스 ──────────────────────
    {
        "key": "eye_redness", "species": ["dog", "cat"], "complaint": "눈 충혈과 눈곱",
        "keywords": ["눈 충혈", "눈곱", "눈 깜빡임"], "urgency": ("YELLOW", 3),
        "suspected": ["결막염 의심", "안구 자극 가능성"],
        "summary": "이틀째 한쪽 눈 충혈과 노란 눈곱, 자주 깜빡이고 앞발로 비빔.",
        "action": "안과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "강아지 한쪽 눈이 빨갛고 눈곱이 자꾸 껴요. 자꾸 비비려고 해요."),
            ("assistant", "어느 쪽 눈인지, 눈곱 색과 양, 눈을 못 뜨거나 부었는지 알려주세요. 사진이 있으면 첨부해 주세요."),
            ("user", "오른쪽이고 노란 눈곱이에요. 뜨긴 하는데 자주 깜빡여요."),
            ("assistant", "결막 자극이 의심돼요. 비비지 못하게 해주시고, 눈을 아예 못 뜨거나 각막이 뿌예지면 바로 내원해 주세요."),
        ],
        "followups": ["안약 넣으니 충혈이 좀 가라앉았어요.", "눈곱이 줄었어요."],
        "vet_memo": "우안 결막 충혈·점액성 안분비물, 소양감. 결막염 의심으로 안과 검사 및 점안 처치 권고.",
    },
    {
        "key": "patella", "species": ["dog"], "complaint": "뒷다리를 들고 깡총 뜀(슬개골 의심)",
        "keywords": ["슬개골", "깡총 걸음", "다리 들기"], "urgency": ("YELLOW", 3),
        "suspected": ["슬개골 탈구 의심"],
        "summary": "소형견, 걷다가 가끔 뒷다리를 들고 깡총 뛰다 다시 정상 보행. 통증 반응은 경미.",
        "action": "정형외과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "소형견인데 가끔 뒷다리를 들고 깡총깡총 뛰다가 또 멀쩡히 걸어요."),
            ("assistant", "어느 쪽 다리인지, 점프나 미끄러운 바닥에서 더 그러는지, 만질 때 아파하는지 알려주세요."),
            ("user", "양쪽 다 가끔 그래요. 마룻바닥에서 더 그런 것 같아요."),
            ("assistant", "슬개골 관련 보행 이상이 의심돼요. 미끄럼 방지 매트를 깔아주시고 진료 때 슬개골 단계 검사를 받아보세요."),
        ],
        "followups": ["미끄럼 매트 깔아주니 덜 그래요.", "계단은 안고 다녀요."],
        "vet_memo": "간헐적 후지 거상·skipping gait, 소형견. 슬개골 탈구(MPL) 의심으로 촉진·등급 평가 및 영상 권고.",
    },
    {
        "key": "parasite", "species": ["dog", "cat"], "complaint": "몸에서 진드기/벌레 발견",
        "keywords": ["진드기", "외부기생충", "긁음"], "urgency": ("GREEN", 4),
        "suspected": ["외부기생충(진드기) 부착", "예방 상담 필요"],
        "summary": "산책 후 목덜미에서 진드기 1마리 발견, 그 주변을 긁음. 발열·무기력 없음.",
        "action": "예방의학", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "산책 갔다 왔더니 목덜미에 진드기 같은 게 붙어 있어요."),
            ("assistant", "크기와 개수, 무리하게 떼지는 않으셨는지 알려주세요. 잘못 떼면 입 부분이 남을 수 있어요."),
            ("user", "콩알만 한 거 하나예요. 아직 안 뗐어요."),
            ("assistant", "억지로 비틀어 떼지 마시고, 진료 때 안전하게 제거하고 외부기생충 예방약을 함께 상담받으시길 권해요."),
        ],
        "followups": ["병원에서 떼고 예방약 발랐어요.", "긁는 건 줄었어요."],
        "vet_memo": "경부 진드기 부착 1개체, 국소 소양감. 안전 제거 및 외부기생충 예방 프로토콜 상담.",
    },
    {
        "key": "senior_cat_weightloss", "species": ["cat"], "complaint": "노령묘 체중 감소와 식욕 저하",
        "keywords": ["노령묘", "체중 감소", "식욕 저하", "물 많이 마심"], "urgency": ("ORANGE", 2),
        "suspected": ["노령성 대사 질환 가능성 — 검사 필요"],
        "summary": "14세 고양이, 한 달간 체중 감소와 식욕 저하, 물을 평소보다 많이 마심.",
        "action": "내과", "checkup": False, "red_flags": ["지속 체중 감소", "다음다뇨"],
        "chat": [
            ("user", "14살 고양이인데 요즘 살이 빠지고 밥도 잘 안 먹어요. 물은 엄청 많이 마셔요."),
            ("assistant", "체중 변화 기간, 소변량 변화, 구토가 있는지 알려주세요. 노령묘에서 다음다뇨는 검사가 필요한 신호예요."),
            ("user", "한 달쯤 됐고 화장실 소변 덩어리가 커졌어요."),
            ("assistant", "노령묘 대사 질환 가능성이 있어 혈액·소변 검사를 권장드려요. 빠른 시일 내 진료를 잡아보세요."),
        ],
        "followups": ["검사 예약했어요.", "그래도 캔은 조금 먹어요."],
        "vet_memo": "14세령, 1개월 체중 감소·식욕 저하·다음다뇨. 노령 대사질환 감별 위해 혈액/소변 검사 권고.",
    },
    {
        "key": "neuter_consult", "species": ["dog", "cat", "rabbit"], "complaint": "중성화 수술 상담",
        "keywords": ["중성화", "수술 상담", "시기"], "urgency": ("GREEN", 4),
        "suspected": ["중성화 시기/절차 상담"],
        "summary": "중성화 수술 시기와 준비 사항 문의. 현재 건강 이상 없음.",
        "action": "외과", "checkup": True, "red_flags": [],
        "chat": [
            ("user", "중성화 수술을 언제 하는 게 좋을지 상담받고 싶어요."),
            ("assistant", "나이와 몸무게, 최근 접종/건강 상태를 알려주시면 적절한 시기와 준비를 안내해 드릴게요."),
            ("user", "7개월 됐고 건강해요. 접종도 다 했어요."),
            ("assistant", "수술 전 신체검사와 금식 안내가 필요해요. 일정을 잡아 드릴 테니 자세한 절차는 내원 시 설명드릴게요."),
        ],
        "followups": ["수술 날짜 잡았어요.", "전날 금식 잘 시킬게요."],
        "vet_memo": "무증상 중성화 상담. 수술 전 신체검사·기초 혈액검사 및 금식 안내 예정.",
    },
    {
        "key": "nail_injury", "species": ["dog", "cat"], "complaint": "발톱이 부러지고 발을 듦",
        "keywords": ["발톱 부러짐", "출혈", "발 듦"], "urgency": ("YELLOW", 3),
        "suspected": ["발톱 손상/출혈", "이차 감염 가능성"],
        "summary": "발톱 하나가 부러져 약간 피가 났고 그 발을 들고 다님. 핥으려 함.",
        "action": "외과", "checkup": False, "red_flags": [],
        "chat": [
            ("user", "발톱이 부러졌는지 피가 조금 났고 그 발을 들고 다녀요."),
            ("assistant", "출혈이 멈췄는지, 발톱이 흔들리거나 살이 보이는지, 계속 핥는지 알려주세요."),
            ("user", "피는 멎었는데 자꾸 핥아요."),
            ("assistant", "핥지 못하게 해주시고 깨끗이 유지해 주세요. 발톱이 들떠 있거나 붓고 진물이 나면 처치가 필요해요."),
        ],
        "followups": ["핥는 건 줄었어요.", "부기는 없어요."],
        "vet_memo": "발톱 파절·경미한 출혈, 자가 손상 시도. 발톱 처치 및 이차 감염 예방, 필요 시 제거 안내.",
    },
]
CASE_BY_SPECIES: dict[str, list[dict]] = {}
for _c in CASES:
    for _sp in _c["species"]:
        CASE_BY_SPECIES.setdefault(_sp, []).append(_c)


# ── 삭제(데모 마커 범위) ─────────────────────────────────────────────────
async def _ids(db: AsyncSession, sql: str, **params) -> list[int]:
    rows = (await db.execute(text(sql), params)).fetchall()
    return [r[0] for r in rows]


async def delete_demo_data(db: AsyncSession) -> None:
    """데모 마커가 붙은 행만 FK 안전 순서로 삭제한다. 실제 사용자 데이터는 건드리지 않는다."""
    user_ids = await _ids(db, 'SELECT userid FROM "userDB" WHERE loginid LIKE :p', p=f"%@{DEMO_DOMAIN}")
    hosp_ids = await _ids(db, 'SELECT hospitalid FROM "hospitalDB" WHERE business_number LIKE :p', p=f"{DEMO_BIZ_PREFIX}%")
    doc_ids = await _ids(db, 'SELECT doctorid FROM "doctorDB" WHERE hospitalid = ANY(:ids)', ids=hosp_ids or [-1])
    pet_ids = await _ids(db, 'SELECT petid FROM "petDB" WHERE userid = ANY(:ids)', ids=user_ids or [-1])
    emr_ids = await _ids(db, 'SELECT emrid FROM "guardianDB" WHERE petid = ANY(:ids)', ids=pet_ids or [-1])
    demr_ids = await _ids(
        db,
        'SELECT doctor_emrid FROM "doctorEMRDB" WHERE petid = ANY(:p) OR doctorid = ANY(:d)',
        p=pet_ids or [-1], d=doc_ids or [-1],
    )
    sched_ids = await _ids(
        db,
        'SELECT scheduleid FROM "scheduleDB" WHERE emrid = ANY(:e) OR doctorid = ANY(:d)',
        e=emr_ids or [-1], d=doc_ids or [-1],
    )

    # children → parents
    stmts = [
        # 평가/에이전트 산출물(스케줄·문진을 참조). 스케줄/guardian 삭제 전에 먼저 비워야 FK 위반이 안 난다.
        ('DELETE FROM "validation_resultDB" WHERE emrid = ANY(:e) OR scheduleid = ANY(:s)',
         {"e": emr_ids or [-1], "s": sched_ids or [-1]}),
        ('DELETE FROM "agent_pipeline_resultDB" WHERE emrid = ANY(:e) OR scheduleid = ANY(:s) '
         'OR petid = ANY(:p) OR userid = ANY(:u)',
         {"e": emr_ids or [-1], "s": sched_ids or [-1], "p": pet_ids or [-1], "u": user_ids or [-1]}),
        ('DELETE FROM "photo_analysisDB" WHERE emrid = ANY(:e)', {"e": emr_ids or [-1]}),
        ('DELETE FROM "prescriptionDB" WHERE doctor_emrid = ANY(:x)', {"x": demr_ids or [-1]}),
        ('DELETE FROM "doctorEMRDB" WHERE doctor_emrid = ANY(:x)', {"x": demr_ids or [-1]}),
        ('DELETE FROM "doctor_alarmDB" WHERE doctorid = ANY(:d) OR scheduleid = ANY(:s)',
         {"d": doc_ids or [-1], "s": sched_ids or [-1]}),
        ('DELETE FROM "reportDB" WHERE emrid = ANY(:e) OR scheduleid = ANY(:s)',
         {"e": emr_ids or [-1], "s": sched_ids or [-1]}),
        ('DELETE FROM "followupDB" WHERE emrid = ANY(:e) OR userid = ANY(:u)',
         {"e": emr_ids or [-1], "u": user_ids or [-1]}),
        ('DELETE FROM "triage_resultDB" WHERE emrid = ANY(:e)', {"e": emr_ids or [-1]}),
        ('DELETE FROM "chat_historyDB" WHERE userid = ANY(:u)', {"u": user_ids or [-1]}),
        ('DELETE FROM "scheduleDB" WHERE scheduleid = ANY(:s)', {"s": sched_ids or [-1]}),
        ('DELETE FROM "guardianDB" WHERE emrid = ANY(:e)', {"e": emr_ids or [-1]}),
        ('DELETE FROM "petDB" WHERE petid = ANY(:p)', {"p": pet_ids or [-1]}),
        ('DELETE FROM "guardian_hospitalDB" WHERE userid = ANY(:u) OR hospitalid = ANY(:h)',
         {"u": user_ids or [-1], "h": hosp_ids or [-1]}),
        ('DELETE FROM "vet_weekly_scheduleDB" WHERE doctorid = ANY(:d)', {"d": doc_ids or [-1]}),
        ('DELETE FROM "doctor_profileDB" WHERE doctorid = ANY(:d)', {"d": doc_ids or [-1]}),
        ('DELETE FROM "doctorDB" WHERE doctorid = ANY(:d)', {"d": doc_ids or [-1]}),
        ('DELETE FROM "hospital_weekly_scheduleDB" WHERE hospitalid = ANY(:h)', {"h": hosp_ids or [-1]}),
        ('DELETE FROM "hospital_closed_datesDB" WHERE hospitalid = ANY(:h)', {"h": hosp_ids or [-1]}),
        ('DELETE FROM "hospital_profileDB" WHERE hospitalid = ANY(:h)', {"h": hosp_ids or [-1]}),
        ('UPDATE "clinic_signup_requestDB" SET created_hospitalid = NULL WHERE created_hospitalid = ANY(:h)',
         {"h": hosp_ids or [-1]}),
        ('DELETE FROM "petDB" WHERE userid = ANY(:u)', {"u": user_ids or [-1]}),
        ('DELETE FROM "userDB" WHERE userid = ANY(:u)', {"u": user_ids or [-1]}),
        ('DELETE FROM "hospitalDB" WHERE hospitalid = ANY(:h)', {"h": hosp_ids or [-1]}),
        ('DELETE FROM "admin_userDB" WHERE loginid LIKE :p', {"p": f"%@{DEMO_DOMAIN}"}),
    ]
    for sql, params in stmts:
        await db.execute(text(sql), params)
    await db.commit()
    print(
        f"[seed_demo] 기존 데모 데이터 삭제: 보호자 {len(user_ids)} / 병원 {len(hosp_ids)} / "
        f"수의사 {len(doc_ids)} / 반려동물 {len(pet_ids)} / 문진레코드 {len(emr_ids)}"
    )


# ── 생성 ────────────────────────────────────────────────────────────────
def _slots_for_day(hours: tuple) -> list[time]:
    """영업시간(점심 제외)에서 30분 슬롯 시작시각 목록."""
    start, end, lunch_s, lunch_e = hours
    slots: list[time] = []
    cur = datetime.combine(date.today(), start)
    end_dt = datetime.combine(date.today(), end)
    while cur + timedelta(minutes=DEFAULT_DURATION_MIN) <= end_dt:
        t = cur.time()
        if not (lunch_s and lunch_e and lunch_s <= t < lunch_e):
            slots.append(t)
        cur += timedelta(minutes=DEFAULT_DURATION_MIN)
    return slots


async def seed(db: AsyncSession, guardian_profiles: list[tuple[str, str, str]],
               scale: float = 1.0) -> dict:
    counts = {k: 0 for k in
              ["admin", "hospital", "doctor", "guardian", "pet", "appointment",
               "triage", "chat", "followup", "emr"]}

    # 마스터 id 조회(없으면 첫 행 fallback)
    async def _cat_id(code: int) -> int | None:
        row = (await db.execute(select(CategoryMaster).where(CategoryMaster.code == code))).scalar_one_or_none()
        if not row:
            row = (await db.execute(select(CategoryMaster))).scalars().first()
        return row.id if row else None

    async def _tri_id(code: int) -> int | None:
        row = (await db.execute(select(TriageMaster).where(TriageMaster.code == code))).scalar_one_or_none()
        return row.id if row else None

    cat_general = await _cat_id(2)   # 일반진료
    cat_checkup = await _cat_id(1)   # 정기검진
    tri_by_num = {1: await _tri_id(1), 2: await _tri_id(2), 3: await _tri_id(3), 4: await _tri_id(3)}

    now = datetime.now(KST)
    today = now.date()

    # 1) 운영진 계정 ---------------------------------------------------------
    admins = [
        (f"admin@{DEMO_DOMAIN}", PW_ADMIN, "메디포 운영관리자"),
        (f"ops@{DEMO_DOMAIN}", PW_ADMIN, "메디포 운영매니저"),
    ]
    for loginid, pw, name in admins:
        db.add(AdminUser(loginid=loginid, password=hash_password(pw), name=name))
        counts["admin"] += 1
    await db.flush()

    # 2) 병원 + 프로필 + 영업시간/휴무 + 수의사 -----------------------------
    hosp_records: list[dict] = []  # {hospitalid, doctors:[{doctorid, days, name, specialty}], def}
    for h_i, hdef in enumerate(HOSPITALS):
        hosp = Hospital(
            hospital_name=hdef["name"],
            hospital_address=hdef["address"],
            hospital_number=hdef["phone"],
            business_number=hdef["biz"],
            owner_email=hdef["owner_email"],
            loginid=hdef["login"],
            password=hash_password(PW_VET_INITIAL),
            is_initial_password=True,   # 운영팀 발급 → 첫 로그인 시 비밀번호 변경 필요
            is_active=True,
        )
        db.add(hosp)
        await db.flush()
        counts["hospital"] += 1

        db.add(HospitalProfile(
            hospitalid=hosp.hospitalid,
            tagline=hdef["tagline"],
            intro=hdef["intro"],
            banner_image_url=hospital_banner_url(h_i),   # placeholder(공개 이미지). 사내 이미지로 교체 가능.
            banner_image_position="50% 50%",
            features=hdef["features"] + [f"진료과목:{'·'.join(hdef['departments'])}",
                                         f"진료가능:{'·'.join(hdef['species'])}",
                                         "응급가능" if hdef["emergency"] else "응급불가"],
        ))

        # 병원 주간 영업시간 (월=0 ~ 일=6)
        for dow in range(7):
            if dow <= 4:
                s, e, ls, le = hdef["weekday_hours"]
                is_open = True
            elif dow == 5:
                s, e, ls, le = hdef["sat_hours"]
                is_open = True
            else:
                s = e = ls = le = None
                is_open = hdef["sun_open"]
                if is_open:
                    s, e, ls, le = hdef["weekday_hours"]
            db.add(HospitalWeeklySchedule(
                hospitalid=hosp.hospitalid, day_of_week=dow, is_open=is_open,
                start_time=s if is_open else None, end_time=e if is_open else None,
                lunch_start=ls if is_open else None, lunch_end=le if is_open else None,
            ))

        # 휴무일(신정 등)
        for cd in hdef["closed_dates"]:
            if cd == "__new_year__":
                d = date(today.year + 1, 1, 1)
            else:
                d = date.fromisoformat(cd)
            db.add(HospitalClosedDate(hospitalid=hosp.hospitalid, date=d))

        # 수의사 + 프로필 + 주간 가능시간
        doc_list = []
        for i, ddef in enumerate(DOCTORS[hdef["biz"]], start=1):
            doc = Doctor(
                hospitalid=hosp.hospitalid,
                doctor_name=ddef["name"],
                license_number=f"{DEMO_LICENSE_PREFIX}{hdef['biz'][-4:]}-{i}",
                email=f"{hdef['biz'].lower()}-vet{i}@{DEMO_DOMAIN}",
                is_active=True,
            )
            db.add(doc)
            await db.flush()
            counts["doctor"] += 1

            db.add(DoctorProfile(
                doctorid=doc.doctorid,
                specialty=ddef["specialty"],
                education=ddef["edu"],
                bio=f"{hdef['name']} {ddef['specialty']} 담당. {ddef['career']}. "
                    f"{', '.join(ddef['areas'])} 분야를 진료합니다.",
                specialty_areas=ddef["areas"],
                profile_image_url=doctor_avatar_url(doc.doctorid),  # placeholder(공개 초상). 사내 이미지로 교체 가능.
                profile_image_position="50% 50%",
            ))

            # 수의사 가능 요일 = 병원 영업일 ∩ 의사 근무일
            for dow in range(7):
                hosp_open = (dow <= 4) or (dow == 5) or (dow == 6 and hdef["sun_open"])
                works = (dow in ddef["days"]) and hosp_open
                if dow <= 4:
                    s, e, ls, le = hdef["weekday_hours"]
                elif dow == 5:
                    s, e, ls, le = hdef["sat_hours"]
                else:
                    s, e, ls, le = hdef["weekday_hours"]
                db.add(VetWeeklySchedule(
                    doctorid=doc.doctorid, day_of_week=dow, is_open=works,
                    start_time=s if works else None, end_time=e if works else None,
                    lunch_start=ls if works else None, lunch_end=le if works else None,
                ))
            doc_list.append({"doctorid": doc.doctorid, "days": ddef["days"],
                             "name": ddef["name"], "specialty": ddef["specialty"]})

        hosp_records.append({"hospitalid": hosp.hospitalid, "def": hdef, "doctors": doc_list})
    await db.flush()

    # 3) 보호자 + 기본병원 연결 + 반려동물 ----------------------------------
    guardians: list[dict] = []  # {userid, name, hospital_idx, pets:[{petid, species_kr, species}], login, pw}
    for gi, (name, phone, addr) in enumerate(guardian_profiles):
        loginid = f"g{gi+1:02d}@{DEMO_DOMAIN}"
        user = User(
            loginid=loginid, password=hash_password(PW_GUARDIAN),
            name=name, phone=phone, address=addr,
        )
        db.add(user)
        await db.flush()
        counts["guardian"] += 1

        # 보호자 기본병원: 메디포(index 0)에 집중 배정(시연 계정이 메디포라서).
        hosp_weights = [GUARDIAN_HOSP_WEIGHTS[i] if i < len(GUARDIAN_HOSP_WEIGHTS) else 1.0
                        for i in range(len(hosp_records))]
        hosp_idx = RNG.choices(range(len(hosp_records)), weights=hosp_weights, k=1)[0]
        primary_hid = hosp_records[hosp_idx]["hospitalid"]
        db.add(GuardianHospital(userid=user.userid, hospitalid=primary_hid, is_primary=True))
        # 일부 보호자는 보조 병원도 연결
        if gi % 3 == 0:
            sec = hosp_records[(hosp_idx + 1) % len(hosp_records)]["hospitalid"]
            db.add(GuardianHospital(userid=user.userid, hospitalid=sec, is_primary=False))

        # 반려동물 1~3마리 — 종은 병원 제약 없이 전 종에서 가중 랜덤(다양성↑).
        n_pets = RNG.choice([1, 2, 2, 3])
        pets = []
        for _ in range(n_pets):
            species_kr = RNG.choices(SPECIES_KR, weights=SPECIES_WEIGHTS, k=1)[0]
            pool = PET_POOL[species_kr]
            wmin, wmax = pool["weight"]
            age_years = RNG.randint(1, 13)
            birth = today - timedelta(days=age_years * 365 + RNG.randint(0, 300))
            pet = Pet(
                userid=user.userid,
                petname=RNG.choice(pool["names"]),
                species=pool["species"],
                breed=RNG.choice(pool["breeds"]),
                gender=RNG.choice(["male", "female"]),
                birth_date=birth,
                weight_kg=Decimal(str(round(RNG.uniform(wmin, wmax), 2))),
                is_neutered=RNG.choice([True, False]),
                checkup_date=(today - timedelta(days=RNG.randint(30, 400))) if RNG.random() < 0.6 else None,
                profile_image=None,        # 아래 flush 후 petid로 placeholder URL 설정
                original_image=None,
                doodle_strokes=None,
                notes=(
                    f"특이사항: {RNG.choice(PET_NOTES_BITS['note'])} / "
                    f"알러지: {RNG.choice(PET_NOTES_BITS['allergy'])} / "
                    f"과거병력: {RNG.choice(PET_NOTES_BITS['history'])} / "
                    f"복용약: {RNG.choice(PET_NOTES_BITS['meds'])}"
                ),
            )
            db.add(pet)
            await db.flush()
            pet.profile_image = pet_photo_url(pool["species"], pet.petid)  # placeholder(종별 공개 사진)
            counts["pet"] += 1
            pets.append({"petid": pet.petid, "species_kr": species_kr, "species": pool["species"],
                         "name": pet.petname})
        guardians.append({"userid": user.userid, "name": name, "hosp_idx": hosp_idx,
                          "pets": pets, "login": loginid})
    await db.flush()

    # 병원별 소속 보호자 인덱스
    guardians_by_hosp: dict[int, list[dict]] = {}
    for g in guardians:
        guardians_by_hosp.setdefault(g["hosp_idx"], []).append(g)

    # 4) 예약 + 문진 + 채팅 + followup + EMR --------------------------------
    # 의사별 사용 슬롯 추적(겹침 방지: 동일 의사 동일 시작시각 금지)
    used_slots: dict[int, set] = {}

    def pick_slot(doctor: dict, target_date: date, hdef: dict) -> datetime | None:
        dow = target_date.weekday()
        if dow not in doctor["days"]:
            return None
        if dow == 6 and not hdef["sun_open"]:
            return None
        hours = hdef["weekday_hours"] if dow <= 4 else (hdef["sat_hours"] if dow == 5 else hdef["weekday_hours"])
        candidates = _slots_for_day(hours)
        RNG.shuffle(candidates)
        used = used_slots.setdefault(doctor["doctorid"], set())
        for t in candidates:
            key = (target_date, t.hour, t.minute)
            if key not in used:
                used.add(key)
                return datetime.combine(target_date, t).replace(tzinfo=KST)
        return None

    def workday_offset(base: date, delta_days: int, doctor: dict, hdef: dict) -> date | None:
        d = base + timedelta(days=delta_days)
        # 의사 근무 + 병원 영업일 보정(최대 7일 탐색)
        for _ in range(7):
            dow = d.weekday()
            hosp_open = (dow <= 4) or (dow == 5) or (dow == 6 and hdef["sun_open"])
            if dow in doctor["days"] and hosp_open:
                return d
            d += timedelta(days=1 if delta_days >= 0 else -1)
        return None

    async def make_appointment(g: dict, pet: dict, doctor: dict, hdef: dict,
                               when: datetime, status: str, case: dict,
                               with_triage: bool, cancel_reason: str | None = None):
        # 4-1) 문진/진료 레코드(guardianDB = emrid)
        is_checkup = case.get("checkup")
        guardian_row = Guardian(
            petid=pet["petid"],
            category_id=cat_checkup if is_checkup else cat_general,
            triage_id=tri_by_num.get(case["urgency"][1]) if with_triage else None,
            date=when.date(),
            memo=cancel_reason or case["complaint"],
        )
        db.add(guardian_row)
        await db.flush()
        emrid = guardian_row.emrid
        counts["appointment"] += 1  # 카운트는 schedule 기준으로 아래에서

        # 4-2) 예약(schedule) — 생성시각은 예약시각 이전이되 현재를 넘지 않게 보정
        created = min(when - timedelta(days=RNG.randint(1, 5), hours=RNG.randint(0, 8)),
                      now - timedelta(minutes=RNG.randint(5, 600)))
        sched = Schedule(
            emrid=emrid,
            doctorid=doctor["doctorid"],
            duration_min=DEFAULT_DURATION_MIN,
            confirmed_time=when,
            confirmed_end_time=when + timedelta(minutes=DEFAULT_DURATION_MIN),
            status=status,
            created_at=created,
        )
        if status == "CANCELLED":
            sched.deleted_at = when - timedelta(hours=RNG.randint(2, 24))
            guardian_row.deleted_at = sched.deleted_at
        db.add(sched)
        await db.flush()

        # 4-3) 문진 결과(triage_result) — AI 문진 케이스만
        if with_triage:
            lvl, num = case["urgency"]
            db.add(TriageResult(
                emrid=emrid,
                urgency_level=lvl,
                urgency_level_num=num,
                vtl_basis=f"보호자 진술 기반 1차 분류: {case['summary']}",
                red_flags=case["red_flags"] or None,
                chief_complaint=case["complaint"],
                symptom_onset="최근 1~3일" if num >= 3 else "수 시간~1일 내",
                symptom_keywords=case["keywords"],
                suspected_diseases=case["suspected"],
                symptom_summary=case["summary"],
                recommended_action=f"{case['action']} 진료 권장",
                matched_discriminators=None,
                extracted_variables=None,
                vision_evidence=None,
                rag_context=None,
                created_at=when - timedelta(days=RNG.randint(1, 4)),
            ))
            counts["triage"] += 1

            # 4-4) 채팅 내역(chat_history) — 문진 흐름
            messages = [{"role": r, "content": c, "image_url": None} for r, c in case["chat"]]
            db.add(ChatHistory(
                userid=g["userid"],
                petid=pet["petid"],
                emrid=emrid,
                messages=messages,
                keywords=case["keywords"],
                title=f"{pet['name']} {case['complaint']} 문진",
                orch_state=None,
                is_complete=True,
                is_deleted=False,
                created_at=when - timedelta(days=RNG.randint(1, 4)),
            ))
            counts["chat"] += 1

        # 4-5) followup(경과 기록) — 완료/확정 예약 중 일부
        if status in ("COMPLETED", "CONFIRMED") and case.get("followups") and RNG.random() < 0.6:
            n_fu = RNG.randint(1, min(2, len(case["followups"])))
            for k in range(n_fu):
                msg = case["followups"][k]
                fu_time = when + timedelta(days=k + 1, hours=RNG.randint(0, 6))
                if fu_time > now:
                    fu_time = now - timedelta(hours=RNG.randint(1, 12))
                db.add(Followup(
                    emrid=emrid,
                    userid=g["userid"],
                    images=[],                # TODO: 경과 사진 수동 삽입(빈 배열로 보관)
                    message=msg,
                    ai_summary=f"보호자 경과 보고: {msg} (특이 악화 징후 없음, 경과 관찰 권고)",
                    emergency_alert=(case["urgency"][1] == 1),
                    created_at=fu_time,
                ))
                counts["followup"] += 1

        # 4-6) 의사 진료기록(EMR) — 완료된 예약
        if status == "COMPLETED":
            db.add(EMR(
                petid=pet["petid"],
                doctorid=doctor["doctorid"],
                scheduleid=sched.scheduleid,
                vet_memo=case["vet_memo"],
                attachments=None,           # TODO: 검사 결과/사진 첨부 수동 삽입
                created_at=when + timedelta(minutes=40),
            ))
            counts["emr"] += 1

    # 병원별 예약 분포: 과거 완료/취소 + 오늘 + 이번주 + 미래
    # (각 병원: 오늘 5+, 이번주 15+, 완료 10+ 목표)
    for hrec in hosp_records:
        hdef = hrec["def"]
        hid = hrec["hospitalid"]
        docs = hrec["doctors"]
        hg = guardians_by_hosp.get(hosp_records.index(hrec), [])
        if not hg:
            continue
        # (반려동물, 보호자) 풀
        pet_pool = [(g, p) for g in hg for p in g["pets"]]
        if not pet_pool:
            continue

        def case_for(pet, urgent_bias=False):
            opts = CASE_BY_SPECIES.get(pet["species"], CASE_BY_SPECIES["dog"])
            if urgent_bias:
                urgent = [c for c in opts if c["urgency"][1] <= 2]
                if urgent:
                    return RNG.choice(urgent)
            return RNG.choice(opts)

        # 실제 운영 병원처럼 "약 한 달"(최근 ~25일 ~ 앞으로 ~30일)을 빽빽하게 채운다.
        # 좁은 기간에 많은 건수를 몰아넣어 캘린더가 매일 꽉 차 보이게 한다(병원별, scale 배수).
        # 의사 근무요일/슬롯 제약으로 일부는 미배치될 수 있어 넉넉히 시도한다.
        PAST_WINDOW = 25     # 최근 N일 이내 완료/취소
        FUTURE_WINDOW = 30   # 앞으로 N일 이내 예약(=꽉 찬 한 달)
        base_plan = [("past_completed", 130), ("past_cancelled", 26), ("today", 20),
                     ("upcoming", 320)]
        h_idx = hosp_records.index(hrec)
        h_weight = HOSP_APPT_WEIGHTS[h_idx] if h_idx < len(HOSP_APPT_WEIGHTS) else 0.35
        plan = [(k, max(1, round(q * scale * h_weight))) for k, q in base_plan]
        for kind, qty in plan:
            placed = 0
            attempts = 0
            while placed < qty and attempts < qty * 12:
                attempts += 1
                doctor = RNG.choice(docs)
                g, pet = RNG.choice(pet_pool)
                case = case_for(pet)
                with_triage = RNG.random() < 0.8     # 80%는 AI 문진 연결, 20%는 수의사 수동 예약
                if kind == "past_completed":
                    d = workday_offset(today, -RNG.randint(1, PAST_WINDOW), doctor, hdef)
                    status = "COMPLETED"
                    reason = None
                elif kind == "past_cancelled":
                    d = workday_offset(today, -RNG.randint(1, PAST_WINDOW), doctor, hdef)
                    status = "CANCELLED"
                    reason = RNG.choice(["보호자 일정 변경으로 취소", "증상 호전되어 취소", "병원 사정으로 일정 변경"])
                elif kind == "today":
                    d = today if (today.weekday() in doctor["days"] and
                                  ((today.weekday() <= 5) or hdef["sun_open"])) else None
                    # 오늘 이른 시간은 완료, 이후는 확정
                    status = None
                    reason = None
                else:  # upcoming — 앞으로 한 달치(오늘 다음날 ~ FUTURE_WINDOW일)
                    d = workday_offset(today, RNG.randint(1, FUTURE_WINDOW), doctor, hdef)
                    # 가까운 날짜는 확정 비중↑, 먼 날짜는 대기 비중↑(자연스러운 운영 패턴)
                    status = RNG.choice(["CONFIRMED", "CONFIRMED", "CONFIRMED", "예약대기"]
                                        if d and (d - today).days <= 10
                                        else ["CONFIRMED", "예약대기", "예약대기"])
                    reason = None
                if d is None:
                    continue
                when = pick_slot(doctor, d, hdef)
                if when is None:
                    continue
                if kind == "today":
                    if when.hour < now.hour:
                        status = "COMPLETED"
                        when = when  # 과거 시각이라 완료 처리
                    else:
                        status = "CONFIRMED"
                await make_appointment(g, pet, doctor, hdef, when, status, case, with_triage, reason)
                placed += 1

    # 5) 예약 없는 사전 상담 채팅 몇 건(현실감) -----------------------------
    for g in guardians[:6]:
        if not g["pets"]:
            continue
        pet = g["pets"][0]
        case = CASE_BY_SPECIES.get(pet["species"], CASE_BY_SPECIES["dog"])[0]
        messages = [{"role": r, "content": c, "image_url": None} for r, c in case["chat"][:2]]
        db.add(ChatHistory(
            userid=g["userid"], petid=pet["petid"], emrid=None,
            messages=messages, keywords=case["keywords"][:2],
            title=f"{pet['name']} 사전 상담", orch_state=None,
            is_complete=False, is_deleted=False,
            created_at=now - timedelta(days=RNG.randint(1, 10), hours=RNG.randint(0, 12)),
        ))
        counts["chat"] += 1

    await db.commit()
    return counts


# ── 검증 ────────────────────────────────────────────────────────────────
async def verify(db: AsyncSession) -> None:
    print("\n──────────── 검증 쿼리 ────────────")

    print("\n[병원별 수의사 수]")
    rows = (await db.execute(text("""
        SELECT h.hospital_name, count(d.doctorid)
        FROM "hospitalDB" h LEFT JOIN "doctorDB" d ON d.hospitalid = h.hospitalid
        WHERE h.business_number LIKE :p
        GROUP BY h.hospitalid, h.hospital_name ORDER BY h.hospitalid
    """), {"p": f"{DEMO_BIZ_PREFIX}%"})).fetchall()
    for name, n in rows:
        print(f"  - {name}: {n}명")

    print("\n[병원별 오늘 예약 수(활성)]")
    rows = (await db.execute(text("""
        SELECT h.hospital_name, count(*)
        FROM "scheduleDB" s
        JOIN "doctorDB" d ON d.doctorid = s.doctorid
        JOIN "hospitalDB" h ON h.hospitalid = d.hospitalid
        WHERE h.business_number LIKE :p
          AND s.deleted_at IS NULL AND s.status <> 'CANCELLED'
          AND (s.confirmed_time AT TIME ZONE 'Asia/Seoul')::date = (now() AT TIME ZONE 'Asia/Seoul')::date
        GROUP BY h.hospitalid, h.hospital_name ORDER BY h.hospitalid
    """), {"p": f"{DEMO_BIZ_PREFIX}%"})).fetchall()
    for name, n in rows:
        print(f"  - {name}: {n}건")

    print("\n[수의사별 이번 주 예약 수(활성)]")
    rows = (await db.execute(text("""
        SELECT d.doctor_name, count(*)
        FROM "scheduleDB" s
        JOIN "doctorDB" d ON d.doctorid = s.doctorid
        JOIN "hospitalDB" h ON h.hospitalid = d.hospitalid
        WHERE h.business_number LIKE :p
          AND s.deleted_at IS NULL AND s.status <> 'CANCELLED'
          AND date_trunc('week', s.confirmed_time AT TIME ZONE 'Asia/Seoul')
              = date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')
        GROUP BY d.doctorid, d.doctor_name ORDER BY count(*) DESC
    """), {"p": f"{DEMO_BIZ_PREFIX}%"})).fetchall()
    for name, n in rows:
        print(f"  - {name}: {n}건")

    print("\n[보호자별 반려동물 수]")
    rows = (await db.execute(text("""
        SELECT u.name, count(p.petid)
        FROM "userDB" u LEFT JOIN "petDB" p ON p.userid = u.userid
        WHERE u.loginid LIKE :p
        GROUP BY u.userid, u.name ORDER BY u.userid
    """), {"p": f"%@{DEMO_DOMAIN}"})).fetchall()
    for name, n in rows:
        print(f"  - {name}: {n}마리")

    print("\n[FK 누락 점검(고아 레코드 — 0이어야 정상)]")
    checks = {
        "petDB→userDB": 'SELECT count(*) FROM "petDB" p LEFT JOIN "userDB" u ON u.userid=p.userid WHERE u.userid IS NULL',
        "guardianDB→petDB": 'SELECT count(*) FROM "guardianDB" g LEFT JOIN "petDB" p ON p.petid=g.petid WHERE p.petid IS NULL',
        "scheduleDB→guardianDB": 'SELECT count(*) FROM "scheduleDB" s LEFT JOIN "guardianDB" g ON g.emrid=s.emrid WHERE g.emrid IS NULL',
        "scheduleDB→doctorDB": 'SELECT count(*) FROM "scheduleDB" s LEFT JOIN "doctorDB" d ON d.doctorid=s.doctorid WHERE d.doctorid IS NULL',
        "triage_resultDB→guardianDB": 'SELECT count(*) FROM "triage_resultDB" t LEFT JOIN "guardianDB" g ON g.emrid=t.emrid WHERE g.emrid IS NULL',
        "followupDB→guardianDB": 'SELECT count(*) FROM "followupDB" f LEFT JOIN "guardianDB" g ON g.emrid=f.emrid WHERE g.emrid IS NULL',
        "doctorEMRDB→scheduleDB": 'SELECT count(*) FROM "doctorEMRDB" e LEFT JOIN "scheduleDB" s ON s.scheduleid=e.scheduleid WHERE s.scheduleid IS NULL',
    }
    for label, sql in checks.items():
        n = (await db.execute(text(sql))).scalar()
        flag = "OK" if n == 0 else "!! 누락"
        print(f"  - {label}: {n} ({flag})")


# ── 메인 ────────────────────────────────────────────────────────────────
async def main(reset_only: bool, guardian_count: int, scale: float) -> None:
    _guard_environment()
    guardian_profiles = build_guardian_profiles(guardian_count)
    engine = create_async_engine(_to_async_url(DATABASE_URL), echo=False,
                                 connect_args={"statement_cache_size": 0})
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # 멱등성: 항상 기존 데모 데이터를 먼저 삭제한다.
        await delete_demo_data(db)
        if reset_only:
            print("[seed_demo] --reset-demo: 데모 데이터 삭제만 수행하고 종료합니다.")
            await engine.dispose()
            return
        print(f"[seed_demo] 보호자 {guardian_count}명, 예약 scale={scale} 로 생성합니다...")
        counts = await seed(db, guardian_profiles, scale)
        await verify(db)

    await engine.dispose()

    print("\n──────────── 생성/업데이트 요약 ────────────")
    print(f"  운영진(admin) : {counts['admin']}")
    print(f"  병원(hospital): {counts['hospital']}")
    print(f"  수의사(doctor): {counts['doctor']}")
    print(f"  보호자(user)  : {counts['guardian']}")
    print(f"  반려동물(pet) : {counts['pet']}")
    print(f"  예약(schedule): {counts['appointment']}")
    print(f"  문진(triage)  : {counts['triage']}")
    print(f"  채팅(chat)    : {counts['chat']}")
    print(f"  경과(followup): {counts['followup']}")
    print(f"  진료기록(EMR) : {counts['emr']}")

    print("\n──────────── 데모 로그인 계정 ────────────")
    print("운영진(회사·운영자 웹 http://localhost:5175):")
    print(f"  admin@{DEMO_DOMAIN} / {PW_ADMIN}")
    print(f"  ops@{DEMO_DOMAIN}   / {PW_ADMIN}")
    print(f"\n수의사(병원) 계정(수의사 웹 http://localhost:5174) — 초기 비밀번호 {PW_VET_INITIAL}, 첫 로그인 시 변경 필요:")
    for hdef in HOSPITALS:
        docs = ", ".join(d["name"] for d in DOCTORS[hdef["biz"]])
        print(f"  {hdef['login']} / {PW_VET_INITIAL}  ({hdef['name']} / 소속 수의사: {docs})")
    print(f"\n보호자 계정(보호자 앱 http://localhost:5173) — 공통 비밀번호 {PW_GUARDIAN}:")
    print(f"  계정 형식: g01@{DEMO_DOMAIN} ~ g{counts['guardian']:02d}@{DEMO_DOMAIN} (총 {counts['guardian']}명, 모두 비번 {PW_GUARDIAN})")
    print(f"  예시 → g01@{DEMO_DOMAIN} / {PW_GUARDIAN}")
    print("\n완료.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MediPaw 데모 데이터 시드")
    parser.add_argument("--reset-demo", action="store_true",
                        help="데모 마커 데이터만 삭제하고 종료(재생성 안 함)")
    parser.add_argument("--guardians", type=int, default=DEFAULT_GUARDIAN_COUNT,
                        help=f"생성할 보호자 수(기본 {DEFAULT_GUARDIAN_COUNT}, 1~99 권장)")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="병원별 예약량 배수(기본 1.0). 예: 1.5면 50%% 더 많이")
    args = parser.parse_args()
    asyncio.run(main(reset_only=args.reset_demo,
                     guardian_count=max(1, min(99, args.guardians)),
                     scale=max(0.1, args.scale)))
