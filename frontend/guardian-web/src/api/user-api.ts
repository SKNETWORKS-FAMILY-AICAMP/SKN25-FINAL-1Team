import { apiClient } from "./api-client";

export interface MyProfile {
  name: string;
  phone: string;
  created_at: string;
}

export interface UpdateMyProfileRequest {
  name: string;
  phone: string;
}

export interface UpdateMyProfileResponse {
  message: string;
}

export interface ChangeMyPasswordRequest {
  current_password: string;
  new_password: string;
  new_password_confirm: string;
}

export interface ChangeMyPasswordResponse {
  message: string;
}

export const getMyProfile = async (): Promise<MyProfile> => {
  const response = await apiClient.get<MyProfile>("/users/me");
  return response.data;
};

export const updateMyProfile = async (
  data: UpdateMyProfileRequest,
): Promise<UpdateMyProfileResponse> => {
  const response = await apiClient.put<UpdateMyProfileResponse>(
    "/users/me",
    data,
  );
  return response.data;
};

export const changeMyPassword = async (
  data: ChangeMyPasswordRequest,
): Promise<ChangeMyPasswordResponse> => {
  const response = await apiClient.put<ChangeMyPasswordResponse>(
    "/users/me/password",
    data,
  );
  return response.data;
};
