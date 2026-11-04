import { useState } from "react";
import useApi from "../hooks/useApi";
import { errMsg, get, post } from "../services/api";
import { Btn, Card, Empty, ErrorBox, Loading, PageHeader, Pill, Table } from "../components/ui";
import { fmt, shortDate } from "../utils/format";

export default function Anomalies() {
  const list = useApi(() => get("/anomalies"), []);
  const [z, setZ] = useState(3.5);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState(null);
  const run = async () => { setBusy(true); setErr(null); try { setInfo(await post("/anomalies/detect", { z_min: Number(z) })); await list.reload(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); } };
  return (
    <>
      <PageHeader title="Anomaly Detection" subtitle="Isolation Forest + seasonal robust-z confirmation + event merging to limit false alarms">
        <label className="text-sm text-slate-600">Confirmation z ≥ <input type="number" step="0.5" min="2" value={z} onChange={(e) => setZ(e.target.value)} className="ml-1 w-16 rounded border px-2 py-1" /></label>
        <Btn onClick={run} disabled={busy}>{busy ? "Scanning…" : "Run detection"}</Btn>
      </PageHeader>
      {err && <ErrorBox error={err} />}
      {info && <div className="mb-3 rounded-lg bg-emerald-50 p-2 text-sm text-emerald-900">{info.events} anomaly event(s) found · {info.method}</div>}
      {list.loading ? <Loading /> : list.data?.length === 0 ? <Empty title="No anomalies" hint="Run detection. Higher z thresholds mean fewer, stronger alerts." /> : (
        <Card title="Detected events">
          <Table cols={[{ key: "ts", label: "Time", render: (r) => shortDate(r.ts) }, { key: "resource", label: "Resource" }, { key: "metric", label: "Affected metric" },
            { key: "severity", label: "Severity", render: (r) => <Pill tone={r.severity}>{r.severity}</Pill> }, { key: "score", label: "IF score", render: (r) => fmt(r.score, 3) },
            { key: "investigate", label: "Investigate", render: (r) => <ul className="list-disc pl-4 text-xs">{r.investigate.map((s) => <li key={s}>{s}</li>)}</ul> }]} rows={list.data} />
        </Card>)}
    </>
  );
}
