import { memo } from "react";
import { PawPrint } from "lucide-react";
import { Link } from "react-router-dom";

import type { Pet } from "../../api/pets-api";
import { useTranslation } from "../../i18n/language-context";

interface PetSelectorProps {
  pets: Pet[];
  selectedPetId: number | null;
  isLoadingPets: boolean;
  onSelectPet: (petId: number) => void;
  getProfileImage: (pet: Pet) => string;
}

const PetSelector = ({
  pets,
  selectedPetId,
  isLoadingPets,
  onSelectPet,
  getProfileImage,
}: PetSelectorProps) => {
  const { t } = useTranslation();

  return (
    <aside className="flex h-[220px] flex-col border-b border-slate-100 bg-slate-50/70 lg:h-auto lg:min-h-0 lg:border-b-0 lg:border-r">
      <div className="flex h-14 shrink-0 items-center justify-center border-b border-slate-100 px-3">
        <h2 className="text-center text-[15px] font-bold text-slate-900">
          {t("chatbot.pets")}
        </h2>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3">
        {isLoadingPets ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="h-9 w-9 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
          </div>
        ) : pets.length === 0 ? (
          <div className="flex flex-1 flex-col items-center px-2 pt-[150px] text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
              <PawPrint className="h-8 w-8" />
            </div>
            <p className="mt-3 text-[13px] font-bold leading-5 text-slate-600">
              {t("chatbot.noPets")}
            </p>
            <Link
              to="/pets/register"
              className="mt-3 inline-flex h-10 w-full items-center justify-center rounded-xl bg-blue-600 px-4 text-sm font-bold text-white transition hover:bg-blue-700"
            >
              {t("chatbot.registerPet")}
            </Link>
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {pets.map((pet) => {
              const isSelected = pet.pet_id === selectedPetId;

              return (
                <button
                  key={pet.pet_id}
                  type="button"
                  onClick={() => onSelectPet(pet.pet_id)}
                  className={[
                    "flex w-full items-center gap-2 rounded-2xl border p-2 text-left transition",
                    isSelected
                      ? "border-blue-200 bg-blue-50 shadow-sm"
                      : "border-transparent bg-white hover:border-blue-100 hover:bg-blue-50/60",
                  ].join(" ")}
                >
                  <img
                    src={getProfileImage(pet)}
                    alt={t("chatbot.petProfileAlt", { name: pet.petname })}
                    className="h-11 w-11 rounded-full object-cover ring-2 ring-white"
                  />
                  <span className="min-w-0 flex-1 truncate text-sm font-extrabold text-slate-900">
                    {pet.petname}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
};

export default memo(PetSelector);
