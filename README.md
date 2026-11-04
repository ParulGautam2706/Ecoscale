# GreenCloud AI 2.0 (EcoScale)

An explainable, carbon-aware decision-support platform for cloud cost and resource optimization.

GreenCloud AI estimates the energy use and carbon emissions of cloud resources, forecasts utilization with machine learning, and recommends changes that lower **cost** and **carbon** together, without breaking performance limits. Every recommendation can be explained and tested in a what-if simulator first.

> **Advisory only.** The platform never changes real cloud infrastructure. Public workload traces contain no measured energy, so energy values are estimates and learned models are proxy estimators.

---

## Features

| Feature | Description |
|---|---|
| Energy and carbon engine | Converts CPU, memory, GPU, storage and network utilization into IT power, energy, facility energy (via PUE) and CO2e using regional grid carbon intensity |
| ML forecasting | Trains and compares several models, then uses the best one for utilization and energy forecasts |
| Utilization tiering | KMeans groups resources into Idle, Underused, Optimal and Overused tiers |
| Carbon-aware scheduling | Suggests running flexible workloads at a cleaner time or in a cleaner region, within deadline, capacity and latency limits |
| Multi-objective optimizer | Weighs carbon, cost, latency and SLA risk and shows the trade-offs |
| Explainability | SHAP feature importance and a written explanation for each recommendation |
| What-if simulator | Compares the current setup with alternatives before any change |
| Anomaly detection | Isolation Forest flags unusual CPU, memory, network or energy behavior |
| Dashboard and reports | Web dashboard with charts, plus generated reports |

## How it works

```
Data input -> Energy model -> Carbon engine -> ML forecasting
                                                     |
Dashboard + reports <- What-if simulator <- Explainability <- Optimization
```

1. **Data input:** seed data, simulated or ingested telemetry, or metrics collected from the local machine.
2. **Energy model:** utilization is converted to power (W) and energy (kWh); PUE is applied once to total IT energy.
3. **Carbon engine:** energy multiplied by the regional carbon intensity gives CO2e.
4. **Forecasting:** several models are trained and compared; the best is chosen from measured validation results.
5. **Optimization:** inefficiencies are found and ranked actions are produced.
6. **Explainability and simulation:** the user sees why a change is suggested and previews its effect.
7. **Dashboard and reports:** results, savings and alerts are shown in the web app.

## Tech stack

- **Frontend:** React, Vite, Tailwind CSS (port `5173`)
- **Backend:** Python 3.11, FastAPI, uvicorn (port `8000`, API under `/api/v1`)
- **Database:** SQLite with SQLAlchemy; Alembic for migrations
- **ML:** scikit-learn, with optional XGBoost and LightGBM
- **Auth:** JWT login and registration
- **Packaging:** Docker Compose (optional)

## Project structure

```
greencloud-ai/
  backend/
    main.py              FastAPI entry point
    app/                 routers, services, ML pipeline, database
    scripts/             train_models.py, run_experiments.py, build_research_doc.py
    tests/               pytest tests
    requirements.txt
  frontend/
    src/                 React app
    vite.config.js       dev server and /api proxy
  .env.example
  docker-compose.yml
```

## Requirements

- Python 3.11
- Node.js 20 or newer
- Git

## Quick start (Windows)

Use two terminal windows and keep both open.

### 1. Backend

```bat
cd greencloud-ai\backend
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
copy ..\.env.example .env
```

Open `.env` and set `SECRET_KEY` to a long random string. You can generate one with:

```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

Start the server:

```bat
python -m uvicorn main:app --port 8000
```

Check it works by opening `http://127.0.0.1:8000/api/v1/health` and `http://127.0.0.1:8000/docs`.
The root address `http://127.0.0.1:8000/` shows `{"detail":"Not Found"}`. This is normal, because the API has no page there.

### 2. Frontend

```bat
cd greencloud-ai\frontend
npm install
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`). The dev server forwards `/api` requests to `http://127.0.0.1:8000`, so the backend must be running.

### 3. Load data

Either call **POST `/api/v1/admin/seed`** from `http://127.0.0.1:8000/docs`, or from the backend folder run:

```bat
python scripts\train_models.py --seed
```

### Database tables with Alembic (instead of automatic setup)

```bat
cd greencloud-ai\backend
alembic upgrade head
```

## Docker (optional)

```bat
cd greencloud-ai
copy .env.example .env
docker compose up --build
```

## Tests

```bat
cd greencloud-ai\backend
python -m pytest -q

cd ..\frontend
npm test
```

Running `python -m pytest` instead of `pytest` avoids the "not recognized" error when the virtual environment is not on PATH.

## Research experiments

To re-run the experiments and rebuild the research document:

```bat
cd greencloud-ai\backend
python scripts\run_experiments.py --interval 600
python scripts\build_research_doc.py
```

## API overview

All endpoints start with `/api/v1`. Full interactive documentation is at `/docs`.

| Area | Example endpoints |
|---|---|
| Auth | `/auth/register`, `/auth/login`, `/auth/me` |
| Reference data | `/resources`, `/regions`, `/instance-types`, `/admin/seed`, `/settings` |
| Dashboard | `/dashboard/summary` |
| Carbon | `/carbon/timeseries`, `/carbon/regions`, `/carbon/workloads`, `/carbon/before-after`, `/carbon/intensity`, `/carbon/forecast`, `/carbon/estimate` |
| Telemetry | `/telemetry`, `/telemetry/ingest`, `/telemetry/simulate`, `/telemetry/collect-local` |
| ML | `/ml/train`, `/ml/models`, `/ml/comparison/{target}`, `/ml/forecast/{resource_id}`, `/ml/predict-energy`, `/ml/importance/{target}` |
| Optimization | `/optimization/run`, `/optimization/recommendations`, `/optimization/multiobjective`, `/optimization/tradeoffs`, `/optimization/schedule`, `/optimization/inefficiencies` |
| Cost | `/cost/summary` |
| Explain | `/explain/recommendation/{rec_id}`, `/explain/model/{target}` |
| Simulate | `/simulate`, `/simulate/history` |
| Anomalies | `/anomalies/detect`, `/anomalies` |
| Reports | `/reports/generate` |
| Health | `/health` |

## Troubleshooting

| Problem | Fix |
|---|---|
| `pytest`, `uvicorn` or `python` not found | Activate the virtual environment in that window: `.venv\Scripts\activate.bat` (Command Prompt) or `.\.venv\Scripts\Activate.ps1` (PowerShell) |
| PowerShell blocks the activate script | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again |
| `pip install` fails on xgboost or lightgbm | Delete that line from `requirements.txt` and run the install again |
| Browser Console shows 404 on `/api/v1/...` | An old backend is holding port 8000. Run `netstat -ano \| findstr :8000`, then `taskkill /F /PID <number>`, and start the backend again from this project folder |
| Vite starts on 5174 instead of 5173 | An old frontend is still running. Run `taskkill /F /IM node.exe` and start `npm run dev` again |
| Blank page or login fails | Make sure the backend window is still running, then hard refresh with Ctrl+Shift+R |
| Empty charts or lists | Seed the data (see "Load data" above) |
| "no such table" error | Run `alembic upgrade head` in the backend folder |

## Limitations

- Energy values are estimates from a configurable power model, not measurements.
- Models trained on those estimates describe agreement with the power model, not real consumption.
- Carbon-intensity data covers a limited period, with a static regional table as fallback.
- Recommendations are advisory and should be reviewed by a person, especially region migrations.

## Future work

- Live telemetry from cloud-provider monitoring and Kubernetes
- Calibration against measured power data
- Live carbon-intensity APIs with intensity forecasting
- Pareto-front optimization (for example NSGA-II)
- Opt-in execution of approved recommendations, with rollback

## License and credits

Add your license, authors and supervisor details here.