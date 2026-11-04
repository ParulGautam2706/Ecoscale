import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import useApi from "../hooks/useApi";
import { get } from "../services/api";
import { Card, Empty, ErrorBox, Loading, PageHeader, SimBanner, Stat } from "../components/ui";
import { day, fmt } from "../utils/format";

export default function CostAnalysis() {
  const { data, loading, error, reload } = useApi(() => get("/cost/summary"), []);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (data.empty) return <Empty title="No cost data" hint="Load demo data from the Dashboard." />;
  return (
    <>
      <PageHeader title="Cost Analysis" subtitle={data.pricing_note} />
      <SimBanner origin={data.origin} />
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <Stat label="Total cost (window)" value={`$${fmt(data.total_usd, 0)}`} origin="estimated" />
          <Stat label="Potential savings / month" value={`$${fmt(data.potential_savings_usd_month, 0)}`} sub="pending recommendations" origin="estimated" />
          <Stat label="Top spender" value={data.by_resource[0]?.resource} sub={`$${fmt(data.by_resource[0]?.cost_usd, 0)}`} />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Daily cost"><ResponsiveContainer width="100%" height={240}><LineChart data={data.daily.map((d) => ({ ...d, d: day(d.ts) }))}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="d" /><YAxis /><Tooltip /><Line dataKey="cost_usd" name="$" stroke="#16a34a" /></LineChart></ResponsiveContainer></Card>
          <Card title="Cost by region"><ResponsiveContainer width="100%" height={240}><BarChart data={data.by_region}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="region" /><YAxis /><Tooltip /><Bar dataKey="cost_usd" name="$" fill="#0ea5e9" /></BarChart></ResponsiveContainer></Card>
        </div>
        <Card title="Cost vs carbon by workload"><ResponsiveContainer width="100%" height={300}><BarChart data={data.by_resource}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="resource" interval={0} angle={-30} textAnchor="end" height={80} /><YAxis /><Tooltip />
          <Bar dataKey="cost_usd" name="$" fill="#16a34a" /><Bar dataKey="co2e_kg" name="kgCO₂e" fill="#f59e0b" /></BarChart></ResponsiveContainer></Card>
      </div>
    </>
  );
}
