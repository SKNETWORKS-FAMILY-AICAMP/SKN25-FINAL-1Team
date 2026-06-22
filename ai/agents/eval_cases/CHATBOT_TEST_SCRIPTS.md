# 챗봇 수동 테스트 시나리오 (DB 데이터 생성용)

> `./dev.sh` 실행 후 보호자 계정으로 챗봇 접속해서 아래 대화를 순서대로 입력한다.

---

## 전제조건 확인

| 항목 | 확인 방법 |
|------|-----------|
| 서비스 기동 | `./dev.sh` 실행 후 프론트/백엔드 정상 |
| 보호자 계정 | 병원 연결된 guardian 계정 로그인 |
| Phase 확인 | PRE_BOOKING → triage / BOOKED → followup_filter |

---

## 1. TRIAGE 테스트 (PRE_BOOKING 상태 — 예약 전)

> **결과 저장 위치**: `triage_result` 테이블 (emrid, urgency_level, extracted_variables 등)
> 
> **멀티턴 포인트**: 봇이 질문하면 아래 "봇 질문 후 답변"에 해당하는 내용을 입력한다.

---

### T1. 🔴 RED — 발작 (현재 진행)

```
[1번 메시지] 강아지가 갑자기 쓰러지더니 몸을 계속 떨고 있어요
[봇 질문 후] 지금도 경련이 안 멈춰요. 5분 넘게 계속 발작하고 있어요
[봇 질문 후] 의식이 없는 것 같아요 이름 불러도 반응을 안 해요
```

**예상 결과**: `urgency_level=RED`, `extracted_variables.NEUROLOGIC.seizure_status=active`, red_flag 감지

---

### T2. 🔴 RED — 심한 호흡곤란 + 청색증

```
[1번 메시지] 고양이가 입을 벌리고 숨을 쉬어요 너무 힘들어 보여요
[봇 질문 후] 혀가 파랗게 변한 것 같아요 가슴이 엄청 들썩여요
[봇 질문 후] 숨소리가 이상하고 그렁그렁 소리가 나요
```

**예상 결과**: `urgency_level=RED`, `cyanosis=yes` 또는 `breathing_severity=severe`

---

### T3. 🔴 RED — 소변 폐색

```
[1번 메시지] 고양이가 화장실에 계속 들어가는데 소변이 전혀 안 나와요
[봇 질문 후] 몇 시간째예요. 화장실 들어갔다 나오기를 반복하는데 아무것도 안 싸요
[봇 질문 후] 배를 만지면 아파하는 것 같아요
```

**예상 결과**: `urgency_level=RED`, `urination=obstruction`

---

### T4. 🟠 ORANGE — 중등도 호흡

```
[1번 메시지] 강아지가 좀 숨이 차 보여요
[봇 질문 후] 운동을 안 했는데도 빠르게 숨을 쉬어요. 힘들어 보이긴 한데 걸을 수는 있어요
[봇 질문 후] 어제부터 이랬어요
```

**예상 결과**: `urgency_level=ORANGE`, `breathing_severity=moderate`

---

### T5. 🟠 ORANGE — 기도 협착음

```
[1번 메시지] 강아지 숨 쉴 때 이상한 소리가 나요
[봇 질문 후] 끽끽거리는 소리가 목에서 나요. 숨쉬기 힘들어 보여요
[봇 질문 후] 갑자기 오늘부터 이랬어요
```

**예상 결과**: `urgency_level=ORANGE`, `stridor=yes`

---

### T6. 🟡 YELLOW — 잦은 기침

```
[1번 메시지] 강아지가 기침을 해요
[봇 질문 후] 어제부터 켁켁대고 있어요. 하루에 10번은 넘는 것 같아요
[봇 질문 후] 밥은 잘 먹는데 기침이 많이 나요
```

**예상 결과**: `urgency_level=YELLOW`, `cough=frequent`

---

### T7. 🟡 YELLOW — 빠른 호흡수

```
[1번 메시지] 강아지가 누워있는데도 숨이 빠른 것 같아요
[봇 질문 후] 세어봤더니 분당 50번 가까이 쉬는 것 같아요
[봇 질문 후] 특별히 운동이나 흥분한 것도 아닌데 계속 그래요
```

**예상 결과**: `urgency_level=YELLOW`, `breathing_rate=fast`

---

### T8. 🟢 GREEN — 가끔 기침

```
[1번 메시지] 강아지가 가끔 기침을 해요
[봇 질문 후] 하루에 한두 번 정도예요. 심하진 않아요
[봇 질문 후] 밥도 잘 먹고 활발하게 잘 놀아요
```

**예상 결과**: `urgency_level=GREEN`, `cough=occasional`

---

### T9. 🟢 GREEN — 재채기 / 맑은 콧물

```
[1번 메시지] 강아지가 재채기를 몇 번 했어요
[봇 질문 후] 아침에 두세 번 했어요. 콧물도 조금 나오는데 맑아요
[봇 질문 후] 다른 건 다 괜찮아요 밥도 잘 먹어요
```

**예상 결과**: `urgency_level=GREEN`, `sneezing=yes` or `nasal_discharge=clear`

---

> ### ⚠️ Triage 완료 후 해야 할 것
> 문진이 끝나면 봇이 "예약을 도와드릴까요?" 묻는다.
> - **"예"** 입력 → 예약 확정 → DB에 `schedule` 행 생성 → `scheduleid` 메모해둠
> - 이후 Admin 패널 > 전체 성능 탭에서 `scheduleid`로 케이스 검증 실행

---

## 2. FOLLOWUP FILTER 테스트 (BOOKED 상태 — 예약 후)

> **전제**: 위 T1~T9에서 예약까지 완료한 뒤 같은 계정으로 챗봇 재접속
> 
> **결과 저장 위치**: 메모리 링버퍼 (Admin > 경과필터 탭 > 실시간 운영 로그) + `chat_history.followup_summary`

---

### 【A그룹】 명확한 경과 (is_followup=true 확실)

#### F-A1. 증상 악화 — 구토

```
오늘 강아지가 구토를 세 번 했어요. 어제 진료 때보다 더 심해진 것 같아요
```

**예상**: `is_followup=true`, `category=symptom_change`, `severity=worse`

---

#### F-A2. 즉각 주의 필요 — 발작 재발

```
아까 또 발작을 했어요. 이번엔 약 5분 정도 지속됐어요
```

**예상**: `is_followup=true`, `category=symptom_change`, `severity=urgent_possible`

---

#### F-A3. 약 복용 후 이상 반응

```
처방해주신 약 먹이고 나서 30분 있다가 토를 했어요. 약이 문제인 건지 걱정돼요
```

**예상**: `is_followup=true`, `category=medication_response`, `severity=worse`

---

#### F-A4. 식욕·기력 변화

```
밥을 어제부터 전혀 안 먹어요. 물도 거의 안 마시고 기운이 없어 보여요
```

**예상**: `is_followup=true`, `category=appetite_energy`, `severity=worse`

---

#### F-A5. 대변·소변 변화 (명확)

```
오늘 대변에 피가 섞여 있었어요. 색이 많이 어두운 편이에요
```

**예상**: `is_followup=true`, `category=stool_urine`, `severity=urgent_possible`

---

### 【B그룹】 애매한 경과 (분류가 어려운 케이스)

#### F-B1. 막연한 이상함

```
오늘 왠지 좀 이상한 것 같아요
```

**예상**: `is_followup=true`(아마도), `confidence < 0.7` → 저신뢰 케이스로 기록

---

#### F-B2. 호전도 악화도 아닌 현상유지

```
별로 달라진 건 없는 것 같아요
```

**예상**: `is_followup=true`, `severity=stable`, `confidence` 낮을 수 있음

---

#### F-B3. 식욕 변화 (약간 애매)

```
밥을 조금 덜 먹는 것 같기도 해요
```

**예상**: 경계선 케이스. LLM이 `is_followup=true`(식욕변화) vs `false` 고민 → confidence 확인

---

#### F-B4. 긍정적 변화 (경과 보고 맞음)

```
오늘은 어제보다 훨씬 좋아 보여요! 밥도 잘 먹었어요
```

**예상**: `is_followup=true`, `category=appetite_energy`, `severity=stable`

---

#### F-B5. 사진만 (텍스트 없음)

```
(사진 첨부 후) 이거요
```

**예상**: 사진이 있으면 `is_saved=true`, `has_media=true` — 텍스트가 애매해도 저장

---

### 【C그룹】 경과 아님 (is_followup=false)

#### F-C1. 병원 정보 (hospital_info)

```
병원 몇 시까지 해요?
```

**예상**: `is_followup=false`, `category=hospital_info`

---

#### F-C2. 일반 의료 질문 (pet_general)

```
이 약이 어디에 쓰는 약인지 알 수 있을까요?
```

**예상**: `is_followup=false`, `category=pet_general`

---

#### F-C3. 완전 무관 (irrelevant)

```
오늘 날씨가 좋네요
```

**예상**: `is_followup=false`, `category=irrelevant`

---

#### F-C4. 예약 확인

```
다음 진료 예약이 언제인지 확인할 수 있을까요?
```

**예상**: `is_followup=false`, `category=hospital_info`

---

## 3. Admin에서 결과 확인하는 법

### 경과필터 로그 확인

1. Admin 패널 접속
2. `AI 에이전트 평가` → `경과 필터` 탭
3. **실시간 운영 로그** 테이블 확인
   - EMR #, 시간, 메시지, 카테고리, 심각도, 저장 여부

### Triage 케이스 검증

1. 위 T1~T9 대화 중 예약까지 완료 후 `scheduleid` 메모
2. Admin `전체 성능` 탭 → Schedule ID 입력 → 케이스 검증 실행
3. Triage / Schedule / Chart 각 Check 결과 확인

### 벤치마크 평가 실행

- **Triage 탭**: `평가 실행` 버튼 → 결정론 체크(즉시) + LLM 체크(API 호출)
- **경과 필터 탭**: `평가 실행` 버튼 → keyword + LLM 분류 정확도

---

## 4. 테스트 순서 권장

```
① T1~T3 (RED 케이스 3개) → 예약까지 완료 → scheduleid 메모
② F-A1~F-A5 (명확 경과 5개) → Admin 로그 확인
③ F-B1~F-B5 (애매한 경과 5개) → confidence 값 확인
④ F-C1~F-C4 (경과 아님 4개) → is_followup=false 확인
⑤ T4~T9 (ORANGE~GREEN 케이스) → 응급도 다양성 확보
⑥ Admin > Triage 탭 > 평가 실행
⑦ Admin > 경과 필터 탭 > 평가 실행
```
