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
import PetForm from "../../components/pets/pet-form";
import PetImageUploader from "../../components/pets/pet-image-uploader";
import { usePetForm } from "../../hooks/use-pet-form";
import { useTranslation } from "../../i18n/language-context";

const maxImageSize = 5 * 1024 * 1024;

// PawIcon removed as requested

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
    <main className="mx-auto w-full max-w-4xl px-4 sm:px-6 py-8 md:py-12 relative z-10">

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
        <div className="bg-white rounded-[2rem] border border-[#E5E7EB] shadow-sm p-5 sm:p-8 md:p-12 relative overflow-hidden">
          <div className="flex flex-col items-center border-b border-[#E5E7EB] pb-8 md:pb-10 mb-8">
            <PetImageUploader
              previewUrl={previewUrl}
              isDetailMode={isDetailMode}
              fileInputRef={fileInputRef}
              onImageChange={handleImageChange}
              errorMessage={errors.profileImage}
            />

          </div>

          <form onSubmit={handleSubmit} className="relative z-10">
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
              <p className="mx-2 mt-6 rounded-2xl bg-red-50/80 px-5 py-4 text-sm font-bold text-red-600 ring-1 ring-red-100 flex items-center gap-3">
                <span className="text-xl">⚠️</span>
                {submitMessage}
              </p>
            ) : null}

            <footer className="mt-8 md:mt-10 flex justify-end gap-3 px-1 md:px-2">
              <button
                type="button"
                onClick={closeModal}
                className="h-12 md:h-14 min-w-24 md:min-w-32 rounded-xl bg-[#F8FAFC] px-6 md:px-8 text-sm md:text-base font-extrabold text-[#6B7280] border border-[#E5E7EB] transition-all hover:bg-[#E5E7EB]"
              >
                {t("common.cancel")}
              </button>
              <button
                type="submit"
                disabled={isSubmitting || isUploadingImage}
                className="inline-flex h-12 md:h-14 min-w-32 md:min-w-44 items-center justify-center gap-2 md:gap-3 rounded-xl bg-[#2F6F67] px-6 md:px-8 text-sm md:text-base font-extrabold text-white transition-all hover:bg-[#255E57] disabled:cursor-not-allowed disabled:bg-[#E5E7EB] disabled:text-[#6B7280]"
              >
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

            <hr className="my-8 border-[#E5E7EB]" />
            <div className="flex items-center justify-center gap-2 text-[#6B7280] text-sm font-semibold">
              <span className="text-base">💡</span>
              <p>정확한 정보는 AI 상담과 진료 예약 정확도 향상에 도움이 됩니다.</p>
            </div>
          </form>
        </div>
        )}
      </main>
  );
};

export default PetRegisterPage;
