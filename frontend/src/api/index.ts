import { apiClient } from "./client";
import type { AnalysisDetail, AnalyzeResponse, AuthResponse, DashboardData, HistoryItem, Profile } from "../types/api";

export const authApi = {
  me: () => apiClient.get<AuthResponse>("/auth/me"),
  login: (payload: { username: string; password: string }) => apiClient.post<AuthResponse>("/auth/login", payload),
  logout: () => apiClient.post<{ status: string }>("/auth/logout")
};

export const profilesApi = {
  list: () => apiClient.get<Profile[]>("/profiles"),
  create: (payload: Omit<Profile, "id" | "user_id" | "created_at" | "updated_at">) => apiClient.post<Profile>("/profiles", payload),
  update: (id: number, payload: Omit<Profile, "id" | "user_id" | "created_at" | "updated_at">) => apiClient.put<Profile>(`/profiles/${id}`, payload),
  remove: (id: number) => apiClient.delete<{ status: string }>(`/profiles/${id}`),
  select: (id: number) => apiClient.post<Profile>(`/profiles/${id}/select`)
};

export const analysisApi = {
  analyze: (payload: { profile_id: number; recipe_text: string }) => apiClient.post<AnalyzeResponse>("/analyze", payload),
  history: () => apiClient.get<HistoryItem[]>("/history"),
  historyItem: (id: number) => apiClient.get<AnalysisDetail>(`/history/${id}`),
  dashboard: (profileId?: number) => apiClient.get<DashboardData>(`/dashboard${profileId ? `?profile_id=${profileId}` : ""}`)
};
