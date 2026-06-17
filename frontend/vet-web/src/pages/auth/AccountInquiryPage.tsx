import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, ShieldCheck } from "lucide-react";
import axios from "axios";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { apiClient } from "../../api/client";

export default function AccountInquiryPage() {
  const navigate = useNavigate();
  const [hospitalName, setHospitalName] = useState("");
  const [bizNumber, setBizNumber] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const isValid = hospitalName.trim() && bizNumber.trim() && licenseNumber.trim();

  const handleSubmit = async () => {
    if (!isValid) return;
    setIsLoading(true);
    setError("");
    try {
      await apiClient.post("/doctor/auth/account-inquiry", {
        hospital_name: hospitalName,
        business_number: bizNumber,
        license_number: licenseNumber,
      });
      setSubmitted(true);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data;
        setError(data?.message ?? data?.detail ?? "문의 처리 중 오류가 발생했습니다. 다시 시도해주세요.");
      } else {
        setError("문의 처리 중 오류가 발생했습니다. 다시 시도해주세요.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className="mx-auto flex min-h-[560px] w-full max-w-[500px] flex-col rounded-lg border border-slate-200 bg-white px-10 py-10 shadow-sm">
        <div className="mb-10 h-[88px] text-center">
          <h2 className="text-3xl font-extrabold leading-tight text-slate-900">계정 문의</h2>
          <p className="mt-4 text-sm font-bold text-slate-500">
            등록된 병원 정보를 입력해주세요.
          </p>
        </div>

        <div className="space-y-5">
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
          <div className="mt-5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-center text-sm font-bold text-blue-700">
            등록된 이메일로 계정 정보를 발송했습니다. 이메일을 확인해주세요.
          </div>
        )}

        {error && (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-center text-sm font-bold text-red-600">
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={!isValid || isLoading || submitted}
          className="mt-7 flex h-14 w-full items-center justify-center gap-2 rounded-lg bg-blue-600 text-base font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        >
          <Mail size={18} />
          {isLoading ? "처리 중..." : "문의하기"}
        </button>

        <button
          type="button"
          onClick={() => navigate("/login")}
          className="mt-4 h-11 w-full rounded-lg border border-slate-200 text-sm font-bold text-slate-500 transition hover:bg-slate-50"
        >
          로그인으로 돌아가기
        </button>
      </div>

      <div className="mx-auto mt-5 flex h-14 w-full max-w-[500px] items-center justify-center gap-3 rounded-lg bg-blue-50 text-sm font-bold text-blue-700">
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
        className="h-14 w-full rounded-lg border border-slate-200 px-4 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
      />
    </div>
  );
}
