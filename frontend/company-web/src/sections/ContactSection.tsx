import { FormEvent, ReactNode, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { siteConfig } from "../config/site";

export default function ContactSection() {
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
  };

  return (
    <section id="contact" className="bg-white py-12 sm:py-14 lg:py-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-black uppercase tracking-[0.18em] text-blue-700">Contact MediPaw</p>
          <h2 className="mt-3 break-keep text-3xl font-black leading-tight text-slate-950 sm:text-4xl lg:text-5xl">
            MediPaw와 함께 시작하세요
          </h2>
          <p className="mx-auto mt-3 max-w-2xl break-keep text-sm font-semibold leading-6 text-slate-600 sm:text-base">
            보호자든 동물병원이든, 데모를 신청하고 MediPaw의 혁신을 경험해보세요.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="mx-auto mt-8 max-w-3xl rounded-[20px] border border-slate-200 bg-white p-5 shadow-soft-xl sm:p-6 lg:p-7"
        >
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="이름" htmlFor="contact-name">
              <input id="contact-name" name="name" type="text" placeholder="홍길동" className="contact-input" />
            </Field>

            <Field label="연락처" htmlFor="contact-phone">
              <input id="contact-phone" name="phone" type="tel" placeholder="010-1234-5678" className="contact-input" />
            </Field>
          </div>

          <div className="mt-4">
            <Field label="이메일" htmlFor="contact-email">
              <input id="contact-email" name="email" type="email" placeholder="example@email.com" className="contact-input" />
            </Field>
          </div>

          <div className="mt-4">
            <Field label="사용자 유형" htmlFor="contact-type">
              <select id="contact-type" name="type" defaultValue="보호자" className="contact-input">
                <option>보호자</option>
                <option>동물병원</option>
                <option>제휴/협업</option>
                <option>기타</option>
              </select>
            </Field>
          </div>

          <div className="mt-4">
            <Field label="문의 내용" htmlFor="contact-message">
              <textarea
                id="contact-message"
                name="message"
                rows={3}
                placeholder="궁금한 점을 입력해주세요..."
                className="contact-input min-h-28 resize-y py-3"
              />
            </Field>
          </div>

          {submitted && (
            <div className="mt-4 flex items-start gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-left">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
              <p className="break-keep text-sm font-bold leading-6 text-blue-800">
                문의가 접수되었습니다. {siteConfig.companyEmail}으로 확인 후 연락드리겠습니다.
              </p>
            </div>
          )}

          <button type="submit" className="mt-5 flex h-11 w-full items-center justify-center rounded-2xl bg-sky-600 px-6 text-base font-black text-white transition hover:bg-sky-700">
            문의 신청하기
          </button>

          <p className="mt-3 text-center text-xs font-semibold text-slate-500 sm:text-sm">
            협업 및 도입 문의:{" "}
            <a href={siteConfig.contactHref} className="font-black text-blue-700 transition hover:text-blue-800">
              {siteConfig.companyEmail}
            </a>
          </p>
        </form>
      </div>
    </section>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="block">
      <span className="mb-2 block text-sm font-black text-slate-950 sm:text-base">{label}</span>
      {children}
    </label>
  );
}
