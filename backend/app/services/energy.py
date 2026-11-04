"""Modular energy + carbon engine.

Pipeline:  utilization -> component power (W) -> IT energy (kWh) -> facility energy (x PUE) -> CO2e (kg)

* Energy is integrated ONCE per interval (power x seconds / 3.6e6) - no double counting.
* Facility energy = IT energy x PUE; carbon uses facility energy.
* Result `method` is 'estimated' unless a measured power value is supplied.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from app.utils.units import emissions_kg, watts_seconds_to_kwh


@dataclass(frozen=True)
class InstanceSpec:
    name: str
    vcpu: int
    mem_gb: float
    idle_w: float
    peak_w: float
    hourly_cost: float
    gpu_count: int = 0


@dataclass(frozen=True)
class EnergyConfig:
    ram_w_per_gb: float = 0.375
    ram_idle_fraction: float = 0.5
    gpu_idle_w: float = 25.0
    gpu_peak_w: float = 250.0
    disk_max_w: float = 6.0
    disk_ref_mb_s: float = 500.0
    nic_max_w: float = 8.0
    nic_ref_mbit_s: float = 1000.0
    calibrated: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> "EnergyConfig":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


DEFAULT_CFG = EnergyConfig()


@dataclass
class EnergyResult:
    it_power_w: object
    components_w: dict
    it_kwh: object
    facility_kwh: object
    co2e_kg: object
    pue: float
    ci_g_per_kwh: object
    confidence: float
    method: str            # 'estimated' | 'measured'
    assumptions: dict


def _clip01(x):
    return np.clip(np.nan_to_num(np.asarray(x, dtype=float)), 0.0, 1.0)


def power_components(spec: InstanceSpec, cpu, mem, gpu=None, net_mbit_s=None, disk_mb_s=None,
                     cfg: EnergyConfig = DEFAULT_CFG) -> dict:
    """Per-component power draw in watts. Works on scalars or numpy arrays."""
    cpu, mem = _clip01(cpu), _clip01(mem)
    platform = spec.idle_w + (spec.peak_w - spec.idle_w) * cpu
    ram = spec.mem_gb * cfg.ram_w_per_gb * (cfg.ram_idle_fraction + (1 - cfg.ram_idle_fraction) * mem)
    if spec.gpu_count:
        g = _clip01(gpu) if gpu is not None else 0.0
        gpu_w = spec.gpu_count * (cfg.gpu_idle_w + (cfg.gpu_peak_w - cfg.gpu_idle_w) * g)
    else:
        gpu_w = 0.0 * cpu
    storage = cfg.disk_max_w * np.clip(np.nan_to_num(np.asarray(disk_mb_s if disk_mb_s is not None else 0.0, dtype=float)) / cfg.disk_ref_mb_s, 0, 1) + 0.0 * cpu
    network = cfg.nic_max_w * np.clip(np.nan_to_num(np.asarray(net_mbit_s if net_mbit_s is not None else 0.0, dtype=float)) / cfg.nic_ref_mbit_s, 0, 1) + 0.0 * cpu
    return {"cpu_platform_w": platform, "ram_w": ram, "gpu_w": gpu_w, "storage_w": storage, "network_w": network}


def confidence_score(*, utilization_origin: str, has_net: bool, has_disk: bool, calibrated: bool,
                     measured_power: bool) -> float:
    """Heuristic 0-1 score of how much to trust the estimate. NOT a statistical interval.
    Starts low because generic power coefficients are uncalibrated."""
    if measured_power:
        return 0.95
    s = 0.40
    s += 0.10 if utilization_origin == "measured" else 0.0
    s += 0.05 if has_net else 0.0
    s += 0.05 if has_disk else 0.0
    s += 0.20 if calibrated else 0.0
    return round(min(s, 0.85), 2)


def estimate(spec: InstanceSpec, cpu, mem, interval_s, ci_g_per_kwh, *, gpu=None, net_mbit_s=None,
             disk_mb_s=None, pue: float = 1.58, cfg: EnergyConfig = DEFAULT_CFG,
             utilization_origin: str = "simulated", measured_power_w=None) -> EnergyResult:
    if measured_power_w is not None:
        it_power = np.asarray(measured_power_w, dtype=float)
        comps: dict = {}
        method = "measured"
    else:
        comps = power_components(spec, cpu, mem, gpu, net_mbit_s, disk_mb_s, cfg)
        it_power = sum(comps.values())
        method = "estimated"
    it_kwh = watts_seconds_to_kwh(it_power, interval_s)
    facility = it_kwh * pue
    co2 = emissions_kg(facility, ci_g_per_kwh)
    conf = confidence_score(utilization_origin=utilization_origin, has_net=net_mbit_s is not None,
                            has_disk=disk_mb_s is not None, calibrated=cfg.calibrated,
                            measured_power=measured_power_w is not None)
    return EnergyResult(it_power, comps, it_kwh, facility, co2, pue, ci_g_per_kwh, conf, method,
                        {"pue": pue, "energy_config": asdict(cfg), "instance": spec.name,
                         "note": "IT power from linear utilization model; uncalibrated unless stated"})


def estimate_frame(df, specs: dict, pue_by_region: dict, cfg: EnergyConfig = DEFAULT_CFG):
    """Vectorised estimate for a telemetry DataFrame.
    Required columns: instance_type, region_code, cpu, mem, interval_s, ci_g_per_kwh (optional gpu, net_mbit_s, disk_mb_s)."""
    out = df.copy()
    for col in ("it_power_w", "it_kwh", "facility_kwh", "co2e_kg"):
        out[col] = 0.0
    for itype, idx in out.groupby("instance_type").groups.items():
        sub = out.loc[idx]
        pue = sub["region_code"].map(pue_by_region).astype(float).to_numpy()
        r = estimate(specs[itype], sub["cpu"].to_numpy(), sub["mem"].to_numpy(), sub["interval_s"].to_numpy(),
                     sub["ci_g_per_kwh"].to_numpy(),
                     gpu=sub["gpu"].to_numpy() if "gpu" in sub else None,
                     net_mbit_s=sub["net_mbit_s"].to_numpy() if "net_mbit_s" in sub else None,
                     disk_mb_s=sub["disk_mb_s"].to_numpy() if "disk_mb_s" in sub else None,
                     pue=pue, cfg=cfg)
        out.loc[idx, "it_power_w"] = r.it_power_w
        out.loc[idx, "it_kwh"] = r.it_kwh
        out.loc[idx, "facility_kwh"] = r.facility_kwh
        out.loc[idx, "co2e_kg"] = r.co2e_kg
    return out


def paper_baseline_energy_kwh(cpu_util, runtime_s, mem_gb=0.0, p_idle=100.0, p_peak=400.0, beta=0.375):
    """The reference paper's CPU-only model with its unit error CORRECTED (divide by 3.6e6).
    Used only as the 'original system' baseline in comparisons."""
    cpu_util = _clip01(cpu_util)
    return ((p_idle + (p_peak - p_idle) * cpu_util) * runtime_s + beta * mem_gb * runtime_s) / 3_600_000
