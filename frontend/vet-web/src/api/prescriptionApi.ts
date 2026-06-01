import { apiClient } from "./client";

export interface DrugSearchResult {
  drugid: number;
  name: string;
  ingredient_kr: string | null;
  dosage: string | null;
  usage_method: string | null;
  duration_days: number | null;
}

export interface DrugSearchResponse {
  code: number;
  result: DrugSearchResult[];
}

export async function searchDrugs(params: {
  accessToken: string;
  keyword: string;
}): Promise<DrugSearchResult[]> {
  const { data } = await apiClient.get<DrugSearchResponse>("/drugs/search", {
    headers: { Authorization: `Bearer ${params.accessToken}` },
    params: { keyword: params.keyword },
  });
  return data.result;
}
