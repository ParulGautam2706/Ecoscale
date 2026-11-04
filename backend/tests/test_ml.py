import pytest

from app.ml import pipeline
from app.ml.features import FORECAST_FEATURES, add_features, build_forecast_dataset
from app.ml.train import chronological_split
from app.services.data import instance_specs, region_table, telemetry_df

FAST = ["linear_regression", "hist_gradient_boosting", "lightgbm", "xgboost"]


def test_forecast_split_has_no_temporal_leakage(seeded_db):
    df = telemetry_df(seeded_db)
    feat = add_features(df, instance_specs(seeded_db), sorted(region_table(seeded_db)), 600)
    d = build_forecast_dataset(feat, 6, 600)
    train, test, split = chronological_split(d, target_time_col="target_ts")
    assert train["target_ts"].max() <= split < test["ts"].min()


def test_lag_features_use_only_past(seeded_db):
    df = telemetry_df(seeded_db, resource_ids=[1])
    f = add_features(df, instance_specs(seeded_db), sorted(region_table(seeded_db)), 600).dropna(subset=["cpu_lag1"])
    prev = df.sort_values("ts")["cpu"].shift(1).dropna().to_numpy()
    assert (f["cpu_lag1"].to_numpy() == prev).all()


def test_train_forecast_selects_by_cv_and_reports_baselines(seeded_db):
    r = pipeline.train_target(seeded_db, "cpu_forecast", horizon_steps=6, only=FAST)
    s = r["summary"]
    names = {m["model"] for m in s["all_models"]}
    assert {"linear_regression", "hist_gradient_boosting"} <= names
    best = min(s["all_models"], key=lambda m: m["cv_rmse_mean"])["model"]
    assert r["best_model"] == best
    assert set(s["baselines"]) == {"persistence", "seasonal_naive"}
    assert s["split"] == "chronological" and "TimeSeriesSplit" in s["cv"]
    for m in s["all_models"]:
        assert {"mae", "rmse", "r2", "train_seconds", "predict_ms_per_1000", "model_size_kb"} <= set(m)
    out = pipeline.forecast_resource(seeded_db, 1)
    lo, hi = out["interval_90"]
    assert 0 <= lo <= out["predicted_cpu_utilization"] <= hi <= 1 and out["origin"] == "predicted"


def test_energy_model_is_flagged_as_proxy(seeded_db):
    r = pipeline.train_target(seeded_db, "energy_wh", only=["linear_regression", "hist_gradient_boosting"])
    assert "NOT from metered hardware" in r["summary"]["proxy_label_note"]
    runs = pipeline.list_runs(seeded_db, "energy_wh")
    assert all(x["proxy_label"] for x in runs)
    p = pipeline.predict_energy_wh(seeded_db, {"instance_type": "gp.large", "region_code": "us-east", "cpu": 0.5, "mem": 0.5})
    assert p["predicted_facility_wh_per_interval"] > 0 and p["origin"] == "predicted"


def test_unknown_target_rejected(seeded_db):
    with pytest.raises(ValueError):
        pipeline.train_target(seeded_db, "carbon_truth")


def test_shap_or_fallback_importance(seeded_db):
    from app.ml.explain import global_importance
    pipeline.train_target(seeded_db, "cpu_forecast", horizon_steps=6, only=["xgboost", "linear_regression"])
    g = global_importance(seeded_db, "cpu_forecast", n_rows=100)
    assert g["features"] and set(f["feature"] for f in g["features"]) <= set(FORECAST_FEATURES)
