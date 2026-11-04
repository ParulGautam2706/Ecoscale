import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useApi from "../hooks/useApi";
import { errMsg, get } from "../services/api";
import { Card, Empty, ErrorBox, Loading, OriginBadge, PageHeader, Pill, Select } from "../components/ui";
import { fmt } from "../utils/format";

export default function ExplainableAI() {
  const [params] = useSearchParams();
  const recs = useApi(() => get("/optimization/recommendations"), []);
  const [id, setId] = useState(params.get("rec") || "");
  useEffect(() => { if (!id && recs.data?.length) setId(String(recs.data[0].id)); }, [recs.data, id]);
  const ex = useApi(() => (id ? get(`/explain/recommendation/${id}`) : Promise.resolve(null)), [id]);
  if (recs.loading) return <Loading />;
  if (!recs.data?.length) return <Empty title="Nothing to explain yet" hint="Run the optimizer first (Resource Optimization)." />;
  const e = ex.data?.explanation;
  const sv = e?.expected_savings;
  const mfi = ex.data?.model_feature_influence;
  return (
    <>
      <PageHeader title="Explainable AI" subtitle="Why each recommendation was made, what drives it, and what could go wrong">
        <Select label="Recommendation" value={id} onChange={setId} options={recs.data.map((r) => ({ value: r.id, label: `#${r.id} ${r.type} — ${r.resource}` }))} />
      </PageHeader>
      {ex.loading && <Loading />}
      {ex.error && <ErrorBox error={ex.error} />}
      {e && (
        <div className="space-y-4">
          <Card title="Why this recommendation" right={<span className="flex gap-2"><Pill tone={ex.data.risk}>{ex.data.risk} risk</Pill><OriginBadge origin={e.origin} /></span>}>
            <p className="text-sm">{e.why}</p>
          </Card>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Expected savings (estimated, per month)">
              <ul className="space-y-1 text-sm">
                <li>Energy: <b>{fmt(sv.energy_kwh_day * 30, 1)} kWh</b> ({fmt(sv.energy_kwh_pct, 1)}%)</li>
                <li>Carbon: <b>{fmt(sv.co2e_kg_month, 1)} kgCO₂e</b> ({fmt(sv.co2e_kg_pct, 1)}%)</li>
                <li>Cost: <b>${fmt(sv.cost_usd_month, 0)}</b> ({fmt(sv.cost_usd_pct, 1)}%)</li>
              </ul>
              <p className="mt-2 text-xs text-slate-500">{sv.basis}</p>
            </Card>
            <Card title="Performance impact & confidence">
              <p className="text-sm">{e.performance_impact}</p>
              <p className="mt-2 text-sm">Confidence: <b>{e.confidence}</b></p>
              <p className="text-xs text-slate-500">{e.confidence_basis}</p>
            </Card>
            <Card title="Features that influenced the decision">
              <ul className="space-y-1 text-sm">{e.influencing_features.map((f) => <li key={f.name} className="flex justify-between"><span className="text-slate-600">{f.name}</span><b>{f.value}</b></li>)}</ul>
            </Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Risks"><ul className="list-disc space-y-1 pl-5 text-sm">{e.risks.map((r, i) => <li key={i}>{r}</li>)}</ul></Card>
            <Card title="Assumptions"><ul className="list-disc space-y-1 pl-5 text-sm">{e.assumptions.map((r, i) => <li key={i}>{r}</li>)}</ul></Card>
          </div>
          <Card title="Model feature influence (SHAP) — energy proxy model">
            {mfi ? (<>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart layout="vertical" data={mfi.features.slice(0, 10)}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" /><YAxis type="category" dataKey="feature" width={110} /><Tooltip /><Bar dataKey="importance" fill="#16a34a" /></BarChart>
              </ResponsiveContainer>
              <p className="text-xs text-slate-500">{mfi.method} · model {mfi.model}. {mfi.caveat}</p></>)
              : <p className="text-sm text-slate-500">{ex.data.model_note || "Train the energy model (AI Predictions) to see SHAP feature influence."}</p>}
          </Card>
        </div>
      )}
    </>
  );
}
