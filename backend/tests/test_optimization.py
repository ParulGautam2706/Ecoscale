import pytest

from app.models.entities import RecStatus, Recommendation, Resource
from app.optimization import recommender
from app.optimization.evaluate import evaluate, load_profiles, make_ctx, score, candidates, latency_reference
from app.optimization.multiobjective import optimize_fleet, tradeoff_table
from app.optimization.rightsizing import detect_idle
from app.optimization.scheduler import schedule_options
from app.services.data import telemetry_df


def _by_name(profiles, name):
    return next(p for p in profiles.values() if p.name == name)


def test_idle_detection_finds_only_idle_boxes(seeded_db):
    ctx = make_ctx(seeded_db)
    df = telemetry_df(seeded_db)
    pr = load_profiles(seeded_db, ctx, df)
    names = {pr[i].name for i in detect_idle(df, pr, ctx)}
    assert names == {"dev-sandbox-1", "dev-sandbox-2"}


def test_thresholds_are_configurable_not_hardcoded(seeded_db):
    from app.services import settings_service
    ctx = make_ctx(seeded_db)
    df = telemetry_df(seeded_db)
    pr = load_profiles(seeded_db, ctx, df)
    settings_service.update(seeded_db, "thresholds", {"idle_cpu": 0.0001})
    try:
        assert detect_idle(df, pr, make_ctx(seeded_db)) == set()
    finally:
        settings_service.update(seeded_db, "thresholds", {"idle_cpu": 0.02})


def test_recommendations_are_advisory_and_explained(seeded_db):
    before = [(r.id, r.region_code, r.instance_type) for r in seeded_db.query(Resource).order_by(Resource.id)]
    out = recommender.generate(seeded_db)
    after = [(r.id, r.region_code, r.instance_type) for r in seeded_db.query(Resource).order_by(Resource.id)]
    assert before == after and out["created"] > 0 and "advisory" in out["status"]
    for rec in seeded_db.query(Recommendation).all():
        e = rec.explanation
        for key in ("why", "influencing_features", "expected_savings", "performance_impact", "confidence", "risks", "assumptions", "origin"):
            assert key in e, key
        assert e["origin"] == "estimated" and 0 <= e["confidence"] <= 1
        assert rec.status == RecStatus.pending


def test_no_recommendation_increases_cost_beyond_limit_or_adds_high_sla_risk(seeded_db):
    ctx = make_ctx(seeded_db)
    for rec in seeded_db.query(Recommendation).all():
        assert -rec.savings["cost_usd_pct"] <= ctx.limits["max_cost_increase_pct"] + 1e-6
        if rec.rec_type in ("region", "shift", "rightsize") and rec.explanation["after"]:
            a, b = rec.explanation["after"], rec.explanation["before"]
            assert not (a["sla_risk"] >= 0.30 and a["sla_risk"] > b["sla_risk"])
            assert not a["violations"]


def test_regenerating_replaces_pending_but_keeps_decisions(seeded_db):
    r = seeded_db.query(Recommendation).first()
    r.status = RecStatus.accepted
    seeded_db.commit()
    recommender.generate(seeded_db)
    assert seeded_db.query(Recommendation).filter(Recommendation.status == RecStatus.accepted).count() == 1


def test_multiobjective_respects_constraints_and_capacity(seeded_db):
    ctx = make_ctx(seeded_db)
    pr = load_profiles(seeded_db, ctx)
    res = optimize_fleet(pr, ctx)
    used = {}
    for a in res["assignments"]:
        c = a["chosen"]
        assert c["feasible"] or not a["changed"]
        if a["changed"]:
            assert not c["violations"]
        used[c["region"]] = used.get(c["region"], 0) + c["vcpu"]
    assert all(v <= ctx.limits["region_capacity_vcpu"] for v in used.values())
    assert res["solver"].startswith("scipy.optimize.milp")


def test_objective_normalisation_and_weights(seeded_db):
    ctx = make_ctx(seeded_db)
    p = _by_name(load_profiles(seeded_db, ctx), "api-service")
    base = evaluate(p, ctx.specs[p.instance], p.region, 0, ctx, enforce=False)
    cl = candidates(p, ctx)
    score(cl, {"carbon": 1, "cost": 0, "latency": 0, "sla": 0}, base, latency_reference(p, ctx))
    b = next(e for e in cl if e.region == p.region and e.instance == p.instance)
    assert b.J == pytest.approx(1.0)                      # baseline carbon ratio is exactly 1
    assert min(cl, key=lambda e: e.J).co2e_kg <= b.co2e_kg


def test_tradeoffs_show_no_free_lunch(seeded_db):
    ctx = make_ctx(seeded_db)
    t = {x["preset"]: x for x in tradeoff_table(load_profiles(seeded_db, ctx), ctx)}
    assert t["carbon_first"]["delta_pct"]["co2e_kg_day"] <= t["performance_first"]["delta_pct"]["co2e_kg_day"] + 1e-9
    assert t["carbon_first"]["delta_abs"]["mean_sla_risk"] >= t["performance_first"]["delta_abs"]["mean_sla_risk"] - 1e-9


def test_scheduler_only_for_flexible_and_respects_deadline(seeded_db):
    ctx = make_ctx(seeded_db)
    pr = load_profiles(seeded_db, ctx)
    with pytest.raises(ValueError):
        schedule_options(_by_name(pr, "api-service"), ctx)
    p = _by_name(pr, "nightly-etl")
    out = schedule_options(p, ctx)
    assert out["best"]["offset_h"] + p.job_hours <= p.deadline_hours + 1e-6
    assert out["baseline"]["co2e_kg"] >= out["best"]["co2e_kg"] - 1e-9 or not out["recommended_change"]


def test_non_flexible_never_shifted(seeded_db):
    ctx = make_ctx(seeded_db)
    p = _by_name(load_profiles(seeded_db, ctx), "web-frontend-1")
    assert {c.offset_h for c in candidates(p, ctx)} == {0.0}
