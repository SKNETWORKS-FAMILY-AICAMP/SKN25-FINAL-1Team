import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { getPets, type Pet } from "../../api/pets-api";
import PageHeader from "../../components/common/page-header";
import { startGuardianProductTour } from "../../components/product-tour";
import CheckupReservationModal from "../../components/schedule/checkup-reservation-modal";
import GuardianLayout from "../../layouts/guardian-layout";
import { useTranslation } from "../../i18n/language-context";

const petRegisterPath = "/pets/register";

const previewPets: Pet[] = [
  {
    pet_id: 1,
    petname: "뽀삐",
    species: "강아지",
    breed: "말티즈",
    age: 4,
    gender: "남아",
    profile_image: "/assets/profile1.png",
  },
  {
    pet_id: 2,
    petname: "두부",
    species: "강아지",
    breed: "말티즈",
    age: 4,
    gender: "남아",
    profile_image: "/assets/profile2.png",
  },
  {
    pet_id: 3,
    petname: "콩이",
    species: "강아지",
    breed: "말티즈",
    age: 4,
    gender: "남아",
    profile_image: "/assets/profile3.png",
  },
];

const defaultProfileImages = [
  "/assets/profile1.png",
  "/assets/profile2.png",
  "/assets/profile3.png",
  "/assets/profile4.png",
  "/assets/profile5.png",
  "/assets/profile6.png",
];

const getProfileImage = (pet: Pet) =>
  pet.profile_image ||
  defaultProfileImages[Math.abs(pet.pet_id) % defaultProfileImages.length];

const sortPetsByName = (petsToSort: Pet[]) =>
  [...petsToSort].sort((firstPet, secondPet) =>
    firstPet.petname.localeCompare(secondPet.petname, "ko"),
  );

const PetIllustration = ({ alt }: { alt: string }) => (
  <img
    src="/assets/medi-paw-logo.png"
    alt={alt}
    className="mx-auto h-56 w-auto object-contain"
  />
);

const HomePage = () => {
  const { t, lang } = useTranslation();
  const normalizeSpecies = (species?: string) => {
    if (!species) return undefined;
    if (species === "강아지" || species === "dog") return t("pet.speciesDog");
    if (species === "고양이" || species === "cat") return t("pet.speciesCat");
    if (species === "기타" || species === "other") return t("pet.speciesOther");
    return species;
  };
  const normalizeGender = (gender?: string) => {
    if (!gender) return undefined;
    if (gender === "male" || gender === "수컷" || gender === "남아") {
      return t("home.genderMale");
    }
    if (gender === "female" || gender === "암컷" || gender === "여아") {
      return t("home.genderFemale");
    }
    if (gender === "모름" || gender === "unknown") return t("pet.unknown");
    return gender;
  };
  const normalizeBreed = (breed?: string) => {
    if (!breed) return undefined;
    const breedMap: Record<string, Record<string, string>> = {
      말티즈: {
        ko: "말티즈",
        en: "Maltese",
        ja: "マルチーズ",
        zh: "马尔济斯",
      },
      코리안숏헤어: {
        ko: "코리안숏헤어",
        en: "Korean Shorthair",
        ja: "コリアンショートヘア",
        zh: "韩国短毛猫",
      },
    };
    return breedMap[breed]?.[lang] || breed;
  };
  const getPetMeta = (pet: Pet) =>
    [
      normalizeBreed(pet.breed) || normalizeSpecies(pet.species),
      pet.age ? t("home.yearsOld", { age: pet.age }) : undefined,
      normalizeGender(pet.gender),
    ]
      .filter(Boolean)
      .join(" · ");
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const previewMode = import.meta.env.DEV ? searchParams.get("preview") : null;
  const isEmptyPreview = previewMode === "empty";
  const isPetsPreview = previewMode === "pets";
  const [pets, setPets] = useState<Pet[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [reservationPet, setReservationPet] = useState<Pet | null>(null);

  const hasPets = pets.length > 0;
  const refreshRequestedAt =
    (location.state as { petRegisteredAt?: number; petUpdatedAt?: number } | null)
      ?.petRegisteredAt ||
    (location.state as { petRegisteredAt?: number; petUpdatedAt?: number } | null)
      ?.petUpdatedAt;

  useEffect(() => {
    if (isPetsPreview) {
      setIsLoading(false);
      setErrorMessage("");
      setPets(sortPetsByName(previewPets));
      return;
    }

    if (isEmptyPreview) {
      setIsLoading(false);
      setErrorMessage("");
      setPets([]);
      return;
    }

    let isMounted = true;

    const loadPets = async () => {
      try {
        setIsLoading(true);
        setErrorMessage("");

        const response = await getPets();

        if (!isMounted) {
          return;
        }

        if (response.length === 0) {
          setPets([]);
          return;
        }

        setPets(sortPetsByName(response));
      } catch (error) {
        if (!isMounted) {
          return;
        }

        if (isAxiosError<{ message?: string }>(error)) {
          setErrorMessage(
            error.response?.data?.message || t("home.petsLoadError"),
          );
          return;
        }

        setErrorMessage(t("home.petsLoadError"));
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadPets();

    return () => {
      isMounted = false;
    };
  }, [isEmptyPreview, isPetsPreview, refreshRequestedAt]);

  // 챗봇의 '바로 예약하기'에서 넘어온 경우(?reserve=<petId>) → 해당 반려동물 예약 모달 자동 오픈.
  useEffect(() => {
    const reserveId = Number(searchParams.get("reserve"));
    if (!reserveId || pets.length === 0) return;
    const pet = pets.find((p) => p.pet_id === reserveId);
    if (pet) setReservationPet(pet);
    // 쿼리 제거(뒤로가기/새로고침 시 재오픈 방지).
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("reserve");
      return next;
    }, { replace: true });
  }, [pets, searchParams, setSearchParams]);

  return (
    <GuardianLayout>
      {isLoading ? (
        <section className="flex flex-1 items-center justify-center">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
        </section>
      ) : errorMessage ? (
        <section className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-md rounded-3xl bg-white px-6 py-10 text-center border border-slate-100 shadow-sm">
            <h1 className="text-xl font-bold text-slate-900">
              {t("home.loadError")}
            </h1>
            <p className="mt-3 text-sm font-medium leading-6 text-slate-500">
              {errorMessage}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-6 inline-flex h-11 items-center justify-center rounded-2xl bg-blue-600 px-5 text-sm font-bold text-white transition hover:bg-blue-700"
            >
              {t("common.retry")}
            </button>
          </div>
        </section>
      ) : !hasPets ? (
        <section className="flex flex-1 flex-col pb-8">
          <PageHeader
            title={t("home.title")}
            description={t("home.description")}
            rightAction={
              <div className="flex flex-wrap items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={startGuardianProductTour}
                  className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-600 transition hover:border-blue-200 hover:text-blue-600"
                >
                  튜토리얼
                </button>
                <Link
                  to={petRegisterPath}
                  className="inline-flex h-11 items-center justify-center rounded-xl bg-blue-600 px-6 text-sm font-bold text-white transition hover:bg-blue-700"
                >
                  {t("home.registerLong")}
                </Link>
              </div>
            }
          />
          <div data-tour="guardian-home" className="flex flex-1 w-full min-h-[480px] items-center justify-center rounded-2xl border border-slate-100 bg-white p-8 shadow-sm">
            <div className="text-center">
              <PetIllustration alt={t("home.registerAlt")} />
              <h2 className="mt-8 text-2xl font-bold text-slate-800">
                {t("home.emptyTitle")}
              </h2>
              <p className="mx-auto mt-4 max-w-sm text-sm font-semibold leading-6 text-slate-500">
                {t("home.emptyDescription")}
              </p>
            </div>
          </div>
        </section>
      ) : (
        <section className="flex flex-1 flex-col pb-8">
          <PageHeader
            title={t("home.title")}
            description={t("home.description")}
            rightAction={
              <div className="flex flex-wrap items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={startGuardianProductTour}
                  className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-600 transition hover:border-blue-200 hover:text-blue-600"
                >
                  튜토리얼
                </button>
                <Link
                  to={petRegisterPath}
                  className="inline-flex h-11 items-center justify-center rounded-xl bg-blue-600 px-4 text-sm font-bold text-white transition hover:bg-blue-700"
                >
                  {t("home.registerShort")}
                </Link>
              </div>
            }
          />

          <div data-tour="guardian-home" className="flex-1 min-h-[480px] rounded-2xl border border-slate-100 bg-white p-8 shadow-sm">
            <div className="mb-3 text-sm font-bold text-slate-500">
              {t("home.registeredCount", { count: pets.length })}
            </div>

            <div className="space-y-3">
              {pets.map((pet) => (
                <article
                  key={pet.pet_id}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-4 transition hover:border-slate-300 hover:bg-slate-100/70 hover:shadow-sm sm:flex sm:items-center sm:gap-5"
                >
                  <div className="mx-auto h-24 w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100 sm:mx-0">
                    <img
                      src={getProfileImage(pet)}
                      alt={t("common.petProfileAlt", { name: pet.petname })}
                      className="h-full w-full object-cover"
                    />
                  </div>

                  <div className="mt-3 min-w-0 flex-1 text-center sm:mt-0 sm:text-left">
                    <h2 className="text-base font-extrabold text-slate-950">
                      {pet.petname}
                    </h2>
                    <p className="mt-1 text-sm font-semibold text-slate-500">
                      {getPetMeta(pet) || pet.species || t("home.petFallback")}
                    </p>

                    <div className="mt-3 border-t border-slate-200 pt-3">
                      <div className="grid gap-2 sm:max-w-[620px] sm:grid-cols-3">
                        <Link
                          to={`/pets/${pet.pet_id}`}
                          className="inline-flex h-9 items-center justify-center rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                        >
                          {t("home.detail")}
                        </Link>
                        <button
                          type="button"
                          onClick={() => setReservationPet(pet)}
                          className="inline-flex h-9 items-center justify-center rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                        >
                          {t("home.reserve")}
                        </button>
                        <Link
                          to={`/chatbot?petId=${pet.pet_id}`}
                          className="inline-flex h-9 items-center justify-center rounded-lg bg-blue-600 px-3 text-sm font-bold text-white transition hover:bg-blue-700"
                        >
                          {t("home.chatConsult")}
                        </Link>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      )}

      {reservationPet ? (
        <CheckupReservationModal
          pet={reservationPet}
          pets={pets}
          onChangePet={setReservationPet}
          onClose={() => setReservationPet(null)}
        />
      ) : null}
    </GuardianLayout>
  );
};

export default HomePage;
