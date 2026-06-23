import { useCallback, useState } from "react";

import { translateTexts } from "../api/chat-api";
import { useTranslation } from "./language-context";
import { isKnownText, translateKnownText } from "./known-text";

// 언어 변경 시 챗봇 답변·사용자 메시지·추천(pill)을 선택 언어로 다시 렌더링한다(req2/3).
//  · 고정 문구(knownTextKey)는 사전으로 즉시·무비용 번역.
//  · 그 외 한국어 원문(LLM 답변·자유 입력)은 백엔드 /chat/translate로 일괄 번역 후 캐시.
//  · 한국어(ko) 보기에서는 저장 원문(한국어)을 그대로 노출 — 번역 호출 없음.

// 모듈 레벨 캐시: cache[lang][sourceText] = translated. 언어를 오갈 때 재호출을 막는다.
const translationCache: Record<string, Record<string, string>> = {};
const pendingKeys = new Set<string>();

// 한글 음절/자모가 포함된 한국어 원문만 번역 대상으로 삼는다.
const hasHangul = (text: string): boolean =>
  /[ᄀ-ᇿ㄰-㆏가-힣]/.test(text);

// 번역 API가 브랜드명을 잘못 음역하는 경우를 교정한다.
const fixBrandNames = (text: string): string =>
  text.replace(/Medipo/g, "Medipaw").replace(/medipo/g, "medipaw");

/**
 * 백엔드가 내려준 (원문→번역) 매핑으로 캐시를 미리 채운다.
 * 추천(pill)·스트리밍 답변을 추가 API 호출 없이 즉시 표시하기 위함.
 */
export const primeTranslationCache = (
  lang: string,
  entries: Record<string, string>,
): void => {
  if (lang === "ko") return;
  const cache = (translationCache[lang] ??= {});
  for (const [source, translated] of Object.entries(entries)) {
    if (source && translated) cache[source] = fixBrandNames(translated);
  }
};

export interface TranslationStatus {
  text: string;
  /** 번역 대기 중(아직 결과 없음) — 한국어 원문 대신 shimmer 표시용. */
  pending: boolean;
}

export const useDynamicTranslation = () => {
  const { lang, t } = useTranslation();
  const [, forceRender] = useState(0);

  // 번역 상태까지 반환 — 캐시 미스 시 pending=true(원문 노출 대신 shimmer).
  const translateWithStatus = useCallback(
    (text: string | null | undefined): TranslationStatus => {
      if (!text) return { text: "", pending: false };
      // 고정 문구는 항상 사전 번역(언어 무관, 즉시).
      if (isKnownText(text)) return { text: translateKnownText(text, t, lang), pending: false };
      // 기본 저장 언어(한국어) 보기에서는 원문 그대로.
      if (lang === "ko") return { text, pending: false };
      const cached = translationCache[lang]?.[text];
      if (cached) return { text: cached, pending: false };
      // 한국어 원문은 번역 대기(shimmer). 그 외(이미 타깃 언어인 입력 등)는 그대로.
      if (hasHangul(text)) return { text: "", pending: true };
      return { text, pending: false };
    },
    [lang, t],
  );

  const translate = useCallback(
    (text: string | null | undefined): string => {
      const status = translateWithStatus(text);
      // pending이면 원문(한국어) 대신 빈 문자열 — 호출부에서 placeholder 처리.
      return status.pending ? (text ?? "") : status.text;
    },
    [translateWithStatus],
  );

  const ensureTranslated = useCallback(
    (texts: Array<string | null | undefined>) => {
      if (lang === "ko") return;
      const langCache = (translationCache[lang] ??= {});

      const seen = new Set<string>();
      const missing: string[] = [];
      for (const raw of texts) {
        const text = raw?.trim();
        if (!text || seen.has(text)) continue;
        seen.add(text);
        if (
          !isKnownText(text) &&
          !(text in langCache) &&
          !pendingKeys.has(`${lang}::${text}`) &&
          hasHangul(text) // 한국어 원문만 번역 대상(이미 타깃 언어인 입력은 스킵)
        ) {
          missing.push(text);
        }
      }
      if (missing.length === 0) return;

      const targetLang = lang;
      missing.forEach((text) => pendingKeys.add(`${targetLang}::${text}`));

      void translateTexts(missing, targetLang)
        .then((translations) => {
          const cache = (translationCache[targetLang] ??= {});
          missing.forEach((text, index) => {
            cache[text] = fixBrandNames(translations[index] ?? text);
          });
          forceRender((value) => value + 1);
        })
        .catch(() => {
          // 실패 시 원문 유지
        })
        .finally(() => {
          missing.forEach((text) => pendingKeys.delete(`${targetLang}::${text}`));
        });
    },
    [lang],
  );

  return { translate, translateWithStatus, ensureTranslated, lang };
};
