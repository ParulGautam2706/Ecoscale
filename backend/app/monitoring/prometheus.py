"""Prometheus metrics. Labels carry `origin` so dashboards never confuse simulated with measured."""
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

registry = CollectorRegistry()
CPU = Gauge("gc_cpu_utilization_ratio", "CPU utilization (0-1)", ["resource", "region", "origin"], registry=registry)
MEM = Gauge("gc_memory_utilization_ratio", "Memory utilization (0-1)", ["resource", "region", "origin"], registry=registry)
POWER = Gauge("gc_estimated_power_watts", "Estimated IT power (W)", ["resource", "region", "origin"], registry=registry)
ENERGY = Counter("gc_estimated_energy_kwh_total", "Estimated facility energy (kWh)", ["resource", "region", "origin"], registry=registry)
CO2 = Counter("gc_estimated_co2e_kg_total", "Estimated emissions (kgCO2e)", ["resource", "region", "origin"], registry=registry)


def observe(resource: str, region: str, origin: str, cpu: float, mem: float, power_w: float,
            facility_kwh: float, co2e_kg: float) -> None:
    CPU.labels(resource, region, origin).set(cpu)
    MEM.labels(resource, region, origin).set(mem)
    POWER.labels(resource, region, origin).set(power_w)
    ENERGY.labels(resource, region, origin).inc(max(facility_kwh, 0))
    CO2.labels(resource, region, origin).inc(max(co2e_kg, 0))


def render() -> bytes:
    return generate_latest(registry)
