import pytest

from app.models.entities import Anomaly
from app.optimization.evaluate import load_profiles, make_ctx
from app.services import anomaly, simulation
from app.services.data import telemetry_df


def _rid(db, name):
    from app.models.entities import Resource
    return db.query(Resource).filter(Resource.name == name).one().id


def test_simulation_same_assumptions_and_tradeoffs(seeded_db):
    rid = _rid(seeded_db, "api-service")
    r = simulation.run(seeded_db, rid, [{"type": "region", "region": "eu-north"}, {"type": "reduce_cpu", "percent": 25},
                                         {"type": "instance", "instance_type": "gp.large"}])
    cur, reg, cpu, inst = r["results"]
    assert cur["delta_vs_current"]["co2e_kg_day_pct"] == 0
    assert reg["delta_vs_current"]["co2e_kg_day_pct"] < -50 and reg["delta_vs_current"]["latency_ms_abs"] > 0   # carbon down, latency up
    assert cpu["metrics"]["cpu_util_p95"] > cur["metrics"]["cpu_util_p95"]
    assert inst["metrics"]["constraint_violations"] and inst["metrics"]["sla_risk"] > cur["metrics"]["sla_risk"]
    assert r["origin"] == "estimated"


def test_simulation_validation(seeded_db):
    rid = _rid(seeded_db, "api-service")
    with pytest.raises(ValueError):
        simulation.run(seeded_db, rid, [{"type": "teleport"}])
    with pytest.raises(ValueError):
        simulation.run(seeded_db, rid, [{"type": "reduce_cpu", "percent": 150}])
    with pytest.raises(ValueError):
        simulation.run(seeded_db, 99999, [])


def test_consolidation_scenario(seeded_db):
    a, b = _rid(seeded_db, "cache-1"), _rid(seeded_db, "cache-2")
    r = simulation.run(seeded_db, a, [{"type": "consolidate", "resource_ids": [a, b], "target_instance": "gp.small"}])
    assert r["results"][1]["delta_vs_current"]["energy_kwh_day_pct"] < 0


def test_anomaly_detects_injected_events_with_few_false_positives(seeded_db):
    out = anomaly.detect(seeded_db)
    rows = seeded_db.query(Anomaly).all()
    web1 = _rid(seeded_db, "web-frontend-1")
    assert sum(r.resource_id == web1 for r in rows) >= 5       # >=5 of the 6 injected events found
    assert sum(r.resource_id != web1 for r in rows) <= 3      # 12 clean workloads stay (mostly) quiet
    assert all(r.severity in ("low", "medium", "high") for r in rows)
    assert anomaly.investigation_steps("cpu")


def test_anomaly_needs_enough_data():
    import pandas as pd
    df = pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=10, freq="5min"), "cpu": 0.1, "mem": 0.1,
                       "net_mbit_s": 1.0, "disk_mb_s": 1.0, "facility_kwh": 0.001})
    assert anomaly.detect_frame(df).empty
