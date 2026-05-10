import axios from "axios";
import { toAppPath } from "@/lib/routes";
import { API_BASE_PATH } from "@/lib/api-base";
import { clearStoredAuthUser, setStoredAuthUser } from "@/lib/auth-user";

const API_BASE = API_BASE_PATH;

const api = axios.create({
  baseURL: API_BASE,
});

function clearAuthSession() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  clearStoredAuthUser();
}

function redirectToLogin() {
  if (typeof window !== "undefined") {
    window.location.href = toAppPath("/login", window.location.pathname);
  }
}

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
  if (!refreshToken) {
    clearAuthSession();
    redirectToLogin();
    throw new Error("Your session has expired. Please sign in again.");
  }

  try {
    const refreshResponse = await axios.post(`${API_BASE}/auth/refresh`, {
      refresh_token: refreshToken,
    });

    const { access_token, refresh_token, user } = refreshResponse.data?.data ?? {};
    if (!access_token) {
      throw new Error("Token refresh failed.");
    }

    localStorage.setItem("access_token", access_token);
    if (refresh_token) {
      localStorage.setItem("refresh_token", refresh_token);
    }
    if (user) {
      setStoredAuthUser(user);
    }

    return access_token;
  } catch (error) {
    const message = axios.isAxiosError(error)
      ? error.response?.data?.message || error.response?.data?.detail || "Your session has expired. Please sign in again."
      : error instanceof Error
        ? error.message
        : "Your session has expired. Please sign in again.";
    clearAuthSession();
    redirectToLogin();
    throw new Error(message);
  }
}

api.interceptors.request.use((config) => {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const accessToken = await refreshAccessToken();
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
