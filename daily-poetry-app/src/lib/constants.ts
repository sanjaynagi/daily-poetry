const PROD_API_BASE_URL = "https://daily-poetry-api.vercel.app";
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : PROD_API_BASE_URL);
export const VAPID_PUBLIC_KEY = import.meta.env.VITE_VAPID_PUBLIC_KEY ?? "";

export const STORAGE_KEYS = {
  cachedDaily: "daily-poetry.cached-daily",
  favourites: "daily-poetry.favourites",
  authToken: "daily-poetry.auth-token",
  theme: "daily-poetry.theme",
};
