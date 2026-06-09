import type {
  PetInfo,
  Prescription,
  PrescriptionDocumentResponse,
} from "../../types/emr";

export function buildPrescriptionDocument(params: {
  pet: PetInfo;
  prescriptions: Prescription[];
  doctorName: string;
  hospitalName: string;
  ownerName: string;
  queuePosition: number;
  licenseNumber?: string;
  hospitalPhone?: string;
  businessNumber?: string;
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
        species: params.pet.species,
        gender: `${params.pet.gender === "Female" ? "암" : "수"} / ${params.pet.age}살 / ${params.pet.weight_kg}kg / 임신 여부 해당없음`,
        owner_name: params.ownerName,
        birth_date: params.pet.birth_date.replace(/\./g, "-"),
      },
      hospital: {
        name: params.hospitalName,
        phone: params.hospitalPhone ?? "-",
        business_number: params.businessNumber ?? "-",
        address: "",
      },
      doctor: {
        name: params.doctorName,
        license_number: params.licenseNumber ?? "-",
      },
      prescriptions: params.prescriptions.map((prescription) => ({
        ingredient: prescription.drug_name,
        dosage: prescription.dosage,
        frequency: `${prescription.form} ${prescription.frequency}`,
        duration_days: prescription.duration_days,
        quantity: "1개",
        product_name: "-",
        pil_seon: prescription.pil_seon ?? "",
      })),
    },
  };
}
