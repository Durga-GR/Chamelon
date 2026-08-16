"""
Project Chameleon — Trade-off Slider Dashboard (polished)
=============================================================

Same logic as before, wired directly into policy.py's evaluate_policy().
This version adds visual polish: custom dark theme, styled status cards
instead of a plain table, and a color-coded Plotly chart instead of the
default st.bar_chart.

It also adds two things that make the demo prove more than "the slider
recomputes a threshold":
  - a world map with the real regions, colored live by carbon intensity,
    with animated arcs drawn for every MIGRATE decision
  - a 24h replay scrubber that drives the map/decisions from a real-shaped
    diurnal carbon curve per grid, so the audience can watch decisions
    change because the *carbon signal* moved, not because someone touched
    the weight slider

Run:
    streamlit run dashboard.py
"""

import os
import streamlit as st
import plotly.graph_objects as go

from policy import evaluate_policy, REGIONS, SERVICES, REGION_SOURCES
from carbon_source import REGION_COORDS, get_all_24h_curves


st.set_page_config(page_title="Project Chameleon", page_icon="🦎", layout="wide")

# ---------------------------------------------------------------------------
# Palette — dark "mood shift" theme: near-black surfaces, electric lime for
# a clean/MIGRATE signal, coral for a dirty/high-carbon signal. The lime<->
# coral pair is also the map's colorscale, so the same two colors mean the
# same thing everywhere on the page (a real chameleon's flash colors when
# it shifts state, not a decorative gradient).
# ---------------------------------------------------------------------------
BASE = "#0D0F12"        # app background
SURFACE = "#171A1F"     # decision cards
SURFACE_ALT = "#1C2027" # explanation cards
BORDER = "#2A2F37"
TEAL = "#4FD1C5"        # clean grid / MIGRATE
CORAL = "#FF5C4D"       # dirty grid / high carbon
AMBER = "#FFB54D"       # simulated-data indicator
TEXT = "#EDEFF2"
MUTED = "#8B93A0"
STAY_TONE = "#4A515C"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .chameleon-hero h1, .section-title, .service-name {{
        font-family: 'Space Grotesk', 'Inter', sans-serif;
    }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
    .stApp {{ background-color: {BASE}; }}
    body, .stMarkdown, p, span, label {{ color: {TEXT}; font-family: 'Inter', sans-serif; }}

    .chameleon-hero {{
        background: linear-gradient(135deg, #0D0F12 0%, #1A1030 100%);
        border: 1px solid {BORDER};
        border-radius: 16px;
        padding: 2rem 2.2rem;
        margin-bottom: 1.6rem;
    }}
    .chameleon-hero h1 {{
        margin: 0;
        font-size: 2.1rem;
        font-weight: 800;
        color: {TEAL};
        text-shadow: 0 0 24px rgba(79, 209, 197, 0.25);
    }}
    .chameleon-hero p {{
        margin: 0.3rem 0 0 0;
        color: {MUTED};
        font-size: 1rem;
    }}

    .badge {{
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: 0.9rem;
    }}
    .badge-live {{ background: rgba(79, 209, 197, 0.14); color: {TEAL}; border: 1px solid rgba(79, 209, 197, 0.3); }}
    .badge-sim {{ background: rgba(255, 181, 77, 0.14); color: {AMBER}; border: 1px solid rgba(255, 181, 77, 0.3); }}

    .decision-card {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 0.8rem;
        border-left: 4px solid {TEAL};
    }}
    .decision-card.stay {{ border-left-color: {STAY_TONE}; }}

    .decision-card .service-name {{
        font-weight: 700;
        font-size: 1.05rem;
        color: {TEXT};
    }}
    .decision-card .route {{
        color: {MUTED};
        font-size: 0.9rem;
        margin-top: 0.15rem;
    }}
    .status-pill {{
        display: inline-block;
        padding: 0.15rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.03em;
    }}
    .status-migrate {{ background: {TEAL}; color: {BASE}; }}
    .status-stay {{ background: {STAY_TONE}; color: {TEXT}; }}

    .explanation-card {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 1rem 1.3rem;
        margin-bottom: 0.7rem;
    }}
    .explanation-card .service-name {{
        font-weight: 700;
        color: {TEAL};
        font-size: 0.95rem;
        margin-bottom: 0.2rem;
    }}
    .explanation-card .explanation-text {{
        color: {TEXT};
        font-size: 0.95rem;
        font-style: italic;
    }}

    .section-title {{
        font-weight: 800;
        font-size: 1.3rem;
        color: {TEXT};
        margin: 0.4rem 0 0.9rem 0;
    }}

    .disclaimer {{
        background: rgba(255, 181, 77, 0.1);
        border: 1px solid rgba(255, 181, 77, 0.25);
        border-radius: 10px;
        padding: 0.8rem 1.1rem;
        color: {AMBER};
        font-size: 0.85rem;
        margin-top: 1rem;
    }}

    /* Ambient drifting background — subtle, low-opacity blobs of lime/coral
       that slowly move behind everything. z-index: -1 guarantees it paints
       behind normal content regardless of Streamlit's internal DOM/class
       names, which can change between versions. */
    .stApp::before {{
        content: "";
        position: fixed;
        inset: 0;
        z-index: -1;
        pointer-events: none;
        background:
            radial-gradient(circle at 15% 20%, rgba(79, 209, 197, 0.10), transparent 42%),
            radial-gradient(circle at 85% 15%, rgba(255, 92, 77, 0.08), transparent 40%),
            radial-gradient(circle at 50% 90%, rgba(79, 209, 197, 0.06), transparent 45%);
        background-size: 180% 180%;
        animation: chameleonDrift 26s ease-in-out infinite;
    }}
    @keyframes chameleonDrift {{
        0%   {{ background-position: 0% 0%, 100% 0%, 50% 100%; }}
        50%  {{ background-position: 25% 35%, 65% 55%, 35% 65%; }}
        100% {{ background-position: 0% 0%, 100% 0%, 50% 100%; }}
    }}

    /* Rising particles inside the hero banner — small dots drifting upward
       and fading, like carbon dispersing off the grid. Contained to the
       hero only so it never distracts from the charts/map below. */
    .chameleon-hero {{
        position: relative;
        overflow: hidden;
    }}
    .hero-particle {{
        position: absolute;
        bottom: -10px;
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: {TEAL};
        opacity: 0;
        animation: riseFade 8s ease-in infinite;
    }}
    @keyframes riseFade {{
        0%   {{ transform: translateY(0) scale(1); opacity: 0; }}
        15%  {{ opacity: 0.55; }}
        90%  {{ opacity: 0; }}
        100% {{ transform: translateY(-140px) scale(0.6); opacity: 0; }}
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Hero header
# ---------------------------------------------------------------------------
st.markdown("""
<div class="chameleon-hero">
    <div class="hero-particle" style="left:6%;  animation-delay:0s;   background:#4FD1C5;"></div>
    <div class="hero-particle" style="left:18%; animation-delay:1.4s; background:#FF5C4D;"></div>
    <div class="hero-particle" style="left:32%; animation-delay:2.8s; background:#4FD1C5;"></div>
    <div class="hero-particle" style="left:47%; animation-delay:0.6s; background:#4FD1C5;"></div>
    <div class="hero-particle" style="left:61%; animation-delay:3.6s; background:#FF5C4D;"></div>
    <div class="hero-particle" style="left:74%; animation-delay:1.9s; background:#4FD1C5;"></div>
    <div class="hero-particle" style="left:88%; animation-delay:4.4s; background:#4FD1C5;"></div>
    <div class="hero-particle" style="left:95%; animation-delay:2.2s; background:#FF5C4D;"></div>
    <h1>🦎 Project Chameleon</h1>
    <p>Interactive carbon-vs-speed trade-off control &mdash; Section 3.5</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Mode: current reading vs. 24h replay
# ---------------------------------------------------------------------------
mode = st.radio(
    "Data mode",
    ["Current reading", "24h replay"],
    horizontal=True,
    label_visibility="collapsed",
)

hour = None
if mode == "24h replay":
    curves = get_all_24h_curves()
    hour = st.slider(
        "Hour of day",
        min_value=0,
        max_value=23,
        value=9,
        step=1,
        format="%d:00",
        help="Drag through a simulated day. Decisions below react to the "
             "changing carbon signal at each hour — the weight slider "
             "doesn't move.",
    )
    active_regions = {region: values[hour] for region, values in curves.items()}
    active_sources = {region: "simulated (24h demo curve)" for region in curves}
else:
    active_regions = REGIONS
    active_sources = REGION_SOURCES

# ---------------------------------------------------------------------------
# Slider — trade-off weight, everything below reacts to it
# ---------------------------------------------------------------------------
weight = st.slider(
    "Speed  ⟷  Carbon Reduction",
    min_value=0.0,
    max_value=1.0,
    value=0.5,
    step=0.05,
    help="0.0 = prioritize speed / low migration cost. 1.0 = prioritize carbon savings.",
)

results = evaluate_policy(active_regions, SERVICES, weight)

using_live_llm = os.environ.get("ANTHROPIC_API_KEY") is not None
if using_live_llm:
    st.markdown('<span class="badge badge-live">🟢 Live Claude explanations</span>', unsafe_allow_html=True)
else:
    st.markdown('<span class="badge badge-sim">🟡 Simulated explanations — set ANTHROPIC_API_KEY for live</span>', unsafe_allow_html=True)

with st.expander("Carbon data source (per region)", expanded=False):
    for region, value in active_regions.items():
        source = active_sources[region]
        icon = "🟢 live" if source == "live" else "🟡 simulated"
        label = REGION_COORDS.get(region, {}).get("label", region)
        st.write(f"**{region}** ({label}) — {value} gCO2/kWh &nbsp;·&nbsp; {icon}")

st.write("")

# ---------------------------------------------------------------------------
# World map — real regions, colored live by carbon intensity, with an
# animated-feeling arc drawn for every MIGRATE decision this run
# ---------------------------------------------------------------------------
st.markdown('<div class="section-title">Where the workloads actually are</div>', unsafe_allow_html=True)

map_fig = go.Figure()

lats = [REGION_COORDS[r]["lat"] for r in active_regions]
lons = [REGION_COORDS[r]["lon"] for r in active_regions]
intensities = [active_regions[r] for r in active_regions]
labels = [REGION_COORDS[r]["label"] for r in active_regions]

map_fig.add_trace(go.Scattergeo(
    lat=lats, lon=lons,
    text=[f"{l}<br>{v} gCO2/kWh" for l, v in zip(labels, intensities)],
    hoverinfo="text",
    mode="markers",
    marker=dict(
        size=[24 + (v / max(intensities)) * 22 for v in intensities],
        color=intensities,
        colorscale=[[0, TEAL], [1, CORAL]],
        cmin=40,
        cmax=700,
        line=dict(width=1.5, color=BASE),
        showscale=False,
    ),
    name="Regions",
))

for r in results:
    if r["migrate"]:
        src = REGION_COORDS[r["current_region"]]
        dst = REGION_COORDS[r["target_region"]]
        map_fig.add_trace(go.Scattergeo(
            lat=[src["lat"], dst["lat"]],
            lon=[src["lon"], dst["lon"]],
            mode="lines",
            line=dict(width=2.5, color=TEAL, dash="dot"),
            opacity=0.9,
            hoverinfo="skip",
            showlegend=False,
        ))
        map_fig.add_trace(go.Scattergeo(
            lat=[dst["lat"]], lon=[dst["lon"]],
            mode="markers",
            marker=dict(size=14, color=TEAL, symbol="triangle-up",
                        line=dict(width=1, color=BASE)),
            hoverinfo="skip",
            showlegend=False,
        ))

map_fig.update_layout(
    geo=dict(
        projection_type="natural earth",
        showland=True, landcolor="#20242B",
        showocean=True, oceancolor="#14171B",
        showcountries=True, countrycolor=BORDER,
        bgcolor="rgba(0,0,0,0)",
    ),
    margin=dict(l=0, r=0, t=10, b=0),
    height=380,
    paper_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(map_fig, use_container_width=True)
st.caption("Dot size/color = carbon intensity right now (lime = clean, coral = dirty). Dotted lime arcs = a MIGRATE decision this run.")

st.write("")

# ---------------------------------------------------------------------------
# Two columns: decision cards + chart
# ---------------------------------------------------------------------------
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    title = "Migration Decisions"
    if hour is not None:
        title += f" &nbsp;<span style='font-weight:500;font-size:0.85rem;color:{MUTED};'>— at {hour:02d}:00</span>"
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    for r in results:
        stay_class = "" if r["migrate"] else "stay"
        pill_class = "status-migrate" if r["migrate"] else "status-stay"
        pill_text = "🔀 MIGRATE" if r["migrate"] else "⏸ STAY"
        route = (
            f"{r['current_region']} ({r['current_intensity']} gCO2/kWh) &rarr; "
            f"{r['target_region']} ({r['target_intensity']} gCO2/kWh)"
            if r["migrate"] else
            f"Staying in {r['current_region']} ({r['current_intensity']} gCO2/kWh)"
        )
        st.markdown(f"""
        <div class="decision-card {stay_class}">
            <div class="service-name">{r['service']} &nbsp; <span class="status-pill {pill_class}">{pill_text}</span></div>
            <div class="route">{route}</div>
        </div>
        """, unsafe_allow_html=True)

with col2:
    st.markdown('<div class="section-title">Carbon Savings vs. Migration Cost</div>', unsafe_allow_html=True)

    services = [r["service"] for r in results]
    savings = [r["carbon_savings"] for r in results]
    costs = [r["migration_cost"] for r in results]
    bar_colors = [TEAL if r["migrate"] else STAY_TONE for r in results]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=services, y=savings, name="Carbon savings (gCO2/kWh)",
        marker_color=bar_colors,
        text=savings, textposition="outside",
        textfont=dict(color=TEXT),
    ))
    fig.add_trace(go.Scatter(
        x=services, y=costs, name="Migration cost (0-100)",
        mode="markers+lines", marker=dict(size=12, color=CORAL),
        line=dict(color=CORAL, dash="dot"),
        yaxis="y2",
    ))
    fig.update_layout(
        yaxis=dict(title="Carbon savings (gCO2/kWh)", color=TEXT, gridcolor=BORDER),
        yaxis2=dict(title="Migration cost (0-100)", overlaying="y", side="right", range=[0, 100], color=TEXT, gridcolor=BORDER),
        xaxis=dict(color=TEXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=TEXT)),
        margin=dict(l=10, r=10, t=40, b=10),
        height=360,
        plot_bgcolor=SURFACE,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT),
    )
    st.plotly_chart(fig, use_container_width=True)

st.write("")

# ---------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------
st.markdown('<div class="section-title">Explanations</div>', unsafe_allow_html=True)
for r in results:
    icon = "🔀" if r["migrate"] else "⏸"
    st.markdown(f"""
    <div class="explanation-card">
        <div class="service-name">{icon} {r['service']}</div>
        <div class="explanation-text">{r['explanation']}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="disclaimer">
    ⚠️ Migration itself is logged/simulated for this demo — no real container orchestration runs.
    The decision policy, weighting, and explanations above are live and real.
</div>
""", unsafe_allow_html=True)
