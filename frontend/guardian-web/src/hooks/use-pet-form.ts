import {
  type ChangeEvent,
  type RefObject,
  useCallback,
  useState,
} from "react";

import {
  type CreatePetPayload,
  type Pet,
} from "../api/pets-api";

export const speciesOptions = ["강아지", "고양이", "기타"];
export const genderOptions = ["수컷", "암컷", "모름"];
export const neuteredOptions = ["예", "아니오", "모름"];
export const maxNotesLength = 200;

const defaultProfileImages = [
  "/assets/profile1.png",
  "/assets/profile2.png",
  "/assets/profile3.png",
  "/assets/profile4.png",
  "/assets/profile5.png",
  "/assets/profile6.png",
];

export interface PetFormState {
  petname: string;
  species: string;
  customSpecies: string;
  breed: string;
  gender: string;
  isNeutered: string;
  birthDate: string;
  isBirthUnknown: boolean;
  weight: string;
  checkupDate: string;
  isCheckupUnknown: boolean;
  notes: string;
}

export type PetFormErrors = Partial<
  Record<keyof PetFormState | "profileImage", string>
>;

type PetPayload = CreatePetPayload & {
  breed?: string;
  birth_date?: string;
  checkup_date?: string;
  notes?: string;
};

const initialForm: PetFormState = {
  petname: "",
  species: "",
  customSpecies: "",
  breed: "",
  gender: "",
  isNeutered: "",
  birthDate: "",
  isBirthUnknown: false,
  weight: "",
  checkupDate: "",
  isCheckupUnknown: false,
  notes: "",
};

const getRandomDefaultProfileImage = () => {
  const randomIndex = Math.floor(Math.random() * defaultProfileImages.length);
  return defaultProfileImages[randomIndex];
};

const normalizeDate = (date?: string) => date?.slice(0, 10) || "";

const normalizeGender = (gender?: string) => {
  if (gender === "male" || gender === "남아") {
    return "수컷";
  }

  if (gender === "female" || gender === "여아") {
    return "암컷";
  }

  return genderOptions.includes(gender || "") ? gender || "" : "";
};

const normalizeNeutered = (isNeutered?: string) =>
  neuteredOptions.includes(isNeutered || "") ? isNeutered || "" : "";

export const getFormFromPet = (pet: Pet): PetFormState => {
  const isKnownSpecies = speciesOptions.includes(pet.species || "");

  return {
    petname: pet.petname || "",
    species: isKnownSpecies ? pet.species || "" : pet.species ? "기타" : "",
    customSpecies: isKnownSpecies ? "" : pet.species || "",
    breed: pet.breed || "",
    gender: normalizeGender(pet.gender),
    isNeutered: normalizeNeutered(pet.is_neutered),
    birthDate: normalizeDate(pet.birth_date),
    isBirthUnknown: Boolean(pet.is_birth_unknown),
    weight: pet.weight_kg ? String(pet.weight_kg) : "",
    checkupDate: normalizeDate(pet.checkup_date),
    isCheckupUnknown: Boolean(pet.is_checkup_unknown),
    notes: pet.notes || "",
  };
};

interface ImageFields {
  profileImage?: string;
  originalImage?: string;
  doodleStrokes?: string;
}

export const getPayloadFromForm = (
  formState: PetFormState,
  images: ImageFields = {},
): PetPayload => ({
  petname: formState.petname.trim(),
  species:
    formState.species === "기타"
      ? formState.customSpecies.trim()
      : formState.species,
  breed: formState.breed.trim(),
  gender: formState.gender,
  is_neutered: formState.isNeutered,
  birth_date:
    !formState.isBirthUnknown && formState.birthDate
      ? formState.birthDate
      : undefined,
  is_birth_unknown: formState.isBirthUnknown,
  weight_kg: Number(formState.weight),
  checkup_date:
    !formState.isCheckupUnknown && formState.checkupDate
      ? formState.checkupDate
      : undefined,
  is_checkup_unknown: formState.isCheckupUnknown,
  notes: formState.notes.trim(),
  ...(images.profileImage ? { profile_image: images.profileImage } : {}),
  ...(images.originalImage ? { original_image: images.originalImage } : {}),
  // 빈 문자열("")도 "그림 없음"을 의미하므로 undefined일 때만 생략(변경 감지용).
  ...(images.doodleStrokes !== undefined
    ? { doodle_strokes: images.doodleStrokes }
    : {}),
});

const getChangedPayload = (
  currentPayload: PetPayload,
  originalPayload: PetPayload,
) =>
  (Object.keys(currentPayload) as Array<keyof PetPayload>).reduce<
    Partial<CreatePetPayload>
  >((changedPayload, key) => {
    if (currentPayload[key] !== originalPayload[key]) {
      return { ...changedPayload, [key]: currentPayload[key] };
    }

    return changedPayload;
  }, {});

interface UsePetFormParams {
  customSpeciesInputRef: RefObject<HTMLInputElement>;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

export const usePetForm = ({ customSpeciesInputRef, t }: UsePetFormParams) => {
  const [form, setForm] = useState<PetFormState>(initialForm);
  const [originalForm, setOriginalForm] = useState<PetFormState | null>(null);
  const [errors, setErrors] = useState<PetFormErrors>({});
  const [previewUrl, setPreviewUrl] = useState("");
  const [originalPreviewUrl, setOriginalPreviewUrl] = useState("");
  // 비파괴 편집 영속 데이터: cleanImageUrl=그림 입히기 전 원본(remote URL),
  // doodleStrokes=그림 stroke JSON 문자열. previewUrl(profile_image)은 표시용 합성본.
  const [cleanImageUrl, setCleanImageUrl] = useState("");
  const [originalCleanImageUrl, setOriginalCleanImageUrl] = useState("");
  const [doodleStrokes, setDoodleStrokes] = useState("");
  const [originalDoodleStrokes, setOriginalDoodleStrokes] = useState("");

  const resetPetFormState = useCallback(() => {
    setForm(initialForm);
    setOriginalForm(null);
    setPreviewUrl("");
    setOriginalPreviewUrl("");
    setCleanImageUrl("");
    setOriginalCleanImageUrl("");
    setDoodleStrokes("");
    setOriginalDoodleStrokes("");
  }, []);

  const applyPetToForm = useCallback((pet: Pet) => {
    const loadedForm = getFormFromPet(pet);
    const loadedProfileImage = pet.profile_image || "";
    const loadedCleanImage = pet.original_image || "";
    const loadedStrokes = pet.doodle_strokes || "";

    setForm(loadedForm);
    setOriginalForm(loadedForm);
    setPreviewUrl(loadedProfileImage);
    setOriginalPreviewUrl(loadedProfileImage);
    setCleanImageUrl(loadedCleanImage);
    setOriginalCleanImageUrl(loadedCleanImage);
    setDoodleStrokes(loadedStrokes);
    setOriginalDoodleStrokes(loadedStrokes);
  }, []);

  const updateForm = <Key extends keyof PetFormState>(
    key: Key,
    value: PetFormState[Key],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));

    if (errors[key]) {
      setErrors((current) => ({ ...current, [key]: undefined }));
    }
  };

  const handleNameChange = (event: ChangeEvent<HTMLInputElement>) => {
    updateForm("petname", event.target.value.slice(0, 15));
  };

  const handleNotesChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    updateForm("notes", event.target.value.slice(0, maxNotesLength));
  };

  const validateForm = () => {
    const nextErrors: PetFormErrors = {};

    if (!form.petname.trim()) {
      nextErrors.petname = t("pet.nameRequired");
    }

    if (!form.species) {
      nextErrors.species = t("pet.speciesRequired");
    }

    if (form.species === "기타" && !form.customSpecies.trim()) {
      nextErrors.customSpecies = t("pet.customSpeciesRequired");
    }

    if (!form.gender) {
      nextErrors.gender = t("pet.genderRequired");
    }

    if (!form.isNeutered) {
      nextErrors.isNeutered = t("pet.neuteredRequired");
    }

    if (!form.weight.trim()) {
      nextErrors.weight = t("pet.weightRequired");
    } else if (Number.isNaN(Number(form.weight)) || Number(form.weight) <= 0) {
      nextErrors.weight = t("pet.weightInvalid");
    }

    setErrors(nextErrors);

    if (nextErrors.customSpecies) {
      window.setTimeout(() => customSpeciesInputRef.current?.focus(), 0);
    }

    return Object.keys(nextErrors).length === 0;
  };

  const buildPayload = (): CreatePetPayload => {
    // 사진 미선택 시 기본 프로필 이미지를 무작위로 부여한다.
    // (업로드 성공 시 previewUrl엔 CloudFront URL이 들어있다 — handleImageChange 참고.
    //  data: 미리보기는 백엔드 validator가 거부하므로 방어적으로 함께 처리)
    const profileImage =
      !previewUrl || previewUrl.startsWith("data:")
        ? getRandomDefaultProfileImage()
        : previewUrl;
    // 원본(clean)이 따로 없으면 합성본=원본으로 간주한다.
    const originalImage =
      !cleanImageUrl || cleanImageUrl.startsWith("data:")
        ? profileImage
        : cleanImageUrl;

    return getPayloadFromForm(form, {
      profileImage,
      originalImage,
      doodleStrokes,
    });
  };

  const buildUpdatePayload = (): Partial<CreatePetPayload> => {
    // 수정 시에도 base64 데이터 URI는 payload에서 제외
    const safePreviewUrl = previewUrl.startsWith("data:") ? originalPreviewUrl : previewUrl;
    const safeOriginalPreviewUrl = originalPreviewUrl.startsWith("data:")
      ? ""
      : originalPreviewUrl;
    const safeCleanUrl = cleanImageUrl.startsWith("data:")
      ? originalCleanImageUrl
      : cleanImageUrl;
    const safeOriginalCleanUrl = originalCleanImageUrl.startsWith("data:")
      ? ""
      : originalCleanImageUrl;

    if (!originalForm) {
      return getPayloadFromForm(form, {
        profileImage: safePreviewUrl,
        originalImage: safeCleanUrl,
        doodleStrokes,
      });
    }

    const originalPayload = getPayloadFromForm(originalForm, {
      profileImage: safeOriginalPreviewUrl,
      originalImage: safeOriginalCleanUrl,
      doodleStrokes: originalDoodleStrokes,
    });
    const currentPayload = getPayloadFromForm(form, {
      profileImage: safePreviewUrl,
      originalImage: safeCleanUrl,
      doodleStrokes,
    });

    return getChangedPayload(currentPayload, originalPayload);
  };

  return {
    form,
    errors,
    previewUrl,
    cleanImageUrl,
    doodleStrokes,
    setErrors,
    setPreviewUrl,
    setCleanImageUrl,
    setDoodleStrokes,
    resetPetFormState,
    applyPetToForm,
    updateForm,
    handleNameChange,
    handleNotesChange,
    validateForm,
    buildPayload,
    buildUpdatePayload,
  };
};
