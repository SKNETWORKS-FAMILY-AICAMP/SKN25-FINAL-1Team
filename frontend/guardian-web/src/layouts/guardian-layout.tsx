import type { ReactNode } from "react";

import GuardianNavbar from "../components/guardian-navbar";

interface GuardianLayoutProps {
  children: ReactNode;
}

const GuardianLayout = ({ children }: GuardianLayoutProps) => {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-950">
      <GuardianNavbar />

      <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col px-6 pb-12 pt-10">
        {children}
      </main>
    </div>
  );
};

export default GuardianLayout;