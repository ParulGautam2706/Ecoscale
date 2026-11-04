import pytest


def test_all_data_endpoints_require_auth(client):
    for path in ("/api/v1/dashboard/summary", "/api/v1/resources", "/api/v1/optimization/recommendations", "/api/v1/settings"):
        assert client.get(path).status_code == 401
    assert client.post("/api/v1/optimization/run", json={}).status_code == 401


def test_admin_only_endpoints(client):
    client.post("/api/v1/auth/register", json={"email": "a@x.io", "password": "password123"})        # admin
    client.post("/api/v1/auth/register", json={"email": "b@x.io", "password": "password123"})        # analyst
    t = client.post("/api/v1/auth/login", data={"username": "b@x.io", "password": "password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert client.post("/api/v1/admin/seed", json={"days": 1}, headers=h).status_code == 403
    assert client.put("/api/v1/settings/weights", json={"carbon": 1}, headers=h).status_code == 403
    assert client.post("/api/v1/ml/train", json={"target": "cpu_forecast"}, headers=h).status_code == 403


def test_empty_state_before_seed(client):
    client.post("/api/v1/auth/register", json={"email": "a@x.io", "password": "password123"})
    t = client.post("/api/v1/auth/login", data={"username": "a@x.io", "password": "password123"}).json()["access_token"]
    r = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 200 and r.json()["empty"] is True


def test_dashboard_labels_simulated_and_estimated(api):
    d = api.get("/api/v1/dashboard/summary").json()
    assert d["origin"]["contains_simulated"] is True and d["origin"]["telemetry"] == ["simulated"]
    assert d["origin"]["energy"] == ["estimated"] and d["data_mode"] == "simulated"
    assert d["totals"]["energy_kwh"] > 0 and len(d["carbon_intensity_by_region"]) == 5
    assert api.get("/api/v1/dashboard/summary?region=eu-north").json()["window"]["region"] == "eu-north"


def test_ingest_validation_and_origin_rules(api):
    ok = {"resource_id": 1, "origin": "measured", "interval_s": 60,
          "samples": [{"ts": "2026-11-05T00:00:00Z", "cpu": 0.4, "mem": 0.5, "net_mbit_s": 10, "disk_mb_s": 2}]}
    assert api.post("/api/v1/telemetry/ingest", json=ok).status_code == 201
    bad = {**ok, "samples": [{"ts": "2026-11-05T00:01:00Z", "cpu": 1.7, "mem": 0.5}]}
    assert api.post("/api/v1/telemetry/ingest", json=bad).status_code == 422
    assert api.post("/api/v1/telemetry/ingest", json={**ok, "origin": "estimated"}).status_code == 422
    assert api.post("/api/v1/telemetry/ingest", json={**ok, "resource_id": 9999}).status_code == 400
    rows = api.get("/api/v1/telemetry?resource_id=1&limit=5").json()
    assert rows[-1]["origin"] == "measured"


def test_carbon_estimate_endpoint_and_units(api):
    body = {"instance_type": "gp.large", "region": "eu-north", "cpu": 0.5, "mem": 0.5, "interval_s": 3600}
    r = api.post("/api/v1/carbon/estimate", json=body).json()
    assert r["method"] == "estimated" and r["confidence"] < 1
    assert r["facility_kwh"] == pytest.approx(r["it_kwh"] * r["pue"])
    assert r["co2e_kg"] == pytest.approx(r["facility_kwh"] * r["ci_g_per_kwh"] / 1000)
    m = api.post("/api/v1/carbon/estimate", json={**body, "measured_power_w": 200}).json()
    assert m["method"] == "measured"
    assert api.post("/api/v1/carbon/estimate", json={**body, "region": "nowhere"}).status_code == 404


def test_carbon_analytics_endpoints(api):
    assert api.get("/api/v1/carbon/regions").json()["regions"]
    assert api.get("/api/v1/carbon/workloads").json()["workloads"][0]["co2e_kg"] > 0
    assert api.get("/api/v1/carbon/timeseries?freq=D").json()["series"]
    f = api.get("/api/v1/carbon/forecast?region=us-east").json()
    assert f["origin"] == "predicted" and len(f["forecast"]) == 48
    assert api.get("/api/v1/carbon/intensity?region=us-east").json()[0]["series"]


def test_full_ml_workflow_over_api(api):
    assert api.get("/api/v1/ml/forecast/1").status_code == 409                       # not trained yet
    r = api.post("/api/v1/ml/train", json={"target": "cpu_forecast", "models": ["linear_regression", "xgboost"], "horizon_steps": 6})
    assert r.status_code == 200, r.text
    assert api.get("/api/v1/ml/forecast/1").json()["origin"] == "predicted"
    pts = api.get("/api/v1/ml/forecast-series/1?steps=20").json()["points"]
    assert pts and {"actual", "predicted", "lower", "upper"} <= set(pts[0])
    assert api.get("/api/v1/ml/comparison/cpu_forecast").json()["baselines"]
    assert api.get("/api/v1/ml/models?target=cpu_forecast").json()
    assert api.post("/api/v1/ml/train", json={"target": "energy_wh", "models": ["hist_gradient_boosting"]}).status_code == 200
    e = api.post("/api/v1/ml/predict-energy", json={"instance_type": "gp.large", "region_code": "us-east", "cpu": 0.5, "mem": 0.5}).json()
    assert "NOT from metered hardware" in e["label_note"]
    assert api.get("/api/v1/ml/importance/cpu_forecast").json()["features"]
    assert api.post("/api/v1/ml/train", json={"target": "bogus"}).status_code == 422


def test_optimization_explain_simulate_report_workflow(api):
    run = api.post("/api/v1/optimization/run", json={}).json()
    assert run["created"] > 0 and "advisory" in run["status"]
    recs = api.get("/api/v1/optimization/recommendations").json()
    assert all(r["advisory_only"] for r in recs) and {r["status"] for r in recs} == {"pending"}
    rid = recs[0]["id"]
    assert api.patch(f"/api/v1/optimization/recommendations/{rid}", json={"status": "accepted"}).json()["status"] == "accepted"
    assert api.patch(f"/api/v1/optimization/recommendations/{rid}", json={"status": "applied"}).status_code == 422
    ex = api.get(f"/api/v1/explain/recommendation/{rid}").json()
    assert ex["explanation"]["risks"] and ex["model_feature_influence"] is not None
    mo = api.post("/api/v1/optimization/multiobjective", json={"carbon": 1, "cost": 0, "latency": 0, "sla": 0}).json()
    assert abs(sum(mo["weights"].values()) - 1) < 1e-9 and mo["optimized_totals"]["co2e_kg_day"] <= mo["baseline_totals"]["co2e_kg_day"]
    assert len(api.get("/api/v1/optimization/tradeoffs").json()["presets"]) == 4
    flex = next(r for r in api.get("/api/v1/resources").json() if r["is_flexible"])
    assert api.post("/api/v1/optimization/schedule", json={"resource_id": flex["id"]}).json()["message"]
    assert api.post("/api/v1/optimization/schedule", json={"resource_id": 3}).status_code == 400
    sim = api.post("/api/v1/simulate", json={"resource_id": 3, "scenarios": [{"type": "region", "region": "eu-north"}]})
    assert sim.status_code == 200 and len(sim.json()["results"]) == 2
    assert api.post("/api/v1/simulate", json={"resource_id": 3, "scenarios": [{"type": "region"}]}).status_code == 400
    assert api.get("/api/v1/simulate/history").json()
    assert api.get("/api/v1/carbon/before-after").json()["reduction_pct"]["co2e_kg_day"] >= 0
    assert api.get("/api/v1/cost/summary").json()["total_usd"] > 0
    an = api.post("/api/v1/anomalies/detect", json={}).json()
    assert an["events"] >= 1 and api.get("/api/v1/anomalies").json()[0]["investigate"]
    csv = api.post("/api/v1/reports/generate", json={"format": "csv", "section": "recommendations"})
    assert csv.status_code == 200 and "rationale" in csv.text
    full = api.post("/api/v1/reports/generate", json={"format": "csv"}).text
    assert "# METHODOLOGY" in full and "# MODELS" in full
    pdf = api.post("/api/v1/reports/generate", json={"format": "pdf"})
    assert pdf.content[:4] == b"%PDF" and len(pdf.content) > 3000
    assert api.post("/api/v1/reports/generate", json={"format": "csv", "section": "nope"}).status_code == 400


def test_settings_weights_are_normalised_and_validated(api):
    out = api.put("/api/v1/settings/weights", json={"carbon": 8, "cost": 1, "latency": 1, "sla": 0}).json()
    assert abs(sum(out.values()) - 1) < 1e-9 and out["carbon"] == pytest.approx(0.8)
    assert api.put("/api/v1/settings/weights", json={"carbon": -1}).status_code == 400
    assert api.put("/api/v1/settings/bogus", json={}).status_code == 400
    assert api.put("/api/v1/settings/thresholds", json={"not_a_key": 1}).status_code == 400
    api.put("/api/v1/settings/weights", json={"carbon": 0.4, "cost": 0.3, "latency": 0.2, "sla": 0.1})


def test_prometheus_metrics_are_origin_labelled(api):
    t = api.get("/metrics").text
    assert "gc_estimated_co2e_kg_total" in t and 'origin="simulated"' in t
