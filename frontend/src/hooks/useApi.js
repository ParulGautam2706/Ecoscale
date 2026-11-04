import { useCallback, useEffect, useState } from "react";
import { errMsg } from "../services/api";

/** Loads data from an async fn; returns {data, loading, error, reload}. */
export default function useApi(fn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setData(await fn()); } catch (e) { setError(errMsg(e)); setData(null); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { data, loading, error, reload: run };
}
