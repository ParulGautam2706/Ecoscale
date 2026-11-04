# Experimental results (auto-generated)

Data: **simulated (synthetic profiles; illustrative carbon intensity)**. Config: {'days': 7, 'interval': 600, 'seed': 42, 'fast': False}. Samples: 13104, resources: 13.
All values are computed by `backend/scripts/run_experiments.py`.

## 1. Original (paper, corrected) vs improved energy estimation
No metered ground truth exists, so neither is 'correct'; this shows how much the richer model changes the estimate.

Total paper-baseline energy: 352.99 kWh; improved estimator (with RAM/GPU/storage/network/PUE): 444.12 kWh (+25.82%).

| resource | paper_baseline_kwh | improved_kwh | paper_baseline_co2e_kg | improved_co2e_kg |
|---|---|---|---|---|
| api-service | 37.42 | 66.41 | 10.94 | 19.39 |
| cache-1 | 21.56 | 16.78 | 5.193 | 4.038 |
| cache-2 | 21.58 | 16.79 | 5.196 | 4.04 |
| dev-sandbox-1 | 18.27 | 17.51 | 12.42 | 11.9 |
| dev-sandbox-2 | 18.28 | 15.01 | 4.391 | 3.606 |
| legacy-reporting | 24.6 | 47.32 | 9.349 | 17.98 |
| metrics-collector | 33.89 | 13.46 | 1.357 | 0.539 |
| ml-training | 30.74 | 60.79 | 11.8 | 23.42 |
| nightly-etl | 27.38 | 51.93 | 10.31 | 19.57 |
| report-batch | 25.38 | 34.33 | 17.11 | 23.19 |
| staging-db | 22.61 | 25.82 | 6.568 | 7.494 |
| web-frontend-1 | 35.89 | 39.22 | 13.71 | 14.96 |
| web-frontend-2 | 35.39 | 38.75 | 13.52 | 14.78 |

## 2. ML: CPU utilization forecast (+60 min) - genuine forecasting target
Chronological split at 2026-10-28 17:30:00 (train 8710, test 2210). Best by CV RMSE: **hist_gradient_boosting**.

Baselines on the same test rows: persistence: RMSE 0.1519, MAE 0.0525, R2 0.352; seasonal_naive: RMSE 0.0390, MAE 0.0172, R2 0.957
Best model RMSE vs persistence: -80.02%, vs seasonal-naive: -22.2% (negative = better).

| model | mae | rmse | r2 | cv_rmse_mean | train_seconds | predict_ms_per_1000 | model_size_kb |
|---|---|---|---|---|---|---|---|
| linear_regression | 0.05574 | 0.1198 | 0.5969 | 0.1286 | 0.009 | 0.357 | 1.8 |
| random_forest | 0.01396 | 0.0306 | 0.9737 | 0.04484 | 0.578 | 16.35 | 2793 |
| gradient_boosting | 0.02798 | 0.05842 | 0.9041 | 0.06086 | 6.667 | 2.734 | 280.9 |
| hist_gradient_boosting | 0.01447 | 0.03036 | 0.9741 | 0.03728 | 0.655 | 4.356 | 732.8 |
| xgboost | 0.01588 | 0.03287 | 0.9696 | 0.04156 | 0.276 | 1.359 | 506.4 |
| lightgbm | 0.01462 | 0.03103 | 0.973 | 0.03973 | 0.299 | 3.346 | 588.3 |

## 2. ML: Energy per interval - PROXY target (labels derived from the power model)
Chronological split at 2026-10-28 14:20:00 (train 10465, test 2613). Best by CV RMSE: **xgboost**.

> Energy labels come from the configured power model, NOT from metered hardware. The model is a fast proxy estimator of that model; metrics measure agreement with it, not real-world accuracy.

| model | mae | rmse | r2 | cv_rmse_mean | train_seconds | predict_ms_per_1000 | model_size_kb |
|---|---|---|---|---|---|---|---|
| linear_regression | 1.58 | 2.429 | 0.985 | 41.23 | 0.009 | 0.325 | 1.6 |
| random_forest | 0.02084 | 0.06338 | 1 | 0.368 | 0.421 | 17.25 | 6662 |
| gradient_boosting | 0.1118 | 0.1884 | 0.9999 | 0.3812 | 5.151 | 2.315 | 300.1 |
| hist_gradient_boosting | 0.04415 | 0.1106 | 1 | 0.2634 | 0.386 | 2.267 | 360.5 |
| xgboost | 0.04531 | 0.09873 | 1 | 0.2305 | 0.241 | 1.543 | 478.6 |
| lightgbm | 0.03765 | 0.09369 | 1 | 0.3251 | 0.328 | 2.197 | 573.6 |

## 3. Optimization (advisory, estimated)
Recommendations: {'consolidate': 1, 'region': 6, 'idle': 2}.

Baseline per day: {'energy_kwh_day': 50.664, 'co2e_kg_day': 17.58, 'cost_usd_day': 55.35}; if all non-rejected applied: {'energy_kwh_day': 36.402, 'co2e_kg_day': 5.681, 'cost_usd_day': 34.46}; reduction %: {'energy_kwh_day': 28.15, 'co2e_kg_day': 67.69, 'cost_usd_day': 37.74}.

| resource | type | risk | priority | co2e_pct | cost_pct | co2e_kg_month | cost_usd_month | confidence |
|---|---|---|---|---|---|---|---|---|
| dev-sandbox-1 | idle | medium | high | 100 | 100 | 51 | 75.6 | 0.67 |
| dev-sandbox-2 | idle | medium | low | 100 | 100 | 15.45 | 75.6 | 0.66 |
| cache-2 | consolidate | medium | medium | 57.95 | 75 | 20.03 | 113.4 | 0.7 |
| api-service | region | low | high | 86.84 | 8.78 | 71.63 | 27.8 | 0.7 |
| legacy-reporting | region | medium | high | 95.32 | 74.65 | 73.35 | 215 | 0.7 |
| staging-db | region | medium | medium | 93.09 | 76.64 | 29.85 | 121.4 | 0.7 |
| nightly-etl | region | high | low | 90.92 | -2.78 | 19.73 | -1 | 0.82 |
| report-batch | region | high | low | 95.67 | -0.53 | 23.97 | -0.1 | 0.81 |
| ml-training | region | medium | medium | 91.6 | -0.46 | 51.95 | -1 | 0.81 |

### Trade-offs by weight preset (fleet, per day)

| preset | co2e_% | energy_% | cost_% | latency_ms_abs | sla_risk_abs | changed |
|---|---|---|---|---|---|---|
| carbon_first | -91.29 | -22.91 | -30.98 | 92 | 0.3907 | 12 |
| cost_first | -83.72 | -22 | -30.89 | 64 | 0.2149 | 12 |
| performance_first | -33.35 | -14.06 | -24.6 | 5 | 0.0011 | 10 |
| balanced | -47.13 | -18.5 | -30.98 | 5 | 0.0394 | 10 |

## 4. Carbon-intensity forecast backtest (hour-of-day profile, 24h hold-out)

| region | mae_g_per_kwh | naive_last_value_mae |
|---|---|---|
| ap-south | 21.36 | 89.31 |
| eu-north | 1.11 | 2.37 |
| eu-west | 8.64 | 36.39 |
| us-east | 9.25 | 50.36 |
| us-west | 5.7 | 50.77 |

## 5. Anomaly detection vs injected anomalies
{'injected_events': 75, 'detected': 74, 'missed': 1, 'false_alarms': 2, 'recall': 0.987, 'precision': 0.974, 'note': 'Injected CPU/network spikes in synthetic data; real-world precision/recall will differ.'}

Total runtime: 58.9 s.