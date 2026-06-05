import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, ShieldCheck } from "lucide-react";
import { AuthLayout } from "../../components/auth/AuthLayout";

export default function AccountInquiryPage() {
  const navigate = useNavigate();
  const [hospitalName, setHospitalName] = useState("");
  const [bizNumber, setBizNumber] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const isValid = hospitalName.trim() && bizNumber.trim() && licenseNumber.trim();

  const handleSubmit = () => {
    if (!isValid) return;
    const subject = encodeURIComponent(`[MediPaw 계정 문의] ${hospitalName}`);
    const body = encodeURIComponent(
      `안녕하세요, MediPaw 고객지원팀 담당자님.\n\n` +
      `MediPaw 시스템 계정 관련 문의 드립니다.\n\n` +
      `─────────────────────────────\n` +
      `■ 동물병원 이름   : ${hospitalName}\n` +
      `■ 사업자등록번호  : ${bizNumber}\n` +
      `■ 의사면허번호    : ${licenseNumber}\n` +
      `─────────────────────────────\n\n` +
      `위 정보를 확인하신 후 빠른 처리 부탁드립니다.\n\n` +
      `감사합니다.`
    );
    window.location.href = `mailto:medipaw@gmail.com?subject=${subject}&body=${body}`;
    setSubmitted(true);
  };

  return (
    <AuthLayout>
      <div className="mx-auto w-full max-w-[500px] rounded-3xl border border-slate-200 bg-white px-10 py-10 shadow-sm">
        <div className="mb-8 text-center">
          <h2 className="text-3xl font-bold text-slate-900">계정 문의</h2>
          <p className="mt-3 text-sm font-medium text-slate-500">
            등록된 병원 정보를 입력해주세요.
          </p>
        </div>

        <div className="space-y-4">
          <FormField
            label="동물병원 이름"
            placeholder="동물병원 이름을 입력하세요"
            value={hospitalName}
            onChange={setHospitalName}
          />
          <FormField
            label="사업자등록번호"
            placeholder="000-00-00000"
            value={bizNumber}
            onChange={setBizNumber}
          />
          <FormField
            label="의사면허번호"
            placeholder="면허번호를 입력하세요"
            value={licenseNumber}
            onChange={setLicenseNumber}
          />
        </div>

        {submitted && (
          <div className="mt-5 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-center text-sm font-bold text-blue-700">
            이메일 앱이 열렸습니다. 내용을 확인 후 발송해주세요.
          </div>
        )}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={!isValid}
          className="mt-6 flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 text-base font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        >
          <Mail size={18} />
          문의하기
        </button>

        <button
          type="button"
          onClick={() => navigate("/login")}
          className="mt-3 h-11 w-full rounded-xl border border-slate-200 text-sm font-bold text-slate-500 transition hover:bg-slate-50"
        >
          로그인으로 돌아가기
        </button>
      </div>

      <div className="mx-auto mt-5 flex h-14 w-full max-w-[500px] items-center justify-center gap-3 rounded-xl bg-blue-50 text-sm font-bold text-blue-700">
        <ShieldCheck size={18} />
        문의 접수 후 영업일 기준 1~2일 내 답변드립니다.
      </div>
    </AuthLayout>
  );
}

function FormField({
  label,
  placeholder,
  value,
  onChange,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-bold text-slate-700">
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-14 w-full rounded-xl border border-slate-200 px-4 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
      />
    </div>
  );
}
