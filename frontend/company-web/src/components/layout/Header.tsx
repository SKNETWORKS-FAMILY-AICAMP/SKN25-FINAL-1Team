import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import { navItems } from "../../config/site";

interface HeaderProps {
  onGuardianClick?: () => void;
  onVetClick?: () => void;
}

export default function Header({ onGuardianClick, onVetClick }: HeaderProps) {
  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <a href="#" className="flex items-center gap-2 rounded-lg" aria-label="MediPaw 홈">
          <img src={medipawSymbol} alt="MediPaw" className="h-9 w-auto" />
        </a>

        <nav className="hidden items-center gap-7 lg:flex">
          {navItems.map((item) => (
            <a key={item.href} href={item.href} className="text-sm font-extrabold text-slate-600 transition hover:text-blue-700">
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Link
            to="/apply"
            className="hidden h-11 items-center rounded-full border border-blue-200 bg-blue-50 px-4 text-sm font-bold text-blue-700 transition hover:bg-blue-100 sm:inline-flex"
          >
            동물병원 입점 신청
          </Link>
          <button
            type="button"
            onClick={onGuardianClick}
            className="hidden sm:inline-flex mp-btn-secondary"
          >
            보호자 웹 보기
          </button>
          <button
            type="button"
            onClick={onVetClick}
            className="mp-btn-primary"
          >
            수의사 웹 보기
            <ArrowRight className="ml-2 h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
