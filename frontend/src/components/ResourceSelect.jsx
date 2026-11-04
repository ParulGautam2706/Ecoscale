import useApi from "../hooks/useApi";
import { get } from "../services/api";
import { Select } from "./ui";

export default function ResourceSelect({ value, onChange, flexibleOnly = false, label = "Resource" }) {
  const { data } = useApi(() => get("/resources"), []);
  const list = (data || []).filter((r) => !flexibleOnly || r.is_flexible);
  return <Select label={label} value={value} onChange={onChange} options={list.map((r) => ({ value: r.id, label: `${r.name} (${r.region}, ${r.instance_type})` }))} />;
}
export const useResources = () => useApi(() => get("/resources"), []);
