"""Builds research/GreenCloud_AI_2.0_Research_Document.md. Numeric results are read from research/results.json."""
import json, os

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = json.load(open(os.path.join(root, "research", "results.json")))
results_md = open(os.path.join(root, "research", "results.md")).read().split("\n", 1)[1]
f, e = R["ml"]["cpu_forecast"], R["ml"]["energy_wh"]
best_f = next(m for m in f["models"] if m["model"] == f["best_model"])
ec, ba, an = R["estimation_comparison"], R["before_after"], R["anomaly"]
tr = {t["preset"]: t for t in R["tradeoffs"]}

doc = f"""# GreenCloud AI 2.0: An Explainable, Cost-Efficient and Carbon-Aware Cloud Resource Monitoring and Optimization Platform

> **Status: draft generated from reproducible experiments.** All results below were produced by `backend/scripts/run_experiments.py`
> on **simulated** workloads and **illustrative** carbon-intensity data. They demonstrate that the system works and how its components
> behave; they are **not** evidence of real-world savings. Verify every reference before submission.

## Abstract
Cloud data centres consume a large and growing share of electricity, yet operators rarely see carbon, cost and performance together at workload level.
We present GreenCloud AI 2.0, an end-to-end platform that (i) estimates energy and emissions from CPU, memory, GPU, storage and network utilization with PUE and
regional grid intensity, explicitly labelling every value as measured, estimated, simulated or predicted; (ii) compares six regression models (linear, random forest,
gradient boosting, HistGradientBoosting, XGBoost, LightGBM) on chronological hold-out data; (iii) generates advisory right-sizing, consolidation, idle-reclamation,
carbon-aware shifting and region recommendations through a multi-objective MILP with a configurable objective J = w1·Carbon + w2·Cost + w3·Latency + w4·SLA risk; and
(iv) explains each recommendation with SHAP-based feature influence, risks and assumptions. On a 7-day simulated fleet of {R['seed']['resources']} workloads
({R['seed']['samples']} samples), the best utilization forecaster ({f['best_model']}) reached RMSE {best_f['rmse']:.4f} versus {f['baselines']['persistence']['rmse']:.4f} (persistence)
and {f['baselines']['seasonal_naive']['rmse']:.4f} (seasonal-naive). Applying all non-rejected recommendations would lower **estimated** fleet carbon by
{ba['reduction_pct']['co2e_kg_day']}% and cost by {ba['reduction_pct']['cost_usd_day']}% under the stated assumptions; the multi-objective presets show explicit trade-offs with latency and SLA risk.

## 1. Problem statement
Operators lack integrated, per-workload tooling that estimates emissions, predicts demand and recommends *safe* changes while exposing the trade-offs among carbon, cost and
service quality. Provider dashboards are coarse; research prototypes address pieces in isolation.

## 2. Literature review (brief)
Energy-proportional computing motivates utilization-based power models (Barroso & Hölzle, 2007). Green Algorithms (Lannelongue et al., 2021) standardises computation footprints.
Carbon-aware computing shifts load in time and space (Radovanović et al., 2023). Tree-ensemble learners are strong tabular baselines (Chen & Guestrin, 2016; Ke et al., 2017).
SHAP (Lundberg & Lee, 2017) provides additive feature attributions; Isolation Forest (Liu et al., 2008) detects anomalies without labels. Google's public cluster traces
are a common source of workload data.

## 3. Limitations of the reference system (Bhonsle et al.)
Analysis of the reference paper identified the following, which GreenCloud AI 2.0 addresses:

| # | Observation in the reference paper | Treatment in GreenCloud AI 2.0 |
|---|---|---|
| 1 | Printed energy formula multiplies by 3,600,000 (should divide to convert W·s to kWh) and is not shown in full for idle power | Unit conversions centralised in `utils/units.py` with tests; corrected paper baseline retained for comparison |
| 2 | The carbon equation is mis-typeset: it shows energy plus a memory term; multiplication by grid intensity is only in prose | Explicit pipeline: IT power → IT energy → ×PUE → ×intensity |
| 3 | ML target (emissions) is computed from the same variables used as model inputs, so high accuracy is expected by construction | Energy targets flagged as **proxy labels**; real forecasting target (CPU at +horizon) added with naive baselines |
| 4 | Random 80/20 split and random 5-fold CV on time-ordered data | Chronological split, time-series CV, targets whose horizon crosses the split are excluded |
| 5 | No numeric results (RMSE, R², savings) are reported | All numbers are produced by a reproducible script |
| 6 | Savings described as consistent with literature; cited 70% figure refers to a reference [6] that is an edge-computing survey | No external savings claims; only computed estimates |
| 7 | No cost, latency or SLA in the optimizer; rule-based only | Multi-objective MILP with SLA/latency constraints, capacity coupling and cost-increase guard |
| 8 | No explainability; GPU acceleration claimed for scikit-learn GBR | SHAP + per-recommendation risk/assumption block; CPU-only training |

## 4. Proposed methodology
### 4.1 Energy and carbon estimation
For an interval of length t seconds:

- Platform power: `P_cpu = P_idle + (P_peak − P_idle)·u_cpu`
- RAM: `P_ram = M·β·(f_idle + (1 − f_idle)·u_mem)` with β = 0.375 W/GB (from the reference paper), f_idle = 0.5
- GPU: `P_gpu = n·(P_gpu,idle + (P_gpu,peak − P_gpu,idle)·u_gpu)`
- Storage and network: linear in activity up to a reference throughput
- `E_IT = (ΣP)·t / 3.6×10^6` kWh; `E_fac = E_IT·PUE`; `CO2e = E_fac·I / 1000` kg, with I in gCO2e/kWh.

Records are labelled `estimated` unless a metered power value is supplied (`measured`). A heuristic confidence score (≤ 0.85 when uncalibrated) is reported; it is not a statistical interval.

### 4.2 Machine learning
Targets: (a) CPU utilization at +60 min (genuine forecasting) and (b) facility energy per interval (proxy of the power model). Features: utilization, instance specification, hour, weekday, region, CPU×memory,
lags (1, 2, 3, 6, one day) and rolling mean/std built from past values only. Split: chronological; selection by lowest mean `TimeSeriesSplit` CV RMSE on the training period; test metrics are reported separately.
Reported: MAE, RMSE, R², training time, prediction latency, serialized model size, resident-memory change. Forecast intervals are empirical 5–95% residual quantiles.

### 4.3 Optimization
Each workload is summarised from telemetry (mean/p95 cores, memory, job hours). Candidates are (instance in family, region, start offset). Objectives are normalised against the workload's baseline
(carbon and cost ratios, latency relative to its SLA reference, absolute SLA risk). The fleet problem selects one candidate per workload minimising ΣJ subject to hard constraints
(p95 CPU/memory ceilings, latency ≤ SLA, deadlines, GPU availability) and regional vCPU capacity, solved exactly with `scipy.optimize.milp`.
Rules from the reference paper (CPU < 25%, memory < 30%, idle < 2%, ≥ 20% carbon improvement to justify shifting) are kept as configurable defaults. Upsizing is only considered if the current setup violates a constraint, and
recommendations may not raise cost beyond a configurable tolerance or add high SLA risk.

### 4.4 Explainability, simulation, anomaly detection
Every recommendation stores: why, influencing features, expected savings, performance impact, confidence, risks, assumptions and before/after metrics. SHAP (TreeExplainer) or permutation importance explains the models.
The what-if simulator reuses the same evaluator for fair comparison. Anomalies: Isolation Forest per workload, confirmed by a seasonal (hour-of-day) robust z-score, with event merging.

## 5. System architecture
React (Vite, Tailwind, Recharts) ↔ FastAPI (JWT, rate limiting, Prometheus) ↔ services (energy, carbon, ML, optimization, simulation, anomaly, reporting) ↔ SQLAlchemy (SQLite / PostgreSQL).
Collectors: simulator, local `psutil` (measured utilization); Kubernetes/cloud collectors can implement the same contract.

## 6. Experimental setup
Fixed seed ({R['config']['seed']}); {R['config']['days']} simulated days at {R['config']['interval']} s intervals; 13 workloads (web, over-provisioned, idle, batch, GPU) across 5 regions; synthetic hour-of-day carbon intensity with
illustrative regional levels; CPU-only training. Anomaly evaluation injects CPU/network spikes into every workload. Google cluster traces can be ingested through the preprocessing pipeline but were **not** used for these results.

## 7. Results and discussion
{results_md}

### Interpretation
- **Estimation:** the richer model changes the fleet energy estimate by {ec['difference_pct']:+}% relative to the corrected CPU-only baseline. Without metered ground truth we cannot say which is closer to reality; the difference mainly shows that RAM, GPU, PUE and instance-specific idle power matter.
- **Forecasting:** all tree ensembles beat persistence by a wide margin. The best model improved on a seasonal-naive baseline by {abs(f['rmse_improvement_vs_seasonal_naive_pct'])}% RMSE, but the synthetic workloads are strongly periodic, which flatters seasonal baselines and hides real-world volatility.
- **Energy model:** R² ≈ 1 for tree models is expected because labels are produced by a deterministic power model; this validates the proxy, not physical accuracy.
- **Optimization:** the large carbon reduction ({ba['reduction_pct']['co2e_kg_day']}%) is dominated by moving workloads to a region whose *illustrative* intensity is about an order of magnitude lower. It is a property of the sample data, not a general expectation.
  The preset table shows the cost of pursuing carbon: carbon-first changes mean latency by {tr['carbon_first']['delta_abs']['mean_latency_ms']} ms and SLA risk by {tr['carbon_first']['delta_abs']['mean_sla_risk']}, while performance-first changes them by {tr['performance_first']['delta_abs']['mean_latency_ms']} ms and {tr['performance_first']['delta_abs']['mean_sla_risk']}.
- **Anomalies:** {an['detected']} of {an['injected_events']} injected events detected (recall {an['recall']}), {an['false_alarms']} false alarms (precision {an['precision']}); injected spikes are easier than real incidents.

## 8. Limitations
1. No metered power: energy and carbon are model estimates; calibration against hardware (e.g., RAPL or smart PDUs) is required for validation.
2. Experiments use simulated telemetry and illustrative carbon intensity and prices; results do not transfer to real fleets without re-running on real data.
3. Latency and SLA risk are heuristic functions of p95 utilization and a static inter-region latency table.
4. Region moves assume instance availability, quotas and data-residency compliance; data-transfer cost is a flat assumption.
5. Embodied carbon is not modelled. Carbon forecasts use an hour-of-day profile only.
6. Recommendations are advisory; no closed-loop execution exists by design.

## 9. Future scope
Real telemetry connectors (Kubernetes metrics, cloud monitoring); calibration with measured power; live carbon-intensity adapters; embodied-carbon accounting; sequence models only if they beat the tuned tree baselines;
a guarded, human-approved execution path for accepted recommendations.

## References (verify before submission)
1. L. A. Barroso and U. Hölzle, "The Case for Energy-Proportional Computing," *IEEE Computer*, 40(12), 33–37, 2007.
2. L. Lannelongue, J. Grealey, M. Inouye, "Green Algorithms: Quantifying the Carbon Footprint of Computation," *Advanced Science*, 8(12), 2100707, 2021.
3. A. Radovanović et al., "Carbon-Aware Computing for Datacenters," arXiv:2106.11750 (published in *IEEE Trans. Power Systems*, 2023).
4. D. Patterson et al., "Carbon Emissions and Large Neural Network Training," arXiv:2104.10350, 2021.
5. S. M. Lundberg and S.-I. Lee, "A Unified Approach to Interpreting Model Predictions," *NeurIPS*, 2017.
6. T. Chen and C. Guestrin, "XGBoost: A Scalable Tree Boosting System," *KDD*, 2016.
7. G. Ke et al., "LightGBM: A Highly Efficient Gradient Boosting Decision Tree," *NeurIPS*, 2017.
8. F. T. Liu, K. M. Ting, Z.-H. Zhou, "Isolation Forest," *IEEE ICDM*, 2008.
9. F. Pedregosa et al., "Scikit-learn: Machine Learning in Python," *JMLR*, 12, 2825–2830, 2011.
10. M. Bhonsle et al., "AI-Based Carbon Footprint Monitoring and Optimization System for Cloud Service Providers" (the supplied reference paper).
11. Google, "Cluster workload traces," https://github.com/google/cluster-data.
"""
open(os.path.join(root, "research", "GreenCloud_AI_2.0_Research_Document.md"), "w").write(doc)
print("written", len(doc), "chars")
