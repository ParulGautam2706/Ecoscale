import { useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useApi from "../hooks/useApi";
import { errMsg, get, post } from "../services/api";
import ResourceSelect from "../components/ResourceSelect";
import { Btn, Card, Empty, ErrorBox, Loading, OriginBadge, PageHeader, Table } from "../components/ui";
import { fmt, shortDate } from "../utils/format";

const modelCols = [{ key: "model", label: "Model", render: (r) => <b>{r.model}</b> }, { key: "mae", label: "MAE" }, { key: "rmse", label: "RMSE" }, { key: "r2", label: "R²" },
  { key: "cv_rmse_mean", label: "CV RMSE" }, { key: "train_seconds", label: "Train s" }, { key: "predict_ms_per_1000", label: "Pred ms/1k" }, { key: "model_size_kb", label: "Size KB" }, { key: "rss_delta_mb", label: "RSS Δ MB" }];

function Comparison({ target, title, hint }) {
  const { data, error, loading } = useApi(() => get(`/ml/comparison/${target}`), [target]);
  if (loading) return <Loading />;
  if (error) return <Empty title="Not trained yet" hint={error} />;
  return (
    <Card title={title} right={<OriginBadge origin={target === "energy_wh" ? "predicted" : "predicted"} />}>
      <p className="mb-2 text-xs text-slate-500">{hint} Best by time-series CV: <b>{data.best_model}</b>. Split: chronological at {data.split_ts}; train {data.train_rows} / test {data.test_rows} rows.</p>
      {data.proxy_label_note && <div className="mb-2 rounded bg-amber-50 p-2 text-xs text-amber-900">⚠ {data.proxy_label_note}</div>}
      {Object.keys(data.baselines || {}).length > 0 && (
        <p className="mb-2 text-xs text-slate-600">Naive baselines (same test rows): {Object.entries(data.baselines).map(([k, v]) => `${k} RMSE ${fmt(v.rmse, 4)}`).join(" · ")}</p>)}
      <Table cols={modelCols} rows={data.all_models} />
    </Card>
  );
}

export default function Predictions() {
  const [rid, setRid] = useState("1");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);
  const series = useApi(() => get(`/ml/forecast-series/${rid}`, { steps: 96 }), [rid, tick]);
  const next = useApi(() => get(`/ml/forecast/${rid}`), [rid, tick]);
  const [form, setForm] = useState({ instance_type: "gp.large", region_code: "us-east", cpu: 0.5, mem: 0.5 });
  const [pred, setPred] = useState(null);
  const train = async (target) => {
    setBusy(target); setErr(null); setMsg(null);
    try { const r = await post("/ml/train", { target }); setMsg(`Trained ${target}: best = ${r.best_model} (selected by time-series CV RMSE).`); setTick((t) => t + 1); }
    catch (e) { setErr(errMsg(e)); } finally { setBusy(""); }
  };
  const predict = async () => { setErr(null); try { setPred(await post("/ml/predict-energy", { ...form, cpu: +form.cpu, mem: +form.mem })); } catch (e) { setErr(errMsg(e)); } };
  return (
    <>
      <PageHeader title="AI Predictions" subtitle="Six models compared on a chronological hold-out. Nothing here is a measured value.">
        <ResourceSelect value={rid} onChange={setRid} />
        <Btn disabled={!!busy} onClick={() => train("cpu_forecast")}>{busy === "cpu_forecast" ? "Training…" : "Train utilization forecaster"}</Btn>
        <Btn kind="secondary" disabled={!!busy} onClick={() => train("energy_wh")}>{busy === "energy_wh" ? "Training…" : "Train energy proxy model"}</Btn>
      </PageHeader>
      {msg && <div className="mb-3 rounded-lg bg-emerald-50 p-2 text-sm text-emerald-900">{msg}</div>}
      {err && <div className="mb-3"><ErrorBox error={err} /></div>}
      <div className="space-y-4">
        {series.error ? <Empty title="No trained forecaster yet" hint="Training takes ~1 minute on the demo data (admin only). Models trained: LR, RF, GBR, HistGB, XGBoost, LightGBM." /> : series.data && (
          <Card title="CPU utilization forecast (+60 min ahead): predicted vs actual with 90% interval" right={<OriginBadge origin="predicted" />}>
            {next.data && <p className="mb-2 text-sm">Next-hour prediction: <b>{fmt(next.data.predicted_cpu_utilization * 100, 1)}%</b> (90% interval {fmt(next.data.interval_90[0] * 100, 1)}–{fmt(next.data.interval_90[1] * 100, 1)}%) · model {next.data.model}</p>}
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={series.data.points.map((p) => ({ ...p, t: shortDate(p.target_ts), band: [p.lower * 100, p.upper * 100], actual: p.actual * 100, predicted: p.predicted * 100 }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="t" minTickGap={50} /><YAxis unit="%" /><Tooltip /><Legend />
                <Area dataKey="band" name="90% interval" stroke="none" fill="#ddd6fe" /><Line dataKey="actual" name="Actual" stroke="#16a34a" dot={false} /><Line dataKey="predicted" name="Predicted" stroke="#7c3aed" dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="mt-1 text-xs text-slate-500">{series.data.note} Interval = empirical 5–95% quantiles of held-out residuals.</p>
          </Card>)}
        <Comparison target="cpu_forecast" title="Utilization forecasting — model comparison" hint="Genuine forecasting target (CPU at +horizon)." />
        <Comparison target="energy_wh" title="Energy prediction — model comparison (proxy)" hint="Target = Wh per interval from the power model." />
        <Card title="Predict energy & carbon for a hypothetical interval (proxy model)">
          <div className="flex flex-wrap items-end gap-2 text-sm">
            {[["instance_type", "Instance"], ["region_code", "Region"], ["cpu", "CPU 0–1"], ["mem", "Mem 0–1"]].map(([k, l]) => (
              <label key={k} className="text-xs text-slate-500">{l}<input className="mt-1 block w-28 rounded border px-2 py-1 text-sm" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>))}
            <Btn onClick={predict}>Predict</Btn>
          </div>
          {pred && <p className="mt-2 text-sm">Predicted facility energy: <b>{fmt(pred.predicted_facility_wh_per_interval, 3)} Wh</b> per interval <OriginBadge origin="predicted" /><br /><span className="text-xs text-slate-500">{pred.label_note}</span></p>}
        </Card>
      </div>
    </>
  );
}
