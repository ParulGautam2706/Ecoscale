import numpy as np
import pandas as pd
import pytest

from app.services.preprocessing import validate_and_clean


def _df(n=100):
    return pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=n, freq="5min"), "cpu": np.linspace(0.1, 0.5, n), "mem": 0.4})


def test_missing_required_column():
    with pytest.raises(ValueError):
        validate_and_clean(_df().drop(columns=["mem"]))


def test_imputation_and_outlier_cap():
    d = _df()
    d["gpu"], d["net_mbit_s"], d["disk_mb_s"] = 0.1, 5.0, 1.0      # 1 missing of 5 fields = 20% < 30% rule
    d.loc[3, "cpu"] = np.nan
    d.loc[5, "cpu"] = 50.0
    out, rep = validate_and_clean(d)
    assert out["cpu"].isna().sum() == 0 and rep["imputed_cells"] == 1
    assert out["cpu"].max() <= 1.0 and rep["capped_cells"] >= 1


def test_drops_rows_with_too_many_missing_fields():
    d = _df()
    d["gpu"], d["net_mbit_s"] = 0.1, 5.0
    d.loc[0, ["cpu", "mem", "gpu"]] = np.nan          # 3/5 numeric missing
    out, rep = validate_and_clean(d)
    assert rep["dropped_missing"] == 1 and len(out) == 99
