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

// On a hard reload, zustand's persist middleware rehydrates the store from
// sessionStorage asynchronously (deliberately, to avoid an SSR/CSR hydration
// mismatch — the client's first render must match the server's default-state
// render before the persisted value can apply). Most pages fire their first
// data fetch immediately on mount, well before that rehydration lands, so
// `useAuthStore.getState().accessToken` is still null for that first request.
// Reading sessionStorage directly here is a synchronous fallback for exactly
// that window — no async/await needed, and no dependency on persist's timing.
function readPersistedToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem("auth-token-mirror");
    return raw ? (JSON.parse(raw)?.state?.accessToken ?? null) : null;
  } catch {
    return null;
  }
}

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken ?? readPersistedToken();
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
