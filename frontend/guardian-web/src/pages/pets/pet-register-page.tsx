import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useParams } from "react-router-dom";

import pawOnlyLogo from "../../../../shared/assets/logo/medipaw-pawonly.png";
import { uploadChatAttachment } from "../../api/chat-api";
import {
  createPet,
  getPet,
  updatePet,
} from "../../api/pets-api";
import GuardianNavbar from "../../components/guardian-navbar";
import PetForm from "../../components/pets/pet-form";
import PetImageUploader from "../../components/pets/pet-image-uploader";
import { usePetForm } from "../../hooks/use-pet-form";
import { useTranslation } from "../../i18n/language-context";

const maxImageSize = 5 * 1024 * 1024;

const PawIcon = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="currentColor">
    <path d="M8.4 9.9c1.1 0 1.9-1.3 1.9-2.9S9.5 4.1 8.4 4.1 6.5 5.4 6.5 7s.8 2.9 1.9 2.9Zm7.2 0c1.1 0 1.9-1.3 1.9-2.9s-.8-2.9-1.9-2.9-1.9 1.3-1.9 2.9.8 2.9 1.9 2.9ZM5.4 13.2c.9-.3 1.2-1.8.7-3.2-.5-1.5-1.7-2.4-2.6-2.1-.9.3-1.2 1.8-.7 3.2.5 1.5 1.7 2.4 2.6 2.1Zm13.2 0c.9.3 2.1-.6 2.6-2.1.5-1.4.2-2.9-.7-3.2-.9-.3-2.1.6-2.6 2.1-.5 1.4-.2 2.9.7 3.2ZM12 11.3c-3.2 0-5.8 2.4-5.8 5.2 0 1.8 1.5 3.1 3.2 3.1 1 0 1.7-.4 2.6-.4s1.6.4 2.6.4c1.7 0 3.2-1.3 3.2-3.1 0-2.8-2.6-5.2-5.8-5.2Z" />
  </svg>
);

const PetRegisterPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { petId } = useParams();
  const parsedPetId = petId ? Number(petId) : NaN;
  const isPetDataRoute = Boolean(petId);
  const isValidPetId =
    isPetDataRoute && Number.isFinite(parsedPetId) && parsedPetId > 0;
  const selectedPetId = isValidPetId ? parsedPetId : undefined;
  const isDetailMode = false;
  const isEditMode = isValidPetId;
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const customSpeciesInputRef = useRef<HTMLInputElement | null>(null);
  const {
    form,
    errors,
    previewUrl,
    setErrors,
    setPreviewUrl,
    resetPetFormState,
    applyPetToForm,
    updateForm,
    handleNameChange,
    handleNotesChange,
    validateForm,
    buildPayload,
    buildUpdatePayload,
  } = usePetForm({ customSpeciesInputRef, t });
  const [submitMessage, setSubmitMessage] = useState("");
  const [loadMessage, setLoadMessage] = useState(
    isPetDataRoute && !isValidPetId ? t("pet.invalidAccess") : "",
  );
  const [isLoading, setIsLoading] = useState(Boolean(isDetailMode || isEditMode));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);

  useEffect(() => {
    if (isPetDataRoute && !isValidPetId) {
      resetPetFormState();
      setLoadMessage(t("pet.invalidAccess"));
      setIsLoading(false);
      return;
    }

    if (!isPetDataRoute) {
      resetPetFormState();
      setLoadMessage("");
      setIsLoading(false);
      return;
    }

    if (!selectedPetId) {
      return;
    }

    let isMounted = true;

    const loadPet = async () => {
      try {
        setIsLoading(true);
        setLoadMessage("");

        const response = await getPet(selectedPetId);
        if (!isMounted) {
          return;
        }

        applyPetToForm(response);
      } catch (error) {
        if (!isMounted) {
          return;
        }

        if (isAxiosError<{ message?: string }>(error)) {
          setLoadMessage(
            error.response?.data?.message || t("pet.loadError"),
          );
          return;
        }

        setLoadMessage(t("pet.loadError"));
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadPet();

    return () => {
      isMounted = false;
    };
  }, [applyPetToForm, isPetDataRoute, isValidPetId, resetPetFormState, selectedPetId]);

  const closeModal = () => {
    navigate("/home");
  };

  const handleImageChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // 같은 파일을 다시 선택해도 onChange가 발생하도록 input 값을 비운다.
    event.target.value = "";

    if (!file) {
      return;
    }

    if (!["image/jpeg", "image/png"].includes(file.type)) {
      setErrors((current) => ({
        ...current,
        profileImage: t("pet.imageOnlyType"),
      }));
      return;
    }

    if (file.size > maxImageSize) {
      setErrors((current) => ({
        ...current,
        profileImage: t("pet.imageTooLarge"),
      }));
      return;
    }

    setErrors((current) => ({ ...current, profileImage: undefined }));

    // S3에 직접 업로드하고, 반환된 CloudFront URL을 profile_image로 저장한다.
    // (base64 미리보기는 백엔드 validator가 거부하므로 사용하지 않는다.)
    setIsUploadingImage(true);
    try {
      const { result } = await uploadChatAttachment(file);
      if (result?.cloudfront_url) {
        setPreviewUrl(result.cloudfront_url);
      } else {
        setErrors((current) => ({
          ...current,
          profileImage: t("pet.imageUploadFailed"),
        }));
      }
    } catch (error) {
      const message = isAxiosError<{ detail?: string }>(error)
        ? error.response?.data?.detail
        : undefined;
      setErrors((current) => ({
        ...current,
        profileImage: message || t("pet.imageUploadFailed"),
      }));
    } finally {
      setIsUploadingImage(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitMessage("");

    if (!validateForm()) {
      return;
    }

    try {
      setIsSubmitting(true);
      const updatePayload = isEditMode ? buildUpdatePayload() : undefined;

      if (isEditMode && Object.keys(updatePayload || {}).length === 0) {
        navigate("/home", {
          replace: true,
          state: { petUpdatedAt: Date.now() },
        });
        return;
      }

      let petIdToRefresh: number | undefined;
      const response =
        isEditMode && selectedPetId
          ? await updatePet(selectedPetId, updatePayload || {})
          : await createPet(buildPayload());

      if (isEditMode) {
        petIdToRefresh = selectedPetId;
      } else {
        petIdToRefresh = (response as { pet_id?: number }).pet_id;
      }

      if (petIdToRefresh) {
        await getPet(petIdToRefresh);
      }

      navigate("/home", {
        replace: true,
        state: isEditMode
          ? { petUpdatedAt: Date.now() }
          : { petRegisteredAt: Date.now() },
      });
    } catch (error) {
      if (isAxiosError<{ message?: string }>(error)) {
        setSubmitMessage(
          error.response?.data?.message ||
            (isEditMode ? t("pet.editFailed") : t("pet.registerFailed")),
        );
        return;
      }

      setSubmitMessage(isEditMode ? t("pet.editFailed") : t("pet.registerFailed"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <GuardianNavbar />

      <main className="mx-auto w-full max-w-[1280px] px-6 py-8">
        <section className="flex items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
            <img
              src={pawOnlyLogo}
              alt=""
              aria-hidden="true"
              className="h-8 w-8 object-contain"
            />
          </div>
          <div>
            <h1
              className={`font-extrabold text-slate-950 ${
                isEditMode ? "text-xl" : "text-2xl"
              }`}
            >
              {isEditMode ? t("pet.detailTitle") : t("pet.registerTitle")}
            </h1>
            <p className="mt-1 text-sm font-semibold text-slate-500">
              {isEditMode ? t("pet.detailSubtitle") : t("pet.registerSubtitle")}
            </p>
          </div>
        </section>

        {isLoading ? (
          <section className="mt-6 flex min-h-[420px] items-center justify-center rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-teal-100 border-t-teal-700" />
          </section>
        ) : loadMessage ? (
          <section className="mt-6 rounded-2xl border border-red-100 bg-white px-6 py-10 text-center shadow-sm">
            <h2 className="text-lg font-extrabold text-slate-900">
              {t("pet.loadErrorTitle")}
            </h2>
            <p className="mt-3 text-sm font-semibold text-red-500">
              {loadMessage}
            </p>
            <button
              type="button"
              onClick={() => navigate("/home")}
              className="mt-6 h-11 rounded-xl bg-teal-700 px-6 text-sm font-extrabold text-white transition hover:bg-teal-800"
            >
              {t("pet.backHome")}
            </button>
          </section>
        ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[340px_1fr]">
          <aside className="space-y-6">
            <PetImageUploader
              previewUrl={previewUrl}
              isDetailMode={isDetailMode}
              fileInputRef={fileInputRef}
              onImageChange={handleImageChange}
              errorMessage={errors.profileImage}
            />

            <section className="relative overflow-hidden rounded-2xl bg-teal-50 p-6 ring-1 ring-teal-100">
              <div className="flex items-center gap-2 text-teal-700">
                <PawIcon className="h-5 w-5" />
                <h2 className="text-lg font-extrabold">{t("pet.noticeTitle")}</h2>
              </div>
              <ul className="mt-6 space-y-4 pr-6 text-sm font-semibold leading-6 text-slate-700">
                {isEditMode ? (
                  <>
                    <li>{t("pet.noticeEdit1")}</li>
                    <li>{t("pet.noticeCommon")}</li>
                  </>
                ) : (
                  <>
                    <li>{t("pet.noticeNew1")}</li>
                    <li>{t("pet.noticeCommon")}</li>
                  </>
                )}
              </ul>
              <div className="pointer-events-none mt-8 flex justify-center gap-3 text-6xl leading-none">
                <span>🐶</span>
                <span>🐱</span>
              </div>
            </section>
          </aside>

          <form
            onSubmit={handleSubmit}
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
          >
            <PetForm
              form={form}
              errors={errors}
              isDetailMode={isDetailMode}
              customSpeciesInputRef={customSpeciesInputRef}
              updateForm={updateForm}
              handleNameChange={handleNameChange}
              handleNotesChange={handleNotesChange}
            />

            {submitMessage ? (
              <p className="mx-6 mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-bold text-red-600">
                {submitMessage}
              </p>
            ) : null}

            <footer className="mt-4 flex justify-end gap-3 border-t border-slate-100 px-6 py-5">
              <button
                type="button"
                onClick={closeModal}
                className="h-11 min-w-32 rounded-xl border border-slate-200 bg-white px-6 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50"
              >
                {t("common.cancel")}
              </button>
              <button
                type="submit"
                disabled={isSubmitting || isUploadingImage}
                className="inline-flex h-11 min-w-40 items-center justify-center gap-2 rounded-xl bg-teal-700 px-6 text-sm font-extrabold text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-teal-300"
              >
                <PawIcon className="h-4 w-4" />
                {isUploadingImage
                  ? t("pet.uploadingImage")
                  : isSubmitting
                    ? isEditMode
                      ? t("pet.editing")
                      : t("pet.registering")
                    : isEditMode
                      ? t("pet.editSubmit")
                      : t("pet.registerSubmit")}
              </button>
            </footer>
          </form>
        </div>
        )}
      </main>
    </div>
  );
};

export default PetRegisterPage;
