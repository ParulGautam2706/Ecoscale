import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { auth, get } from "../services/api";

const NAV = [
  ["/", "Dashboard"], ["/monitoring", "Resource Monitoring"], ["/carbon", "Carbon Analytics"], ["/predictions", "AI Predictions"],
  ["/optimization", "Resource Optimization"], ["/cost", "Cost Analysis"], ["/explain", "Explainable AI"], ["/simulator", "What-If Simulator"],
  ["/anomalies", "Anomaly Detection"], ["/reports", "Reports"], ["/settings", "Settings"],
];

export default function AppLayout() {
  const nav = useNavigate();
  const [me, setMe] = useState(null);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("");
  useEffect(() => { auth.me().then(setMe).catch(() => {}); get("/health").then((h) => setMode(h.data_mode)).catch(() => {}); }, []);
  return (
    <div className="flex min-h-screen">
      <aside className={`${open ? "block" : "hidden"} fixed inset-y-0 z-20 w-60 bg-green-950 p-4 text-green-50 md:static md:block`}>
        <div className="mb-6 text-lg font-bold">🌱 GreenCloud AI <span className="text-xs font-normal text-green-300">2.0</span></div>
        <nav className="space-y-1">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-green-700 text-white" : "text-green-100 hover:bg-green-900"}`}>{label}</NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-between border-b bg-white px-4 py-2">
          <button className="rounded border px-2 py-1 text-sm md:hidden" onClick={() => setOpen(!open)}>☰</button>
          <div className="text-xs text-slate-500">Data mode: <b className="text-slate-700">{mode || "…"}</b> · advisory-only recommendations</div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">{me?.email} <span className="text-xs text-slate-400">({me?.role})</span></span>
            <button className="text-green-700 underline" onClick={() => { auth.logout(); nav("/login"); }}>Sign out</button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl p-4 md:p-6"><Outlet /></main>
      </div>
    </div>
  );
}
