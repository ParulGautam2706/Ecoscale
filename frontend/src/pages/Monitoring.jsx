import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useApi from "../hooks/useApi";
import { errMsg, get, post } from "../services/api";
import ResourceSelect, { useResources } from "../components/ResourceSelect";
import { Btn, Card, Empty, ErrorBox, Loading, OriginBadge, PageHeader, Pill, Table } from "../components/ui";
import { fmt, shortDate } from "../utils/format";

export default function Monitoring() {
  const [rid, setRid] = useState("1");
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const res = useResources();
  const ts = useApi(() => get("/telemetry", { resource_id: rid, limit: 300 }), [rid]);
  const ineff = useApi(() => get("/optimization/inefficiencies"), []);
  const act = async (fn) => { setErr(null); setMsg(null); try { setMsg(await fn()); await ts.reload(); } catch (e) { setErr(errMsg(e)); } };
  const cur = (res.data || []).find((r) => String(r.id) === String(rid));
  return (
    <>
      <PageHeader title="Resource Monitoring" subtitle="Utilization history. Data mode: simulated unless you ingest or collect real samples.">
        <ResourceSelect value={rid} onChange={setRid} />
        <Btn kind="secondary" onClick={() => act(async () => { const r = await post("/telemetry/simulate", { resource_id: Number(rid), hours: 6, profile: "web" }); return `Added ${r.samples} SIMULATED samples`; })}>+ 6h simulated</Btn>
        <Btn kind="secondary" onClick={() => act(async () => { const r = await post("/telemetry/collect-local"); return `Collected 1 MEASURED local sample (CPU ${fmt(r.sample.cpu * 100, 0)}%). ${r.note}`; })}>Collect local machine sample</Btn>
      </PageHeader>
      {msg && <div className="mb-3 rounded-lg bg-emerald-50 p-2 text-sm text-emerald-900">{msg}</div>}
      {err && <div className="mb-3"><ErrorBox error={err} /></div>}
      {ts.loading && <Loading />}
      {ts.data?.length === 0 && <Empty title="No samples for this resource" hint="Load demo data from the Dashboard, or POST to /telemetry/ingest." />}
      {ts.data?.length > 0 && (
        <div className="space-y-4">
          <Card title={`${cur?.name ?? "Resource"} — CPU & memory utilization`} right={<span className="flex gap-1">{[...new Set(ts.data.map((s) => s.origin))].map((o) => <OriginBadge key={o} origin={o} />)}</span>}>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={ts.data.map((s) => ({ ...s, t: shortDate(s.ts), cpu: +(s.cpu * 100).toFixed(1), mem: +(s.mem * 100).toFixed(1) }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="t" minTickGap={40} /><YAxis unit="%" domain={[0, 100]} /><Tooltip /><Legend />
                <Line dataKey="cpu" name="CPU %" stroke="#16a34a" dot={false} /><Line dataKey="mem" name="Memory %" stroke="#0ea5e9" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Network & storage activity">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={ts.data.map((s) => ({ t: shortDate(s.ts), net: s.net_mbit_s, disk: s.disk_mb_s }))}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="t" minTickGap={40} /><YAxis /><Tooltip /><Legend />
                  <Line dataKey="net" name="Network Mbit/s" stroke="#a855f7" dot={false} /><Line dataKey="disk" name="Disk MB/s" stroke="#f59e0b" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Fleet utilization & idle detection (paper thresholds, configurable)">
              {ineff.data && <Table cols={[{ key: "resource", label: "Resource" }, { key: "mean_cpu", label: "CPU" }, { key: "mean_mem", label: "Mem" },
                { key: "underuse_share", label: "Under-use share" }, { key: "idle", label: "Idle", render: (r) => (r.idle ? <Pill tone="high">idle</Pill> : "—") }]} rows={ineff.data} />}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
