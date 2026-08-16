"""
Project Chameleon — Decision Policy + Explanation Layer
=========================================================

Implements the weighted threshold decision policy described in Section 3.2
of the paper, plus the LLM-generated plain-language explanation layer
described in Section 3.4.

Run directly for a command-line demo:
    python policy.py

Or import and call evaluate_policy() from a dashboard (e.g. Streamlit):
    from policy import evaluate_policy, REGIONS, SERVICES
    results = evaluate_policy(REGIONS, SERVICES, weight=0.5)
"""

import os
import json
import urllib.request
import urllib.error

from carbon_source import get_all_regions


# ---------------------------------------------------------------------------
# Sample data — swap REGIONS values for real carbon-intensity numbers later
# (see carbon_source.py in Prompt 3) without changing anything below.
# ---------------------------------------------------------------------------

# gCO2/kWh — lower is cleaner. Pulled from carbon_source.py, which returns
# live data from the Electricity Maps API when ELECTRICITYMAPS_API_KEY is
# set and reachable, and silently falls back to realistic simulated values
# otherwise. REGION_SOURCES tells you which mode was actually used for
# each region ("live" or "simulated").
REGIONS, REGION_SOURCES = get_all_regions()

# Each microservice: which region it currently runs in, its resource
# footprint, and a migration-cost estimate (0-100 scale, higher = costlier
# to move) derived from image size + expected data transfer, per Sec. 3.2.
SERVICES = {
    "auth-service": {
        "current_region": "asia-south",
        "footprint_mb": 180,
        "migration_cost": 45,
    },
    "recommendation-engine": {
        "current_region": "us-east",
        "footprint_mb": 640,
        "migration_cost": 70,
    },
    "image-processor": {
        "current_region": "asia-south",
        "footprint_mb": 310,
        "migration_cost": 35,
    },
}

# Below this many gCO2/kWh of *weighted* savings, don't bother migrating.
BASE_THRESHOLD = 100

# How strongly migration_cost weighs against migrating at weight=0.
# Retuned for the real-world carbon spread pulled from carbon_source.py
# (France's grid is genuinely ~60 gCO2/kWh vs. ~690 for coal-heavy grids,
# a much bigger gap than arbitrary placeholder numbers would give you) —
# adjust if you change REGIONS/SERVICES.
COST_MULTIPLIER = 7


# ---------------------------------------------------------------------------
# Core policy logic (Section 3.2)
# ---------------------------------------------------------------------------

def _cleanest_region(regions: dict, exclude: str) -> tuple[str, int]:
    """Return (region_name, intensity) for the cleanest region other than `exclude`."""
    candidates = {r: v for r, v in regions.items() if r != exclude}
    best = min(candidates, key=candidates.get)
    return best, candidates[best]


def _evaluate_service(name: str, service: dict, regions: dict, weight: float) -> dict:
    """
    Apply the weighted threshold rule to a single microservice.

    weight: 0.0 = pure speed/cost priority (almost never migrate)
            1.0 = pure carbon priority (migrate whenever there's any savings)
    """
    current_region = service["current_region"]
    current_intensity = regions[current_region]
    target_region, target_intensity = _cleanest_region(regions, current_region)

    carbon_savings = max(0, current_intensity - target_intensity)  # gCO2/kWh saved
    migration_cost = service["migration_cost"]  # 0-100 scale

    # Weighted comparison: as `weight` rises toward 1.0, the effective cost
    # penalty shrinks, making migration easier to justify. As it falls toward
    # 0.0, the cost penalty dominates and migration becomes hard to justify.
    effective_threshold = BASE_THRESHOLD + migration_cost * COST_MULTIPLIER * (1 - weight)
    should_migrate = carbon_savings > effective_threshold

    return {
        "service": name,
        "current_region": current_region,
        "current_intensity": current_intensity,
        "target_region": target_region if should_migrate else current_region,
        "target_intensity": target_intensity if should_migrate else current_intensity,
        "carbon_savings": carbon_savings,
        "migration_cost": migration_cost,
        "effective_threshold": round(effective_threshold, 1),
        "migrate": should_migrate,
    }


def evaluate_policy(regions: dict, services: dict, weight: float = 0.5) -> list[dict]:
    """Evaluate the decision policy for every service, and attach an explanation to each."""
    results = []
    for name, service in services.items():
        decision = _evaluate_service(name, service, regions, weight)
        decision["explanation"] = explain_decision(decision)
        results.append(decision)
    return results


# ---------------------------------------------------------------------------
# Explanation layer (Section 3.4) — calls Claude if ANTHROPIC_API_KEY is set,
# otherwise falls back to a clearly-labeled canned explanation so the script
# still runs end-to-end without a key.
# ---------------------------------------------------------------------------

def _call_claude(prompt: str) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"].strip()
    except (urllib.error.URLError, KeyError, IndexError, TimeoutError):
        return None


def _fallback_explanation(decision: dict) -> str:
    """Deterministic, clearly-labeled stand-in used when no LLM is available."""
    if decision["migrate"]:
        pct = round(
            100 * decision["carbon_savings"] / max(decision["current_intensity"], 1)
        )
        return (
            f"[simulated explanation] Migrated because {decision['target_region']} "
            f"is roughly {pct}% cleaner than {decision['current_region']} "
            f"— worth the estimated migration cost."
        )
    return (
        f"[simulated explanation] Stayed in {decision['current_region']} — "
        f"available carbon savings didn't clear the migration-cost threshold."
    )


def explain_decision(decision: dict) -> str:
    prompt = (
        "You are the explanation layer of a carbon-aware microservice migration "
        "system. In exactly 1-2 short sentences, explain this decision in plain "
        "language for a non-technical operator. Be concrete and specific, no "
        "preamble.\n\n"
        f"Service: {decision['service']}\n"
        f"Decision: {'MIGRATE' if decision['migrate'] else 'STAY'}\n"
        f"From region: {decision['current_region']} "
        f"({decision['current_intensity']} gCO2/kWh)\n"
        f"To region: {decision['target_region']} "
        f"({decision['target_intensity']} gCO2/kWh)\n"
        f"Estimated carbon savings: {decision['carbon_savings']} gCO2/kWh\n"
        f"Migration cost estimate: {decision['migration_cost']}/100\n"
    )
    result = _call_claude(prompt)
    if result:
        return result
    return _fallback_explanation(decision)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _print_results(results: list[dict], weight: float) -> None:
    using_live_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"\nProject Chameleon — Decision Policy Run (weight={weight})")
    print(f"Explanation source: {'Claude API (live)' if using_live_llm else 'simulated fallback (no ANTHROPIC_API_KEY set)'}")
    print("Carbon data:")
    for region, value in REGIONS.items():
        print(f"    {region:12s} {value:4d} gCO2/kWh  [{REGION_SOURCES[region]}]")
    print("=" * 70)
    for r in results:
        status = "MIGRATE" if r["migrate"] else "STAY"
        print(f"\n[{status}] {r['service']}")
        print(f"  {r['current_region']} ({r['current_intensity']} gCO2/kWh) "
              f"-> {r['target_region']} ({r['target_intensity']} gCO2/kWh)")
        print(f"  carbon savings: {r['carbon_savings']} gCO2/kWh | "
              f"migration cost: {r['migration_cost']}/100 | "
              f"threshold: {r['effective_threshold']}")
        print(f"  explanation: {r['explanation']}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    import sys

    weight = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    results = evaluate_policy(REGIONS, SERVICES, weight)
    _print_results(results, weight)
