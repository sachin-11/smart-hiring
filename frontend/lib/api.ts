import axios, { AxiosError, type AxiosInstance } from "axios";

import { useAuthStore } from "@/lib/store/auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30_000,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      console.error(
        `[api] ${error.response.status} ${error.config?.method?.toUpperCase()} ${error.config?.url}`,
        error.response.data,
      );
    } else if (error.request) {
      console.error(`[api] No response received for ${error.config?.url}`, error.message);
    } else {
      console.error("[api] Request setup error", error.message);
    }
    return Promise.reject(error);
  },
);

export default api;
