import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import { siteConfig } from "../../config/site";
import ContactLink from "../common/ContactLink";

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <img src={medipawSymbol} alt="MediPaw" className="h-8 w-fit" />
          <span className="text-sm font-extrabold text-slate-500">AI-assisted veterinary workflow platform</span>
        </div>
        <div className="flex flex-col gap-2 text-sm font-semibold text-slate-400 sm:flex-row sm:items-center sm:gap-5">
          <ContactLink className="inline-flex items-center gap-2 font-bold text-blue-700 transition hover:text-blue-800" label={siteConfig.companyEmail} />
          <span>© 2026 MediPaw. Built for safer clinical workflows.</span>
        </div>
      </div>
    </footer>
  );
}
