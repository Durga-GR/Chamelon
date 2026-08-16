"""
Project Chameleon — Real Carbon-Intensity Data Source
=========================================================

Pulls live carbon intensity (gCO2/kWh) for real regions from the
Electricity Maps API (Section 3.1). If no API key is set, or the live
call fails for any reason (no internet, rate limit, bad key, DNS
blocked), it silently falls back to realistic simulated values for the
same real-world zones — so a live demo never visibly breaks.

Every value returned is tagged with its source ("live" or "simulated")
so callers (policy.py, dashboard.py) can display this honestly instead
of pretending simulated data is live.
"""

import os
import time
import random
import json
import urllib.request
import urllib.error


# Map our internal region keys to real Electricity Maps zone codes.
# FR (France) is a genuinely useful demo pick: nuclear-heavy grid, so it's
# dramatically cleaner than a coal-heavy grid like IN-SO — the contrast is
# real, not exaggerated for effect.
REGION_ZONES = {
    "us-east": "US-NY-NYIS",   # New York ISO
    "eu-west": "FR",           # France
    "asia-south": "IN-SO",     # Southern India
}

# Realistic baseline values (gCO2/kWh) for the fallback, based on each
# zone's typical grid mix. Real values fluctuate hour to hour — the
# fallback adds small random jitter to imitate that instead of returning
# a dead-flat number, since a demo where the numbers never move looks fake.
SIMULATED_BASELINE = {
    "us-east": 410,
    "eu-west": 60,     # France's nuclear-heavy grid is genuinely this clean
    "asia-south": 690,
}
JITTER_PCT = 0.06  # +/- 6% random walk per call

API_URL = "https://api.electricitymap.org/v3/carbon-intensity/latest"
CACHE_TTL_SECONDS = 60

_cache: dict[str, dict] = {}  # region -> {"value": int, "source": str, "ts": float}


def _simulated_value(region: str) -> int:
    base = SIMULATED_BASELINE[region]
    jitter = base * random.uniform(-JITTER_PCT, JITTER_PCT)
    return max(1, round(base + jitter))


def _fetch_live(zone: str, api_key: str) -> int | None:
    req = urllib.request.Request(
        f"{API_URL}?zone={zone}",
        headers={"auth-token": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            return round(data["carbonIntensity"])
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError, OSError):
        return None


def get_carbon_intensity(region: str) -> tuple[int, str]:
    """
    Return (intensity_gCO2_per_kWh, source) for one region.
    source is "live" or "simulated". Cached for CACHE_TTL_SECONDS to
    avoid hammering the API (or re-jittering wildly) while a slider
    is being dragged repeatedly during a demo.
    """
    if region not in REGION_ZONES:
        raise ValueError(f"Unknown region: {region}")

    cached = _cache.get(region)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL_SECONDS:
        return cached["value"], cached["source"]

    api_key = os.environ.get("ELECTRICITYMAPS_API_KEY")
    value, source = None, "simulated"

    if api_key:
        live_value = _fetch_live(REGION_ZONES[region], api_key)
        if live_value is not None:
            value, source = live_value, "live"

    if value is None:
        value, source = _simulated_value(region), "simulated"

    _cache[region] = {"value": value, "source": source, "ts": time.time()}
    return value, source


# ---------------------------------------------------------------------------
# 24h diurnal curves (for the time-scrubber demo view)
# ---------------------------------------------------------------------------
#
# Electricity Maps' free tier only exposes the *current* reading, not
# historical series, so this is explicitly a simulated demo curve — but it's
# shaped from each grid's real generation mix, not arbitrary:
#   - eu-west (France): nuclear baseload dominates -> flat, low variance
#   - us-east (NY):     mixed grid with a real evening demand peak
#   - asia-south (S. India): coal-heavy, plus a solar dip at midday and a
#     sharp evening peak when solar drops off and coal/gas cover demand
#
# Every value returned is tagged "simulated (24h demo curve)" wherever it's
# displayed, same honesty policy as the live/simulated split above.

REGION_COORDS = {
    "us-east": {"lat": 40.71, "lon": -74.01, "label": "New York, USA"},
    "eu-west": {"lat": 46.60, "lon": 1.88, "label": "France"},
    "asia-south": {"lat": 13.08, "lon": 80.27, "label": "South India"},
}


def _diurnal_multiplier(region: str, hour: int) -> float:
    import math

    if region == "eu-west":
        # Nuclear baseload: small ripple, tiny evening bump
        return 1.0 + 0.06 * math.sin((hour - 18) / 24 * 2 * math.pi)
    if region == "us-east":
        # Morning + evening demand peaks, dip overnight
        return 1.0 + 0.22 * math.sin((hour - 18) / 24 * 2 * math.pi) + 0.05 * math.sin((hour - 8) / 24 * 2 * math.pi)
    if region == "asia-south":
        # Solar dip around midday, sharp coal/gas-driven evening peak
        solar_dip = -0.18 * math.exp(-((hour - 13) ** 2) / 18)
        evening_peak = 0.28 * math.exp(-((hour - 19) ** 2) / 6)
        return 1.0 + solar_dip + evening_peak
    return 1.0


def generate_24h_curve(region: str) -> list[int]:
    """
    Return 24 hourly gCO2/kWh values (index 0 = midnight local) for one
    region, shaped by that grid's real generation profile. Deterministic
    per region (no randomness) so the demo is reproducible run to run.
    """
    if region not in SIMULATED_BASELINE:
        raise ValueError(f"Unknown region: {region}")
    base = SIMULATED_BASELINE[region]
    return [max(1, round(base * _diurnal_multiplier(region, h))) for h in range(24)]


def get_all_24h_curves(regions: list[str] | None = None) -> dict[str, list[int]]:
    """Return {region: [24 hourly gCO2/kWh values]} for the given regions."""
    regions = regions or list(REGION_ZONES.keys())
    return {region: generate_24h_curve(region) for region in regions}


def get_all_regions(regions: list[str] | None = None) -> tuple[dict[str, int], dict[str, str]]:
    """
    Return (intensities, sources) dicts for the given regions
    (defaults to all regions in REGION_ZONES).
    """
    regions = regions or list(REGION_ZONES.keys())
    intensities, sources = {}, {}
    for region in regions:
        value, source = get_carbon_intensity(region)
        intensities[region] = value
        sources[region] = source
    return intensities, sources


if __name__ == "__main__":
    intensities, sources = get_all_regions()
    api_key_set = bool(os.environ.get("ELECTRICITYMAPS_API_KEY"))
    print(f"ELECTRICITYMAPS_API_KEY set: {api_key_set}\n")
    for region, value in intensities.items():
        zone = REGION_ZONES[region]
        print(f"  {region:12s} ({zone:12s}) -> {value:4d} gCO2/kWh  [{sources[region]}]")
