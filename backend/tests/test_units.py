import pytest
from app.utils.units import emissions_kg, g_to_kg, watts_seconds_to_kwh


def test_kwh():
    assert watts_seconds_to_kwh(1000, 3600) == pytest.approx(1.0)
    assert watts_seconds_to_kwh(250, 1800) == pytest.approx(0.125)


def test_g_to_kg():
    assert g_to_kg(1500) == 1.5


def test_emissions():
    assert emissions_kg(2.0, 500) == pytest.approx(1.0)
