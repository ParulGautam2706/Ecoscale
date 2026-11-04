import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useApi from "../hooks/useApi";
import { errMsg, get, post } from "../services/api";
import { Btn, Card, Empty, ErrorBox, Loading, PageHeader, Pill, Select, SimBanner, Stat } from "../components/ui";
import { day, fmt, pct } from "../utils/format";

export default function Dashboard() {
  const [region, setRegion] = useState("");
  const [days, setDays] = useState("7");
  const [seedErr, setSeedErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const { data, loading, error, reload } = useApi(() => get("/dashboard/summary", { region: region || undefined, days }), [region, days]);
  const regions = useApi(() => get("/regions"), []);
  const seed = async () => { setBusy(true); setSeedErr(null); try { await post("/admin/seed", { days: 7, interval_s: 300 }); await reload(); } catch (e) { setSeedErr(errMsg(e)); } finally { setBusy(false); } };

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Estimated energy, carbon and cost across your fleet">
        <Select label="Region" value={region} onChange={setRegion} options={[{ value: "", label: "All regions" }, ...(regions.data || []).map((r) => ({ value: r.code, label: r.code }))]} />
        <Select label="Window" value={days} onChange={setDays} options={[1, 3, 7, 14, 30].map((d) => ({ value: d, label: `Last ${d} d` }))} />
      </PageHeader>
      {loading && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data?.empty && (
        <Empty title="No telemetry yet" hint="Load simulated demo data (admin only) or ingest your own telemetry via the API. Demo data is clearly labelled as simulated.">
          <Btn onClick={seed} disabled={busy}>{busy ? "Seeding…" : "Load simulated demo data"}</Btn>
          {seedErr && <div className="mt-2"><ErrorBox error={seedErr} /></div>}
        </Empty>
      )}
      {data && !data.empty && (
        <div className="space-y-4">
          <SimBanner origin={data.origin} />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Energy (facility)" value={fmt(data.totals.energy_kwh, 1)} unit="kWh" origin="estimated" />
            <Stat label="Carbon emissions" value={fmt(data.totals.co2e_kg, 1)} unit="kgCO₂e" origin="estimated" sub={`confidence ≈ ${data.origin.mean_confidence} (heuristic)`} />
            <Stat label="Cloud cost" value={`$${fmt(data.totals.cost_usd, 0)}`} origin="estimated" sub="on-demand catalogue prices" />
            <Stat label="Optimization opportunities" value={data.opportunities.count} sub={`≈ ${fmt(data.opportunities.potential_co2e_kg_month, 0)} kgCO₂e / $${fmt(data.opportunities.potential_cost_usd_month, 0)} per month (est.)`} />
            <Stat label="Avg CPU utilization" value={pct(data.avg_cpu)} origin={data.origin.telemetry[0]} />
            <Stat label="Avg memory utilization" value={pct(data.avg_mem)} origin={data.origin.telemetry[0]} />
            <Stat label="Resources monitored" value={data.health.resources} sub={`${fmt(data.health.samples, 0)} samples`} />
            <Stat label="System health" value={data.health.database === "ok" ? "OK" : "Degraded"} sub={`latest data ${day(data.health.latest_telemetry)}`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Energy & carbon trend (daily)">
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={data.energy_trend_daily.map((r) => ({ ...r, d: day(r.ts) }))}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="d" /><YAxis yAxisId="l" /><YAxis yAxisId="r" orientation="right" />
                  <Tooltip /><Area yAxisId="l" dataKey="energy_kwh" name="Energy kWh" stroke="#0ea5e9" fill="#bae6fd" />
                  <Area yAxisId="r" dataKey="co2e_kg" name="CO₂e kg" stroke="#16a34a" fill="#bbf7d0" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Carbon intensity by region (gCO₂e/kWh)" right={<span className="text-xs text-slate-400">illustrative sample data</span>}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.carbon_intensity_by_region}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="region" /><YAxis /><Tooltip />
                  <Bar dataKey="mean_g_per_kwh" name="Mean" fill="#16a34a" /><Bar dataKey="latest_g_per_kwh" name="Latest" fill="#0ea5e9" />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
          <Card title="Recent recommendations (advisory)">
            {data.recent_recommendations.length === 0 ? <p className="text-sm text-slate-500">None yet — open Resource Optimization and run the analysis.</p> :
              <ul className="space-y-2 text-sm">{data.recent_recommendations.map((r) => (
                <li key={r.id} className="flex items-start justify-between gap-3 border-b pb-2 last:border-0">
                  <span><b className="capitalize">{r.type}</b> — {r.rationale}</span><Pill tone={r.risk}>{r.risk} risk</Pill>
                </li>))}</ul>}
          </Card>
        </div>
      )}
    </>
  );
}
