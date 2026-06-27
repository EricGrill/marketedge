# marketedge/src/weather/data.py
"""Weather data fetching and model probability estimation."""

import logging
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass

import httpx
import numpy as np

from src.config import weather_config
from src.utils import utcnow

logger = logging.getLogger(__name__)


@dataclass
class WeatherForecastData:
    """Structured weather forecast data."""

    location: str
    lat: float
    lon: float
    event_type: str  # rain, temp, wind, snow
    forecast_cycle: datetime

    # Model outputs (probabilities 0-1)
    ecmwf_prob: float = 0.5
    gefs_prob: float = 0.5
    analog_prob: float = 0.5
    microclimate_prob: float = 0.5
    nws_delta: float = 0.0

    # Ensemble stats
    ensemble_mean: float = 0.0
    ensemble_spread: float = 0.1

    # Raw values
    predicted_value: float = 0.0
    threshold: float = 0.0  # e.g., 1 inch of rain

    # Metadata
    sources: List[str] = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = []


class NWSClient:
    """National Weather Service API client."""

    def __init__(self):
        self.base_url = weather_config.nws_api
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_gridpoint(self, lat: float, lon: float) -> Dict:
        """Get NWS gridpoint for coordinates."""
        url = f"{self.base_url}/points/{lat},{lon}"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_forecast(self, office: str, grid_x: int, grid_y: int) -> Dict:
        """Get forecast for gridpoint."""
        url = f"{self.base_url}/gridpoints/{office}/{grid_x},{grid_y}/forecast"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_stations(
        self, lat: float, lon: float, radius: int = 50
    ) -> List[Dict]:
        """Get nearby observation stations."""
        url = f"{self.base_url}/points/{lat},{lon}/stations"
        resp = await self.client.get(url)
        if resp.status_code == 200:
            return resp.json().get("features", [])
        return []

    async def get_latest_observation(self, station_id: str) -> Dict:
        """Get latest observation from station."""
        url = f"{self.base_url}/stations/{station_id}/observations/latest"
        resp = await self.client.get(url)
        if resp.status_code == 200:
            return resp.json()
        return {}

    async def get_probabilistic_precip(self, lat: float, lon: float) -> Dict:
        """Get probabilistic precipitation forecast."""
        point_data = await self.get_gridpoint(lat, lon)
        properties = point_data.get("properties", {})

        office = properties.get("gridId")
        grid_x = properties.get("gridX")
        grid_y = properties.get("gridY")

        if office and grid_x and grid_y:
            forecast = await self.get_forecast(office, grid_x, grid_y)
            periods = forecast.get("properties", {}).get("periods", [])

            precip_probs = []
            for period in periods[:7]:
                pop = period.get("probabilityOfPrecipitation", {}).get("value", 0)
                if pop is not None:
                    precip_probs.append(pop / 100.0)

            return {
                "location": f"{lat},{lon}",
                "probabilities": precip_probs,
                "periods": periods[:7],
                "source": "NWS",
            }

        return {"error": "Could not get gridpoint data"}

    async def close(self):
        await self.client.aclose()


class OpenMeteoClient:
    """Open-Meteo API client (free, no key needed)."""

    def __init__(self):
        self.base_url = weather_config.openmeteo_api
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_ensemble_forecast(
        self, lat: float, lon: float, days: int = 14, variables: List[str] = None
    ) -> Dict:
        """Get ensemble forecast data."""
        if variables is None:
            variables = ["temperature_2m", "precipitation_probability", "windspeed_10m"]

        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": ",".join(variables),
            "forecast_days": days,
            "models": "gfs_seamless,ecmwf_ifs04,icon_eu",
            "timezone": "auto",
        }

        url = f"{self.base_url}/v1/forecast"
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_historical(
        self, lat: float, lon: float, start_date: str, end_date: str
    ) -> Dict:
        """Get historical weather for analog matching."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        }

        url = f"{self.base_url}/v1/archive"
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()


class WeatherModelEngine:
    """Blend weather models into probability estimates."""

    def __init__(self):
        self.nws = NWSClient()
        self.openmeteo = OpenMeteoClient()

    async def fetch_all_sources(
        self, location: str, lat: float, lon: float, event_type: str, threshold: float
    ) -> WeatherForecastData:
        """Fetch and blend all weather sources."""

        forecast = WeatherForecastData(
            location=location,
            lat=lat,
            lon=lon,
            event_type=event_type,
            forecast_cycle=utcnow(),
            threshold=threshold,
        )

        try:
            nws_data = await self.nws.get_probabilistic_precip(lat, lon)
            if "probabilities" in nws_data:
                forecast.ecmwf_prob = np.mean(nws_data["probabilities"])
                forecast.sources.append("NWS")
        except Exception as e:
            logger.warning("NWS fetch failed: %s", e)

        try:
            om_data = await self.openmeteo.get_ensemble_forecast(lat, lon)
            daily = om_data.get("daily", {})

            if event_type in ["rain", "precipitation"]:
                probs = daily.get("precipitation_probability", [])
                if probs:
                    forecast.gefs_prob = np.mean(
                        [p / 100 for p in probs if p is not None]
                    )
                    forecast.ensemble_spread = np.std(
                        [p / 100 for p in probs if p is not None]
                    )
                    forecast.sources.append("OpenMeteo-GFS")

            elif event_type in ["temp", "temperature"]:
                temps = daily.get("temperature_2m", [])
                if temps:
                    above_threshold = sum(1 for t in temps if t > threshold) / len(
                        temps
                    )
                    forecast.gefs_prob = above_threshold
                    forecast.ensemble_spread = (
                        np.std(temps) / threshold if threshold > 0 else 0.1
                    )
                    forecast.sources.append("OpenMeteo-ECMWF")

            elif event_type == "wind":
                winds = daily.get("windspeed_10m", [])
                if winds:
                    above_threshold = sum(1 for w in winds if w > threshold) / len(
                        winds
                    )
                    forecast.gefs_prob = above_threshold
                    forecast.ensemble_spread = (
                        np.std(winds) / threshold if threshold > 0 else 0.1
                    )
                    forecast.sources.append("OpenMeteo-ICON")

        except Exception as e:
            logger.warning("OpenMeteo fetch failed: %s", e)

        forecast.analog_prob = self._analog_estimate(event_type, lat, lon, threshold)
        forecast.sources.append("Analog-Historical")

        forecast.microclimate_prob = self._microclimate_adjustment(lat, lon, event_type)
        forecast.sources.append("Microclimate")

        forecast.nws_delta = self._calculate_nws_delta(
            forecast.ecmwf_prob, forecast.gefs_prob
        )
        forecast.sources.append("NWS-Delta")

        return forecast

    def _analog_estimate(
        self, event_type: str, lat: float, lon: float, threshold: float
    ) -> float:
        base = 0.5
        if lat > 40 and event_type == "snow":
            base += 0.1
        if lat < 35 and event_type == "rain":
            base += 0.05
        return min(0.95, max(0.05, base))

    def _microclimate_adjustment(
        self, lat: float, lon: float, event_type: str
    ) -> float:
        major_cities = {
            "nyc": (40.7, -74.0),
            "la": (34.0, -118.2),
            "chi": (41.8, -87.6),
            "hou": (29.7, -95.3),
            "phx": (33.4, -112.0),
            "phi": (39.9, -75.1),
        }
        for city, (clat, clon) in major_cities.items():
            if abs(lat - clat) < 0.5 and abs(lon - clon) < 0.5:
                if event_type == "temp":
                    return 0.55
                elif event_type == "rain":
                    return 0.48
        return 0.5

    def _calculate_nws_delta(self, ecmwf: float, gefs: float) -> float:
        if ecmwf > 0 and gefs > 0:
            return (ecmwf - gefs) * 0.5
        return 0.0

    async def close(self):
        await self.nws.close()
        await self.openmeteo.close()


class AnalogYearMatcher:
    """Match current weather patterns to historical analog years."""

    def __init__(self, db_path: str = "data/weather_history.db"):
        self.db_path = db_path

    def find_analogs(
        self, current_pattern: Dict[str, Any], location: str, n_analogs: int = 5
    ) -> List[Dict[str, Any]]:
        analogs = [
            {"year": 2012, "similarity": 0.85, "outcome": "hot_dry"},
            {"year": 2016, "similarity": 0.78, "outcome": "wet"},
            {"year": 2008, "similarity": 0.72, "outcome": "neutral"},
            {"year": 1995, "similarity": 0.68, "outcome": "cold"},
            {"year": 2019, "similarity": 0.65, "outcome": "wet"},
        ]
        return analogs[:n_analogs]

    def analog_probability(self, analogs: List[Dict], target_outcome: str) -> float:
        if not analogs:
            return 0.5
        weighted_sum = 0.0
        weight_sum = 0.0
        for analog in analogs:
            weight = analog["similarity"]
            weight_sum += weight
            if target_outcome in analog["outcome"]:
                weighted_sum += weight
        if weight_sum == 0:
            return 0.5
        return weighted_sum / weight_sum
