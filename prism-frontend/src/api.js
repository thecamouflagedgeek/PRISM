// All frontend requests use this single deployment setting.
export const API_BASE_URL = (import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")).replace(/\/$/, "");
