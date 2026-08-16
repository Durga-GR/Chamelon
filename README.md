# Project Chameleon — Component 1: Decision Policy + Explanation Layer

Implements the weighted threshold decision policy (Section 3.2 of the paper)
and the LLM explanation layer (Section 3.4).

## Run it

```bash
python3 policy.py            # weight defaults to 0.5
python3 policy.py 0.0        # pure speed/cost priority
python3 policy.py 1.0        # pure carbon priority
```

## Component 2 — Trade-off Slider Dashboard

`dashboard.py` is a Streamlit app that wires a single slider directly into
`evaluate_policy()` from `policy.py`. Moving the slider re-runs the real
policy live and updates:
- the migration decisions table
- a carbon-savings-vs-migration-cost chart
- the explanation text for every service

Run it:

```bash
pip install streamlit pandas plotly
streamlit run dashboard.py
```

It opens in your browser at `http://localhost:8501`. It uses the exact same
`policy.py` as Component 1 — no separate/duplicated logic — so anything true
of Component 1 (real weighted threshold rule, real or simulated LLM
explanations) is true here too.

The `.streamlit/config.toml` file sets a custom green theme matching the
slide deck — make sure this folder stays alongside `dashboard.py` when you
copy the project, or Streamlit will fall back to its default theme.

**Demo tip:** drag the slider from left to right slowly and watch
`recommendation-engine` flip from STAY to MIGRATE around the middle — that's
your proof, live, that the trade-off control actually works.

## Use a real LLM (Claude) for explanations

By default, no API key is required — the script uses a clearly-labeled
simulated fallback explanation so it always runs. To use live Claude-generated
explanations instead:

```bash
export ANTHROPIC_API_KEY="your-key-here"
python3 policy.py 0.5
```

The output header tells you which mode is active:
`Explanation source: Claude API (live)` vs `simulated fallback`.

## Demo tip for judges

Run it at weight=0.0, 0.5, and 1.0 back to back. Watch `recommendation-engine`
flip from STAY to MIGRATE as the weight increases past ~0.6 — that's live proof
the weighted threshold rule actually responds to the carbon-vs-speed trade-off,
not just a hardcoded decision.

## Component 3 — Real Carbon-Intensity Data

`carbon_source.py` pulls live carbon intensity from the Electricity Maps API
for 3 real zones, and is what `policy.py` now uses for `REGIONS` automatically:

| Region key   | Real zone         | Why it's a good demo pick                     |
|--------------|--------------------|------------------------------------------------|
| `us-east`    | US-NY-NYIS (New York) | Moderate, mixed grid                       |
| `eu-west`    | FR (France)        | Nuclear-heavy — genuinely very clean            |
| `asia-south` | IN-SO (South India)| Coal-heavy — genuinely much dirtier             |

**To use live data instead of the fallback:**

```bash
export ELECTRICITYMAPS_API_KEY="your-key-here"   # free tier: electricitymaps.com
python3 policy.py 0.5
streamlit run dashboard.py
```

Without a key — or if the live call fails for any reason (no internet, rate
limit, bad key) — it **silently and automatically** falls back to realistic
simulated values for the same real zones, tagged `[simulated]` in every output
so you're never claiming live data you don't have. This was tested directly:
setting a fake API key forces a real failed live call, and the fallback still
works cleanly with no crash.

Test it standalone:
```bash
python3 carbon_source.py
```

### Note on thresholds

Real carbon values (e.g. France ≈ 60 gCO2/kWh vs. South India ≈ 690 gCO2/kWh)
are a much bigger gap than arbitrary placeholder numbers. `BASE_THRESHOLD` and
`COST_MULTIPLIER` in `policy.py` were retuned against this real spread so the
slider demo (`recommendation-engine` flipping STAY → MIGRATE) still lands
around the middle of the slider, not at one extreme.

