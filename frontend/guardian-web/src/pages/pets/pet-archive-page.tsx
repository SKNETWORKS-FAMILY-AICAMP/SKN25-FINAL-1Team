import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { Link } from "react-router-dom";

import {
  getArchivedPets,
  restorePet,
  permanentlyDeletePet,
  type Pet,
} from "../../api/pets-api";
import ActionButton from "../../components/common/action-button";
import PageHeader from "../../components/common/page-header";
import SectionCard from "../../components/common/section-card";
import GuardianLayout from "../../layouts/guardian-layout";
import { useTranslation } from "../../i18n/language-context";

interface ApiMessageResponse {
  code?: number;
  message?: string;
}

// 서버 HTTPException 의 detail 은 응답 body 의 message 필드로 내려온다(예: 409 보관 정책 안내).
const getErrorMessage = (error: unknown, fallbackMessage: string) => {
  if (isAxiosError<ApiMessageResponse | string>(error)) {
    const responseData = error.response?.data;
    if (typeof responseData === "string") {
      try {
        return (
          (JSON.parse(responseData) as ApiMessageResponse).message ||
          fallbackMessage
        );
      } catch {
        return fallbackMessage;
      }
    }
    return responseData?.message || fallbackMessage;
  }
  return fallbackMessage;
};

const PetArchivePage = () => {
  const { t } = useTranslation();
  const [pets, setPets] = useState<Pet[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadMessage, setLoadMessage] = useState("");
  const [notice, setNotice] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [pendingId, setPendingId] = useState<number | null>(null);

  const load = async () => {
    try {
      setIsLoading(true);
      setLoadMessage("");
      const data = await getArchivedPets();
      setPets(data);
    } catch (error) {
      setLoadMessage(getErrorMessage(error, t("petArchive.loadFailed")));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRestore = async (pet: Pet) => {
    setNotice("");
    setErrorMessage("");
    try {
      setPendingId(pet.pet_id);
      const res = await restorePet(pet.pet_id);
      setPets((current) => current.filter((p) => p.pet_id !== pet.pet_id));
      setNotice(res.message);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, t("petArchive.restoreFailed")));
    } finally {
      setPendingId(null);
    }
  };

  const handlePermanentDelete = async (pet: Pet) => {
    setNotice("");
    setErrorMessage("");
    // eslint-disable-next-line no-alert
    if (!window.confirm(t("petArchive.permanentConfirm"))) {
      return;
    }
    try {
      setPendingId(pet.pet_id);
      const res = await permanentlyDeletePet(pet.pet_id);
      setPets((current) => current.filter((p) => p.pet_id !== pet.pet_id));
      setNotice(res.message);
    } catch (error) {
      // 409: 진료 기록이 있어 영구 삭제 불가 — 서버 보관 정책 안내 문구를 그대로 노출.
      setErrorMessage(getErrorMessage(error, t("petArchive.permanentFailed")));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <GuardianLayout>
      <PageHeader
        title={t("petArchive.pageTitle")}
        description={t("petArchive.pageDescription")}
        rightAction={
          <Link
            to="/home"
            className="text-sm font-semibold text-slate-400 transition hover:text-blue-600"
          >
            {t("pet.backHome")}
          </Link>
        }
      />

      {/* 영구 삭제는 기록 없는 펫만 가능하다는 UX 안내 */}
      <div className="mb-5 rounded-xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-700">
        {t("petArchive.permanentNote")}
      </div>

      {notice ? (
        <div className="mb-5 rounded-xl bg-blue-50 px-4 py-3 text-sm font-bold text-blue-700">
          {notice}
        </div>
      ) : null}
      {errorMessage ? (
        <div className="mb-5 rounded-xl bg-rose-50 px-4 py-3 text-sm font-bold text-rose-600">
          {errorMessage}
        </div>
      ) : null}

      {isLoading ? (
        <SectionCard>
          <div className="flex min-h-[200px] items-center justify-center">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
          </div>
        </SectionCard>
      ) : loadMessage ? (
        <SectionCard className="text-center">
          <p className="text-sm font-bold text-rose-600">{loadMessage}</p>
          <ActionButton type="button" onClick={load} className="mt-6">
            {t("common.retry")}
          </ActionButton>
        </SectionCard>
      ) : pets.length === 0 ? (
        <SectionCard className="text-center">
          <p className="py-10 text-sm font-semibold text-slate-500">
            {t("petArchive.empty")}
          </p>
        </SectionCard>
      ) : (
        <div className="space-y-3">
          {pets.map((pet) => (
            <article
              key={pet.pet_id}
              className="rounded-xl border border-slate-200 bg-slate-50 p-4 sm:flex sm:items-center sm:justify-between sm:gap-5"
            >
              <div className="min-w-0">
                <h2 className="text-base font-extrabold text-slate-950">
                  {pet.petname}
                </h2>
                <p className="mt-1 text-sm font-semibold text-slate-500">
                  {pet.species || pet.breed || t("home.petFallback")}
                </p>
              </div>
              <div className="mt-3 flex gap-2 sm:mt-0">
                <ActionButton
                  type="button"
                  variant="outlineBlue"
                  size="sm"
                  disabled={pendingId === pet.pet_id}
                  onClick={() => handleRestore(pet)}
                >
                  {t("petArchive.restore")}
                </ActionButton>
                <ActionButton
                  type="button"
                  variant="outlineDanger"
                  size="sm"
                  disabled={pendingId === pet.pet_id}
                  onClick={() => handlePermanentDelete(pet)}
                >
                  {t("petArchive.permanentDelete")}
                </ActionButton>
              </div>
            </article>
          ))}
        </div>
      )}
    </GuardianLayout>
  );
};

export default PetArchivePage;
