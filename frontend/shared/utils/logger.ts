/**
 * 개발 환경에서만 콘솔에 출력하는 로거.
 * 프로덕션 빌드에서는 무음 처리하여 devtools 콘솔로 내부 구조/에러 페이로드가
 * 노출되지 않도록 한다. error는 추후 Sentry 등 외부 리포팅 연동 지점으로 사용한다.
 */
const isDev = import.meta.env.DEV;

export const logger = {
  log: (...args: unknown[]) => {
    if (isDev) console.log(...args);
  },
  info: (...args: unknown[]) => {
    if (isDev) console.info(...args);
  },
  warn: (...args: unknown[]) => {
    if (isDev) console.warn(...args);
  },
  error: (...args: unknown[]) => {
    if (isDev) console.error(...args);
    // TODO: 프로덕션 에러 리포팅(Sentry 등) 연동 지점
  },
};
