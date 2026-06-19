import type { ReactNode } from "react";

interface GuardianLayoutProps {
  children: ReactNode;
}

// 네비바는 GuardianShell이 한 번만 마운트한다. 여기서는 표준 본문 래퍼만 제공.
const GuardianLayout = ({ children }: GuardianLayoutProps) => {
  return (
    <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col px-4 pb-12 pt-6 sm:px-6 sm:pt-10">
      {children}
    </main>
  );
};

export default GuardianLayout;