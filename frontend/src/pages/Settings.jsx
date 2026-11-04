import { useEffect, useState } from "react";
import useApi from "../hooks/useApi";
import { errMsg, get, put } from "../services/api";
import { Btn, Card, ErrorBox, Loading, PageHeader } from "../components/ui";

const HELP = {
  thresholds: "Right-sizing / idle / shifting rules (defaults from the reference paper where applicable).",
  weights: "Objective weights for J = w1·Carbon + w2·Cost + w3·Latency + w4·SLA risk. Normalised to sum to 1 on save.",
  limits: "Capacity, data-transfer, cost-increase and latency limits used by the optimizer.",
  energy: "Power-model coefficients. Set calibrated=true only if you have calibrated them against metered hardware.",
  monitoring: "Collector interval (seconds).",
};

function Group({ name, values, reload }) {
  const [form, setForm] = useState(values);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => setForm(values), [values]);
  const save = async () => {
    setErr(null); setMsg(null);
    const body = {};
    for (const [k, v] of Object.entries(form)) body[k] = typeof values[k] === "boolean" ? v === true || v === "true" : v === "" || v === null ? values[k] : Number(v);
    try { await put(`/settings/${name}`, body); setMsg("Saved"); reload(); } catch (e) { setErr(errMsg(e)); }
  };
  return (
    <Card title={name[0].toUpperCase() + name.slice(1)} right={<Btn onClick={save}>Save</Btn>}>
      <p className="mb-3 text-xs text-slate-500">{HELP[name]}</p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {Object.entries(form).map(([k, v]) => (
          <label key={k} className="text-xs text-slate-500">{k}
            {typeof values[k] === "boolean" ? (
              <select className="mt-1 block w-full rounded border px-2 py-1 text-sm" value={String(v)} onChange={(e) => setForm({ ...form, [k]: e.target.value })}><option>true</option><option>false</option></select>
            ) : <input type="number" step="any" className="mt-1 block w-full rounded border px-2 py-1 text-sm text-slate-900" value={v ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />}
          </label>))}
      </div>
      {msg && <p className="mt-2 text-sm text-emerald-700">{msg}</p>}
      {err && <div className="mt-2"><ErrorBox error={err.includes("Admin") ? "Only admins can change settings." : err} /></div>}
    </Card>
  );
}

export default function Settings() {
  const { data, loading, error, reload } = useApi(() => get("/settings"), []);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="Settings" subtitle="All assumptions are configurable. Changing them affects future analyses; admin only." />
      <div className="space-y-4">{Object.entries(data).map(([k, v]) => <Group key={k} name={k} values={v} reload={reload} />)}</div>
    </>
  );
}
