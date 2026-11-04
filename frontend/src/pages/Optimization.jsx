import { useState } from "react";
import { Link } from "react-router-dom";
import useApi from "../hooks/useApi";
import { errMsg, get, patch, post } from "../services/api";
import ResourceSelect from "../components/ResourceSelect";
import { Btn, Card, Empty, ErrorBox, Loading, PageHeader, Pill, Table } from "../components/ui";
import { fmt } from "../utils/format";

export default function Optimization() {
  const recs = useApi(() => get("/optimization/recommendations"), []);
  const trade = useApi(() => get("/optimization/tradeoffs"), []);
  const ineff = useApi(() => get("/optimization/inefficiencies"), []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [rid, setRid] = useState("8");
  const [sched, setSched] = useState(null);
  const run = async () => { setBusy(true); setErr(null); try { await post("/optimization/run", {}); await recs.reload(); await trade.reload(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); } };
  const setStatus = async (id, status) => { try { await patch(`/optimization/recommendations/${id}`, { status }); await recs.reload(); } catch (e) { setErr(errMsg(e)); } };
  const doSched = async () => { setErr(null); try { setSched(await post("/optimization/schedule", { resource_id: Number(rid) })); } catch (e) { setErr(errMsg(e)); setSched(null); } };
  return (
    <>
      <PageHeader title="Resource Optimization" subtitle="Advisory only — accepting a recommendation records your decision; it never changes infrastructure.">
        <Btn onClick={run} disabled={busy}>{busy ? "Analysing…" : "Run optimization analysis"}</Btn>
      </PageHeader>
      {err && <div className="mb-3"><ErrorBox error={err} /></div>}
      <div className="space-y-4">
        <Card title="Recommendations">
          {recs.loading ? <Loading /> : recs.data?.length === 0 ? <Empty title="No recommendations yet" hint="Click “Run optimization analysis”. Requires telemetry (see Dashboard)." /> : (
            <Table cols={[
              { key: "priority", label: "Priority", render: (r) => <Pill tone={r.priority}>{r.priority}</Pill> },
              { key: "type", label: "Type", render: (r) => <b className="capitalize">{r.type}</b> },
              { key: "resource", label: "Resource" },
              { key: "rationale", label: "Why", render: (r) => <span className="text-xs">{r.rationale}</span> },
              { key: "savings", label: "Est. saving / month", render: (r) => <span className="text-xs">{fmt(r.savings.co2e_kg_month, 1)} kgCO₂e ({fmt(r.savings.co2e_kg_pct, 0)}%)<br />${fmt(r.savings.cost_usd_month, 0)} ({fmt(r.savings.cost_usd_pct, 0)}%)</span> },
              { key: "performance_impact", label: "Performance impact", render: (r) => <span className="text-xs">{r.performance_impact}</span> },
              { key: "risk", label: "Risk", render: (r) => <Pill tone={r.risk}>{r.risk}</Pill> },
              { key: "confidence", label: "Conf." },
              { key: "status", label: "Decision", render: (r) => (
                <div className="space-y-1"><Pill tone={r.status}>{r.status}</Pill>
                  <div className="flex gap-1"><Btn kind="secondary" onClick={() => setStatus(r.id, "accepted")}>Accept</Btn><Btn kind="secondary" onClick={() => setStatus(r.id, "rejected")}>Reject</Btn></div>
                  <Link className="block text-xs text-green-700 underline" to={`/explain?rec=${r.id}`}>Explain</Link></div>) },
            ]} rows={recs.data || []} />)}
        </Card>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Multi-objective trade-offs (J = w₁·Carbon + w₂·Cost + w₃·Latency + w₄·SLA risk)">
            {trade.data ? (<>
              <Table cols={[{ key: "preset", label: "Preset" }, { key: "c", label: "CO₂e", render: (t) => `${fmt(t.delta_pct.co2e_kg_day, 1)}%` }, { key: "k", label: "Cost", render: (t) => `${fmt(t.delta_pct.cost_usd_day, 1)}%` },
                { key: "l", label: "Latency Δ", render: (t) => `${fmt(t.delta_abs.mean_latency_ms, 0)} ms` }, { key: "s", label: "SLA risk Δ", render: (t) => fmt(t.delta_abs.mean_sla_risk, 3) }, { key: "n", label: "Changed", render: (t) => t.changed_workloads }]}
                rows={trade.data.presets.map((p) => ({ ...p, id: p.preset }))} />
              <p className="mt-2 text-xs text-slate-500">{trade.data.note} Latency/SLA averages cover latency-sensitive workloads only.</p></>) : trade.error ? <p className="text-sm text-slate-500">{trade.error}</p> : <Loading />}
          </Card>
          <Card title="Detected inefficiencies">
            <Table cols={[{ key: "resource", label: "Resource" }, { key: "instance", label: "Instance" }, { key: "mean_cpu", label: "CPU" }, { key: "underuse_share", label: "Under-use share" },
              { key: "idle", label: "Idle", render: (r) => (r.idle ? <Pill tone="high">idle</Pill> : "—") }]} rows={(ineff.data || []).slice(0, 8)} />
          </Card>
        </div>
        <Card title="Carbon-aware scheduler (flexible workloads)" right={<div className="flex items-center gap-2"><ResourceSelect value={rid} onChange={setRid} flexibleOnly /><Btn onClick={doSched}>Find schedule</Btn></div>}>
          {sched ? (<>
            <p className="text-sm">{sched.message}</p>
            <Table cols={[{ key: "region", label: "Region" }, { key: "offset_h", label: "Start +h" }, { key: "ci_g_per_kwh", label: "gCO₂e/kWh" }, { key: "co2e_kg", label: "kgCO₂e" }, { key: "cost_usd", label: "$/day" }, { key: "latency_ms", label: "Latency ms" }]}
              rows={sched.alternatives_by_carbon.slice(0, 6)} />
            <p className="mt-2 text-xs text-slate-500">{sched.note}</p></>) : <p className="text-sm text-slate-500">Choose a flexible workload to compare start times and regions under its deadline, latency and cost limits.</p>}
        </Card>
      </div>
    </>
  );
}
