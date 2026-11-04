import axios from "axios";

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || "/api/v1" });

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("gc_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
api.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response?.status === 401 && !e.config.url.includes("/auth/login")) {
      localStorage.removeItem("gc_token");
      window.location.href = "/login";
    }
    return Promise.reject(e);
  }
);

export const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (d) return typeof d === "string" ? d : JSON.stringify(d);
  return e?.message || "Request failed";
};

export const auth = {
  login: async (email, password) => {
    const f = new URLSearchParams({ username: email, password });
    const { data } = await api.post("/auth/login", f);
    localStorage.setItem("gc_token", data.access_token);
  },
  register: (email, password) => api.post("/auth/register", { email, password }),
  me: () => api.get("/auth/me").then((r) => r.data),
  logout: () => localStorage.removeItem("gc_token"),
  isLoggedIn: () => !!localStorage.getItem("gc_token"),
};

export const get = (url, params) => api.get(url, { params }).then((r) => r.data);
export const post = (url, body) => api.post(url, body ?? {}).then((r) => r.data);
export const patch = (url, body) => api.patch(url, body).then((r) => r.data);
export const put = (url, body) => api.put(url, body).then((r) => r.data);
export const download = async (url, body, filename) => {
  const r = await api.post(url, body, { responseType: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(r.data);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
};
export default api;
