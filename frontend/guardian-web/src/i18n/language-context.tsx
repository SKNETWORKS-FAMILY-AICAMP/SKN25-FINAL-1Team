import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  DEFAULT_LANGUAGE,
  translations,
  type Language,
  type TranslationTree,
} from "./translations";

const STORAGE_KEY = "medipaw.lang";

interface LanguageContextValue {
  lang: Language;
  setLang: (lang: Language) => void;
  /** 점(.) 경로로 번역 문자열을 조회. {var} 치환 지원. 없으면 키 자체를 반환. */
  t: (key: string, vars?: Record<string, string | number>) => string;
  /** 현재 UI 언어와 무관하게 지정한 언어로 번역(대화별 언어 고정용). */
  translateTo: (
    targetLang: Language,
    key: string,
    vars?: Record<string, string | number>,
  ) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

const isLanguage = (value: unknown): value is Language =>
  value === "ko" || value === "en" || value === "ja" || value === "zh";

const readInitialLanguage = (): Language => {
  if (typeof window === "undefined") return DEFAULT_LANGUAGE;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isLanguage(stored)) return stored;
  // 브라우저 언어로 1회 추정
  const nav = window.navigator.language?.slice(0, 2).toLowerCase();
  if (isLanguage(nav)) return nav;
  return DEFAULT_LANGUAGE;
};

const lookup = (tree: TranslationTree, key: string): string | undefined => {
  const segments = key.split(".");
  let current: string | TranslationTree | undefined = tree;
  for (const segment of segments) {
    if (typeof current !== "object" || current === null) return undefined;
    current = current[segment];
  }
  return typeof current === "string" ? current : undefined;
};

const interpolate = (
  template: string,
  vars?: Record<string, string | number>,
): string => {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    name in vars ? String(vars[name]) : match,
  );
};

export const LanguageProvider = ({ children }: { children: ReactNode }) => {
  const [lang, setLangState] = useState<Language>(readInitialLanguage);

  useEffect(() => {
    document.documentElement.lang = lang;
    window.localStorage.setItem(STORAGE_KEY, lang);
  }, [lang]);

  const setLang = useCallback((next: Language) => setLangState(next), []);

  const translateTo = useCallback(
    (
      targetLang: Language,
      key: string,
      vars?: Record<string, string | number>,
    ) => {
      const value =
        lookup(translations[targetLang], key) ??
        lookup(translations[DEFAULT_LANGUAGE], key);
      return value !== undefined ? interpolate(value, vars) : key;
    },
    [],
  );

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) =>
      translateTo(lang, key, vars),
    [lang, translateTo],
  );

  const value = useMemo<LanguageContextValue>(
    () => ({ lang, setLang, t, translateTo }),
    [lang, setLang, t, translateTo],
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useTranslation = (): LanguageContextValue => {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useTranslation must be used within a LanguageProvider");
  }
  return ctx;
};
