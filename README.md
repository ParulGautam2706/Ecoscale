# GreenCloud AI 2.0

Explainable, cost-efficient, **carbon-aware** cloud resource monitoring and optimization platform (FastAPI + React).
Recommendations are **advisory only**. Every value is labelled `measured`, `estimated`, `simulated` or `predicted`.

> Demo data is **simulated** and carbon intensity is **illustrative**. Numbers in the UI are estimates, not measurements.

## Quick start (Windows PowerShell)

Prerequisites: Python 3.11, Node.js 20+, Git.

```powershell
# 1) Backend
cd greencloud-ai\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
copy ..\.env.example .env             # then edit SECRET_KEY to a long random string
pytest -q                             # 50+ tests, ~1 min
uvicorn main:app --reload             # API docs: http://127.0.0.1:8000/docs

# 2) Frontend (new terminal)
cd greencloud-ai\frontend
npm install
npm test
npm run dev                           # http://localhost:5173
```

First run: open http://localhost:5173 → **Register** (first account becomes admin) → Dashboard → **Load simulated demo data**
→ AI Predictions → train models → Resource Optimization → **Run optimization analysis**.

### Database migrations
```powershell
cd backend
alembic upgrade head                  # creates all tables (SQLite by default; PostgreSQL via DATABASE_URL)
alembic revision --autogenerate -m "describe change"
```

### Reproduce the research results
```powershell
cd backend
python scripts\run_experiments.py --interval 600      # ~1 min, writes research\results.json / results.md
python scripts\build_research_doc.py                  # regenerates the research document from those results
```

### Docker (PostgreSQL + backend + nginx frontend)
```powershell
copy .env.example .env                # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build             # UI http://localhost:8080 , API http://localhost:8000/docs
```
*The Docker files were written but not executed in the authoring environment — expect to debug on first run.*

### Optional Prometheus
`GET /metrics` exposes `gc_*` gauges/counters labelled with `origin`. `prometheus.yml` is a ready scrape config.

## Architecture
```
React (Vite, Tailwind, Recharts) --JWT--> FastAPI --> services --> SQLAlchemy (SQLite / PostgreSQL)
   pages: Dashboard · Monitoring · Carbon · Predictions · Optimization · Cost · Explainable AI · Simulator · Anomalies · Reports · Settings
backend/app: api/ core/ database/ models/ schemas/ services/ ml/ optimization/ monitoring/ utils/
```
Energy pipeline: utilization → component power (W) → IT kWh (W·s/3.6e6) → ×PUE → ×gCO2e/kWh/1000 = kgCO2e.

| Area | Module |
|---|---|
| Energy/carbon engine | `services/energy.py`, `services/carbon.py`, `utils/units.py` |
| ML (LR, RF, GBR, HistGB, XGBoost, LightGBM) | `ml/features.py`, `ml/train.py`, `ml/pipeline.py`, `ml/explain.py` |
| Optimization (MILP, scheduler, idle/consolidation) | `optimization/*` |
| What-if, anomaly, reports | `services/simulation.py`, `anomaly.py`, `reporting.py` |
| Monitoring | `monitoring/collectors.py`, `monitoring/prometheus.py` |

## Honest limitations
- No metered power → energy/carbon are model estimates; ML energy models are **proxies** of the power model (R² ≈ 1 is expected, not a validation).
- Carbon-intensity, price, latency and hardware-power tables are **illustrative assumptions**; replace them (Settings, `core/defaults.py`, or a carbon-API adapter).
- Google Cluster traces are supported via the preprocessing pipeline but are not bundled.
- Region moves do not check availability, quotas or data residency. SLA risk is a heuristic.
- LightGBM/XGBoost are used when installable; otherwise they are skipped automatically.

## Testing
`pytest` covers unit conversions, energy formulas (hand-calculated cases), leakage-free splits, optimizer constraints/capacity, advisory-only behaviour, simulation trade-offs,
anomaly detection and the full authenticated API workflow. `npm test` covers frontend helpers; `npm run build` verifies the bundle compiles.
"# Ecoscale" 
