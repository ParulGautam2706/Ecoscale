import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useApi from "../hooks/useApi";
import { get } from "../services/api";
import { Card, Empty, ErrorBox, Loading, PageHeader, Select, SimBanner, Stat, Table } from "../components/ui";
import { fmt, shortDate } from "../utils/format";

export default function CarbonAnalytics() {
  const [freq, setFreq] = useState("h");
  const [region, setRegion] = useState("us-east");
  const ts = useApi(() => get("/carbon/timeseries", { freq, days: 7 }), [freq]);
  const regions = useApi(() => get("/carbon/regions"), []);
  const wl = useApi(() => get("/carbon/workloads"), []);
  const ba = useApi(() => get("/carbon/before-after"), []);
  const fc = useApi(() => get("/carbon/forecast", { region }), [region]);
  const inten = useApi(() => get("/carbon/intensity", { region, hours: 96 }), [region]);
  if (ts.loading) return <Loading />;
  if (ts.error) return <ErrorBox error={ts.error} onRetry={ts.reload} />;
  if (!ts.data?.series?.length) return <Empty title="No carbon data" hint="Load demo data from the Dashboard first." />;
  const combined = [...(inten.data?.[0]?.series || []).map((p) => ({ t: shortDate(p.ts), actual: p.g_per_kwh })),
    ...(fc.data?.forecast || []).map((p) => ({ t: shortDate(p.ts), forecast: p.g_per_kwh }))];
  return (
    <>
      <PageHeader title="Carbon Analytics" subtitle="All emissions are estimates: facility energy × grid carbon intensity">
        <Select label="Resolution" value={freq} onChange={setFreq} options={[{ value: "h", label: "Hourly" }, { value: "D", label: "Daily" }]} />
      </PageHeader>
      <SimBanner origin={ts.data.origin} />
      <div className="space-y-4">
        <Card title="Emissions and energy over time (estimated)">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={ts.data.series.map((r) => ({ ...r, t: shortDate(r.ts) }))}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="t" minTickGap={50} /><YAxis yAxisId="l" /><YAxis yAxisId="r" orientation="right" /><Tooltip /><Legend />
              <Line yAxisId="l" dataKey="co2e_kg" name="CO₂e kg" stroke="#16a34a" dot={false} /><Line yAxisId="r" dataKey="energy_kwh" name="Energy kWh" stroke="#0ea5e9" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Regional comparison">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={regions.data?.regions || []}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="region_code" /><YAxis /><Tooltip /><Legend />
                <Bar dataKey="co2e_kg" name="CO₂e kg" fill="#16a34a" /><Bar dataKey="energy_kwh" name="Energy kWh" fill="#0ea5e9" /></BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="Emissions before vs after optimization (estimated, per day)">
            {ba.data && !ba.data.empty ? (<>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="CO₂e before" value={fmt(ba.data.baseline_per_day.co2e_kg_day)} unit="kg/d" />
                <Stat label="CO₂e after" value={fmt(ba.data.after_per_day.co2e_kg_day)} unit="kg/d" />
                <Stat label="Reduction" value={`${fmt(ba.data.reduction_pct.co2e_kg_day, 1)}%`} />
              </div>
              <p className="mt-2 text-xs text-slate-500">{ba.data.note} Counted recommendations: {ba.data.recommendations_counted}.</p>
            </>) : <p className="text-sm text-slate-500">Run the optimizer to see a comparison.</p>}
          </Card>
        </div>
        <Card title="Workload-level carbon estimates">
          <Table cols={[{ key: "resource", label: "Workload" }, { key: "region_code", label: "Region" }, { key: "instance_type", label: "Instance" }, { key: "co2e_kg", label: "kgCO₂e" },
            { key: "energy_kwh", label: "kWh" }, { key: "cost_usd", label: "$" }, { key: "avg_cpu", label: "Avg CPU" }, { key: "confidence", label: "Confidence" }]} rows={wl.data?.workloads || []} />
        </Card>
        <Card title="Grid carbon intensity: history + forecast" right={<Select value={region} onChange={setRegion} options={["us-east", "us-west", "eu-west", "eu-north", "ap-south"].map((r) => ({ value: r, label: r }))} />}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={combined}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="t" minTickGap={60} /><YAxis /><Tooltip /><Legend />
              <Line dataKey="actual" name="History (sample data)" stroke="#16a34a" dot={false} /><Line dataKey="forecast" name="Forecast (hour-of-day profile)" stroke="#a855f7" strokeDasharray="5 4" dot={false} /></LineChart>
          </ResponsiveContainer>
          {fc.data?.backtest && <p className="mt-2 text-xs text-slate-500">Backtest (24 h hold-out): MAE {fc.data.backtest.mae_g_per_kwh} g/kWh vs last-value baseline {fc.data.backtest.naive_last_value_mae}. Source: illustrative synthetic sample data — plug in a real feed via the adapter.</p>}
        </Card>
      </div>
    </>
  );
}
