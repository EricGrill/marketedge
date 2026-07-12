import pytest

from src.weather.data import OpenMeteoClient


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"daily": {}}


@pytest.mark.asyncio
async def test_openmeteo_requests_daily_aggregation_vars_without_models():
    # Regression for the OpenMeteo HTTP 400: the /forecast `daily` field only
    # accepts daily-aggregation variable names, and passing an explicit `models`
    # list both risks stale IDs and suffixes the response keys. Guard both.
    client = OpenMeteoClient()
    captured = {}

    async def fake_get(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse()

    client.client.get = fake_get
    try:
        await client.get_ensemble_forecast(40.71, -74.01)
    finally:
        await client.close()

    assert "models" not in captured["params"]
    assert (
        captured["params"]["daily"]
        == "temperature_2m_max,precipitation_probability_max,windspeed_10m_max"
    )
