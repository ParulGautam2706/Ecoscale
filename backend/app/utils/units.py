"""Single source of truth for unit conversions."""


def watts_seconds_to_kwh(watts: float, seconds: float) -> float:
    return watts * seconds / 3_600_000


def g_to_kg(grams: float) -> float:
    return grams / 1000


def emissions_kg(kwh: float, g_per_kwh: float) -> float:
    return g_to_kg(kwh * g_per_kwh)
