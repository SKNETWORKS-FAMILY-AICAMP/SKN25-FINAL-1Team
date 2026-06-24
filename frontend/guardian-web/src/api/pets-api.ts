import { apiClient } from "./api-client";

export interface Pet {
  pet_id: number;
  petname: string;
  species?: string;
  breed?: string;
  gender?: string;
  is_neutered?: string;
  age?: number;
  birth_date?: string;
  is_birth_unknown?: boolean;
  weight_kg?: number;
  checkup_date?: string;
  is_checkup_unknown?: boolean;
  notes?: string;
  profile_image?: string;
  original_image?: string;
  doodle_strokes?: string;
}

export interface CreatePetPayload {
  petname: string;
  species: string;
  breed?: string;
  gender: string;
  is_neutered: string;
  birth_date?: string;
  is_birth_unknown?: boolean;
  weight_kg: number;
  checkup_date?: string;
  is_checkup_unknown?: boolean;
  notes?: string;
  profile_image?: string;
  original_image?: string;
  doodle_strokes?: string;
}

export interface CreatePetResponse {
  pet_id: number;
  message: string;
}

export interface UpdatePetResponse {
  message: string;
}

export const getPets = async (): Promise<Pet[]> => {
  const response = await apiClient.get<Pet[]>("/pets");
  return response.data;
};

export const getPet = async (petId: number): Promise<Pet> => {
  const response = await apiClient.get<Pet>(`/pets/${petId}`);
  return response.data;
};

export const createPet = async (
  payload: CreatePetPayload,
): Promise<CreatePetResponse> => {
  const response = await apiClient.post<CreatePetResponse>("/pets", payload);
  return response.data;
};

export const updatePet = async (
  petId: number,
  payload: Partial<CreatePetPayload>,
): Promise<UpdatePetResponse> => {
  const response = await apiClient.put<UpdatePetResponse>(
    `/pets/${petId}`,
    payload,
  );
  return response.data;
};

export interface PetMessageResponse {
  message: string;
}

// 보관(숨김) — 기본 '삭제' 동작. 곧장 지우지 않고 보관함으로 옮긴다.
// 기본 목록·채팅 시작·신규 예약에서 제외되며, 보관함에서 복원할 수 있다.
export const archivePet = async (
  petId: number,
): Promise<PetMessageResponse> => {
  const response = await apiClient.delete<PetMessageResponse>(`/pets/${petId}`);
  return response.data;
};

// 보관함 목록(숨김 처리된 반려동물).
export const getArchivedPets = async (): Promise<Pet[]> => {
  const response = await apiClient.get<Pet[]>("/pets/archived");
  return response.data;
};

// 보관 해제(복원) — 보관함의 반려동물을 다시 기본 목록으로.
export const restorePet = async (
  petId: number,
): Promise<PetMessageResponse> => {
  const response = await apiClient.post<PetMessageResponse>(
    `/pets/${petId}/restore`,
  );
  return response.data;
};

// 영구 삭제 — 보관함에서만 가능. 연결된 진료/상담 기록이 있으면 서버가 409로 막고,
// 해당 기록은 법령·병원 보관 정책에 따라 일정 기간 보관됨을 안내한다(반려동물은 보관함에 남음).
export const permanentlyDeletePet = async (
  petId: number,
): Promise<PetMessageResponse> => {
  const response = await apiClient.delete<PetMessageResponse>(
    `/pets/${petId}/permanent`,
  );
  return response.data;
};
