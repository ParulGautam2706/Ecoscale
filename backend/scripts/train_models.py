import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401
from app.database.session import Base, SessionLocal, engine
from app.ml.pipeline import train_target
from app.models.entities import TelemetrySample
from app.services.seed import seed

ap = argparse.ArgumentParser()
ap.add_argument("--seed", action="store_true", help="load simulated demo data first")
a = ap.parse_args()

Base.metadata.create_all(bind=engine)
db = SessionLocal()
if a.seed or db.query(TelemetrySample).count() == 0:
    print("Seeding SIMULATED data:", seed(db, days=7, interval_s=600))

for target in ("cpu_forecast", "energy_wh"):
    r = train_target(db, target)
    print(f"\n{target}: best model = {r['best_model']}  test metrics = {r['best_metrics_test']}")
    for m in r["summary"]["all_models"]:
        print(f"  {m['model']:<24} RMSE={m['rmse']:.4f}  R2={m['r2']:.3f}  train={m['train_seconds']}s")