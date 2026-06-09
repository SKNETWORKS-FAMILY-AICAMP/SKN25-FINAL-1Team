import type {
  PetInfo,
  Prescription,
  PrescriptionDocumentResponse,
} from "../../types/emr";

const prescriptionProductInfo: Record<
  string,
  { quantity: string; product_name: string }
> = {
  "클라벳 시럽": {
    quantity: "1개 (120ml)",
    product_name: "Clavacillin®",
  },
  보호렉스정: {
    quantity: "1개 (6정)",
    product_name: "Boromex Tab®",
  },
  유산균: {
    quantity: "1개 (30포)",
    product_name: "Probiotics Vet®",
  },
};

export function createMockPrescriptionDocument(params: {
  pet: PetInfo;
  prescriptions: Prescription[];
  doctorName: string;
  hospitalName: string;
  ownerName: string;
  queuePosition: number;
  licenseNumber?: string;
}): PrescriptionDocumentResponse {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");

  return {
    code: 200,
    result: {
      issued_at: `${yyyy}년 ${mm}월 ${dd}일`,
      issue_number: `${yyyy}${mm}${dd}-${String(params.queuePosition).padStart(3, "0")}`,
      valid_days: 7,
      pet: {
        name: params.pet.pet_name,
        species:
          params.pet.species === "말티즈" ||
          params.pet.species === "푸들" ||
          params.pet.species === "시바견"
            ? "개"
            : params.pet.species,
        gender: `${params.pet.gender === "Female" ? "암" : "수"} / ${params.pet.age}살 / ${params.pet.weight_kg}kg / 임신 여부 해당없음`,
        owner_name: params.ownerName,
        birth_date: params.pet.birth_date.replace(/\./g, "-"),
      },
      hospital: {
        name: params.hospitalName,
        phone: "-",
        business_number: "-",
        address: "",
      },
      doctor: {
        name: params.doctorName,
        license_number: params.licenseNumber ?? "-",
      },
      prescriptions: params.prescriptions.map((prescription) => {
        const productInfo = prescriptionProductInfo[prescription.drug_name] ?? {
          quantity: "1개",
          product_name: "-",
        };

        return {
          ingredient: prescription.drug_name,
          dosage: prescription.dosage,
          frequency: `${prescription.form} ${prescription.frequency}`,
          duration_days: prescription.duration_days,
          quantity: productInfo.quantity,
          product_name: productInfo.product_name,
          pil_seon: prescription.pil_seon ?? "",
        };
      }),
    },
  };
}
