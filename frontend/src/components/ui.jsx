import { fmt } from "../utils/format";

export const Card = ({ title, right, children, className = "" }) => (
  <section className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
    {(title || right) && (
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
        {right}
      </div>
    )}
    {children}
  </section>
);

const ORIGIN = {
  measured: "bg-emerald-100 text-emerald-800", estimated: "bg-sky-100 text-sky-800",
  simulated: "bg-amber-100 text-amber-800", predicted: "bg-violet-100 text-violet-800",
};
export const OriginBadge = ({ origin }) => (
  <span title={`Data origin: ${origin}`} className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ORIGIN[origin] || "bg-slate-100 text-slate-700"}`}>{origin}</span>
);

export const Stat = ({ label, value, unit, sub, origin }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="flex items-center justify-between text-xs text-slate-500">
      <span>{label}</span>{origin && <OriginBadge origin={origin} />}
    </div>
    <div className="mt-1 text-2xl font-bold text-slate-900">{value}<span className="ml-1 text-sm font-normal text-slate-500">{unit}</span></div>
    {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
  </div>
);

const TONE = { high: "bg-red-100 text-red-800", medium: "bg-amber-100 text-amber-800", low: "bg-emerald-100 text-emerald-800",
  accepted: "bg-emerald-100 text-emerald-800", rejected: "bg-slate-200 text-slate-600", pending: "bg-sky-100 text-sky-800" };
export const Pill = ({ children, tone }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[tone || children] || "bg-slate-100 text-slate-700"}`}>{children}</span>
);

export const Loading = () => <div className="animate-pulse p-6 text-sm text-slate-500">Loading…</div>;
export const ErrorBox = ({ error, onRetry }) => (
  <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
    {error} {onRetry && <button className="ml-2 underline" onClick={onRetry}>Retry</button>}
  </div>
);
export const Empty = ({ title, hint, children }) => (
  <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
    <div className="text-base font-semibold text-slate-700">{title}</div>
    {hint && <p className="mx-auto mt-1 max-w-lg text-sm text-slate-500">{hint}</p>}
    <div className="mt-3">{children}</div>
  </div>
);
export const Btn = ({ children, onClick, disabled, kind = "primary", ...p }) => (
  <button onClick={onClick} disabled={disabled} {...p}
    className={`rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:opacity-50 ${kind === "primary" ? "bg-green-700 text-white hover:bg-green-800" : kind === "danger" ? "bg-red-600 text-white hover:bg-red-700" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}>
    {children}
  </button>
);
export const Select = ({ value, onChange, options, label }) => (
  <label className="flex items-center gap-2 text-sm text-slate-600">{label}
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm">
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </label>
);
export const Table = ({ cols, rows, empty = "No rows" }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-left text-sm">
      <thead className="border-b text-xs uppercase text-slate-500"><tr>{cols.map((c) => <th key={c.key} className="px-2 py-2 font-medium">{c.label}</th>)}</tr></thead>
      <tbody>
        {rows.length === 0 && <tr><td colSpan={cols.length} className="px-2 py-4 text-slate-400">{empty}</td></tr>}
        {rows.map((r, i) => (
          <tr key={r.id ?? i} className="border-b last:border-0 hover:bg-slate-50">
            {cols.map((c) => <td key={c.key} className="px-2 py-2 align-top">{c.render ? c.render(r) : typeof r[c.key] === "number" ? fmt(r[c.key], 3) : String(r[c.key] ?? "")}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
export const PageHeader = ({ title, subtitle, children }) => (
  <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
    <div><h1 className="text-xl font-bold text-slate-900">{title}</h1>{subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}</div>
    <div className="flex flex-wrap items-center gap-2">{children}</div>
  </div>
);
export const SimBanner = ({ origin }) =>
  origin?.contains_simulated ? (
    <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <b>Simulated data.</b> Telemetry here is synthetic and energy/carbon values are <b>estimates</b> from a configurable power model — not metered measurements.
    </div>
  ) : null;
