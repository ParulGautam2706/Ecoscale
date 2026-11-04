import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { errMsg, post } from "../services/api";
import ResourceSelect from "../components/ResourceSelect";
import { Btn, Card, ErrorBox, OriginBadge, PageHeader, Pill, Table } from "../components/ui";
import { fmt } from "../utils/format";

const PRESETS = [
  { name: "Reduce CPU 25%", type: "reduce_cpu", percent: 25 }, { name: "Reduce memory 30%", type: "reduce_memory", percent: 30 },
  { name: "Region → eu-north", type: "region", region: "eu-north" }, { name: "Region → us-west", type: "region", region: "us-west" },
  { name: "Shift +6 h", type: "shift", offset_hours: 6 }, { name: "Instance → gp.large", type: "instance", instance_type: "gp.large" },
  { name: "Instance → gp.medium", type: "instance", instance_type: "gp.medium" },
];
const Delta = ({ v, unit = "%", goodNegative = true }) => {
  if (v === 0 || v === undefined) return <span className="text-slate-400">±0</span>;
  const good = goodNegative ? v < 0 : v > 0;
  return <span className={good ? "text-emerald-700" : "text-red-600"}>{v > 0 ? "+" : ""}{fmt(v, 2)}{unit}</span>;
};

export default function Simulator() {
  const [rid, setRid] = useState("3");
  const [picked, setPicked] = useState([PRESETS[2]]);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const toggle = (p) => setPicked((x) => (x.includes(p) ? x.filter((i) => i !== p) : [...x, p]));
  const run = async () => { setBusy(true); setErr(null); try { setRes(await post("/simulate", { resource_id: Number(rid), scenarios: picked })); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); } };
  return (
    <>
      <PageHeader title="What-If Simulator" subtitle="Every scenario uses the same workload profile and assumptions, so comparisons are fair.">
        <ResourceSelect value={rid} onChange={setRid} />
        <Btn onClick={run} disabled={busy || picked.length === 0}>{busy ? "Simulating…" : "Run simulation"}</Btn>
      </PageHeader>
      {err && <div className="mb-3"><ErrorBox error={err} /></div>}
      <Card title="Choose scenarios" className="mb-4">
        <div className="flex flex-wrap gap-2">{PRESETS.map((p) => (
          <button key={p.name} onClick={() => toggle(p)} className={`rounded-full border px-3 py-1 text-sm ${picked.includes(p) ? "border-green-700 bg-green-700 text-white" : "border-slate-300 bg-white text-slate-700"}`}>{p.name}</button>))}</div>
      </Card>
      {res && (
        <div className="space-y-4">
          <Card title={`Before vs after — ${res.resource}`} right={<OriginBadge origin={res.origin} />}>
            <Table cols={[
              { key: "name", label: "Scenario", render: (r) => <b>{r.name}</b> },
              { key: "e", label: "Energy kWh/d", render: (r) => <>{fmt(r.metrics.energy_kwh_day)} <Delta v={r.delta_vs_current.energy_kwh_day_pct} /></> },
              { key: "c", label: "CO₂e kg/d", render: (r) => <>{fmt(r.metrics.co2e_kg_day)} <Delta v={r.delta_vs_current.co2e_kg_day_pct} /></> },
              { key: "k", label: "Cost $/d", render: (r) => <>{fmt(r.metrics.cost_usd_day)} <Delta v={r.delta_vs_current.cost_usd_day_pct} /></> },
              { key: "l", label: "Latency ms", render: (r) => <>{fmt(r.metrics.latency_ms, 0)} <Delta v={r.delta_vs_current.latency_ms_abs} unit=" ms" /></> },
              { key: "u", label: "p95 CPU", render: (r) => `${fmt(r.metrics.cpu_util_p95 * 100, 0)}%` },
              { key: "s", label: "SLA risk", render: (r) => <>{fmt(r.metrics.sla_risk, 3)} <Delta v={r.delta_vs_current.sla_risk_abs} unit="" /></> },
              { key: "v", label: "Constraints", render: (r) => (r.metrics.constraint_violations.length ? <Pill tone="high">{r.metrics.constraint_violations.join(", ")}</Pill> : <Pill tone="low">ok</Pill>) },
            ]} rows={res.results.map((r, i) => ({ ...r, id: i }))} />
            <p className="mt-2 text-xs text-slate-500">{res.note}</p>
          </Card>
          <Card title="Carbon and cost by scenario">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={res.results.map((r) => ({ name: r.name, co2e: r.metrics.co2e_kg_day, cost: r.metrics.cost_usd_day }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" interval={0} /><YAxis /><Tooltip /><Legend />
                <Bar dataKey="co2e" name="kgCO₂e/day" fill="#16a34a" /><Bar dataKey="cost" name="$/day" fill="#0ea5e9" /></BarChart>
            </ResponsiveContainer>
            <ul className="mt-2 list-disc pl-5 text-xs text-slate-500">{[...new Set(res.results.flatMap((r) => r.assumptions))].map((a) => <li key={a}>{a}</li>)}</ul>
          </Card>
        </div>)}
    </>
  );
}
