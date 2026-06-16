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
