import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(
    page_title="WCSAAA Ranking Dashboard",
    page_icon="🎣",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
[data-testid="stMetricLabel"] { font-size: 0.8rem; color: #666; }
.badge-green {
    color: #155724; background: #d4edda; padding: 2px 10px;
    border-radius: 20px; font-weight: 700; font-size: 0.9rem;
}
.badge-red {
    color: #721c24; background: #f8d7da; padding: 2px 10px;
    border-radius: 20px; font-weight: 700; font-size: 0.9rem;
}
.badge-neutral {
    color: #856404; background: #fff3cd; padding: 2px 10px;
    border-radius: 20px; font-weight: 700; font-size: 0.9rem;
}
.section-title {
    font-size: 1.15rem; font-weight: 700; color: #1a3c5e;
    border-left: 4px solid #1a3c5e; padding-left: 10px; margin: 1rem 0 0.4rem;
}
.auto-chip {
    background: #cce5ff; color: #004085; border-radius: 12px;
    padding: 2px 10px; font-size: 0.75rem; font-weight: 700;
}
div[data-testid="stTabs"] button { font-size: 0.9rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
LEAGUE_MAP = {
    "S": "Senior",
    "M": "Masters",
    "G": "Grandmasters",
    "J": "Junior (U21)",
    "L": "Ladies",
    "K": "Kadet (U16)",
}

# Eligibility per division (field, 3yr rank cutoff, league code, auto-select N, bylaw ref)
DIVISIONS = {
    "Senior A":     dict(field="EligSeniorA",  cutoff=40,   league=None, auto=6,  bylaw="§8.3"),
    "Senior B":     dict(field="EligSeniorB",  cutoff=60,   league=None, auto=4,  bylaw="§8.4"),
    "Development":  dict(field="EligDev",      cutoff=80,   league=None, auto=3,  bylaw="§8.5"),
    "Masters":      dict(field="EligMasters",  cutoff=None, league="M",  auto=4,  bylaw="§8.6"),
    "Grandmasters": dict(field="EligGM",       cutoff=None, league="G",  auto=2,  bylaw="§8.7"),
    "Ladies":       dict(field="EligLadies",   cutoff=None, league="L",  auto=2,  bylaw="§8.8"),
    "Junior (U21)": dict(field="EligU21",      cutoff=80,   league="J",  auto=4,  bylaw="§8.9"),
    "Kadet (U16)":  dict(field="EligU16",      cutoff=None, league="K",  auto=3,  bylaw="§8.10"),
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ── Data ──────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    # Season ranking — Sheet row 2 onward, cols 0,1,2,3,28,29,30
    s_raw = pd.read_excel(
        os.path.join(DATA_DIR, "season_ranking.xlsx"),
        sheet_name="Sheet", header=None,
    )
    season = s_raw.iloc[2:, [0, 1, 2, 3, 28, 29, 30]].copy()
    season.columns = ["SeasonRank", "WP_No", "AnglerS", "ClubS", "TotalPts", "SeasonPosRank", "League"]
    season = season[season["SeasonRank"].notna()].reset_index(drop=True)
    for c in ["SeasonRank", "TotalPts", "SeasonPosRank"]:
        season[c] = pd.to_numeric(season[c], errors="coerce")
    season["WP_No"] = season["WP_No"].astype(str).str.strip()
    # Strip club suffix fragments that appear in some angler names
    season["AnglerS"] = (
        season["AnglerS"].astype(str)
        .str.replace(r"\s+(TWO|FOUR|BLUE)$", "", regex=True)
        .str.strip()
    )

    # 3-year ranking — Position sheet row 4 onward, cols 1,2,3,4,6,7,9,10,12,13,15
    t_raw = pd.read_excel(
        os.path.join(DATA_DIR, "3year_ranking.xlsx"),
        sheet_name="Position", header=None,
    )
    three = t_raw.iloc[4:, [1, 2, 3, 4, 6, 7, 9, 10, 12, 13, 15]].copy()
    three.columns = [
        "ThreeYrRank", "WP_No", "Angler3Yr", "Club3Yr",
        "Pts2526", "PosRank2526",
        "Pts2425", "PosRank2425",
        "Pts2324", "PosRank2324",
        "ThreeYrScore",
    ]
    three = three[three["ThreeYrRank"].notna()].reset_index(drop=True)
    for c in ["ThreeYrRank", "ThreeYrScore", "Pts2526", "Pts2425", "Pts2324",
              "PosRank2526", "PosRank2425", "PosRank2324"]:
        three[c] = pd.to_numeric(three[c], errors="coerce")
    three["WP_No"] = three["WP_No"].astype(str).str.strip()

    # Merge on WP_No (outer join — keep anglers in either list)
    df = pd.merge(
        season.rename(columns={"AnglerS": "AnglerSeason", "ClubS": "ClubSeason"}),
        three.rename(columns={"Angler3Yr": "Angler3Yr", "Club3Yr": "Club3Yr"}),
        on="WP_No", how="outer",
    )

    # Canonical name/club: prefer 3-year (cleaner), fall back to season
    df["Angler"] = df["Angler3Yr"].combine_first(df["AnglerSeason"])
    df["Club"] = df["Club3Yr"].combine_first(df["ClubSeason"])

    # Movement = SeasonRank − ThreeYrRank
    # + means 3-yr rank is BETTER (lower number) than season → improved historically
    # − means 3-yr rank is WORSE (higher number) than season → dropped historically
    df["Movement"] = df["SeasonRank"] - df["ThreeYrRank"]

    # Eligibility flags per Bylaw C
    for div, cfg in DIVISIONS.items():
        cutoff = cfg["cutoff"]
        league = cfg["league"]
        if cutoff and league:
            df[cfg["field"]] = (df["ThreeYrRank"] <= cutoff) & (df["League"] == league)
        elif cutoff:
            df[cfg["field"]] = df["ThreeYrRank"] <= cutoff
        elif league:
            df[cfg["field"]] = df["League"] == league
        else:
            df[cfg["field"]] = False

    return df


df = load_data()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎣 WCSAAA Dashboard")
    st.caption("Position Ranking · Bylaw C Eligibility")
    st.divider()

    st.markdown("### 📋 Division / Nomination")
    selected_divs = st.multiselect(
        "Show eligibility for:",
        list(DIVISIONS.keys()),
        default=["Senior A", "Senior B", "Development"],
    )

    st.markdown("### 🔍 Filters")
    clubs = sorted(df["Club"].dropna().unique())
    sel_clubs = st.multiselect("Club", clubs)

    league_opts = sorted(df["League"].dropna().unique())
    league_labels = [f"{c}  —  {LEAGUE_MAP.get(c, c)}" for c in league_opts]
    sel_league_labels = st.multiselect("League / Division", league_labels)
    sel_leagues = [x.split("  —  ")[0].strip() for x in sel_league_labels]

    only_eligible = st.checkbox("Only eligible anglers (selected divisions)", value=False)

    st.markdown("### 📊 View Mode")
    view_mode = st.radio("Display as:", ["Table", "Chart"], horizontal=True)

    st.divider()
    n_season = int(df["SeasonRank"].notna().sum())
    n_3yr = int(df["ThreeYrRank"].notna().sum())
    n_both = int((df["SeasonRank"].notna() & df["ThreeYrRank"].notna()).sum())
    st.caption(
        f"Season: **{n_season}** anglers  \n"
        f"3-Year: **{n_3yr}** anglers  \n"
        f"In both: **{n_both}** anglers"
    )

# ── Filter ────────────────────────────────────────────────────────────────────
filt = df.copy()
if sel_clubs:
    filt = filt[filt["Club"].isin(sel_clubs)]
if sel_leagues:
    filt = filt[filt["League"].isin(sel_leagues)]
if only_eligible and selected_divs:
    mask = pd.Series(False, index=filt.index)
    for d in selected_divs:
        mask |= filt[DIVISIONS[d]["field"]].fillna(False)
    filt = filt[mask]

both = (
    filt[filt["SeasonRank"].notna() & filt["ThreeYrRank"].notna()]
    .copy()
    .sort_values("Movement", ascending=False)
    .reset_index(drop=True)
)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='text-align:center;color:#1a3c5e;'>🎣 WCSAAA Position Ranking Dashboard</h1>"
    "<p style='text-align:center;color:#666;margin-top:-8px;'>"
    "2025/26 Season vs 3-Year (50:30:20) Weighted Ranking · Selection Criteria per Bylaw C</p>",
    unsafe_allow_html=True,
)

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Matched Anglers", len(both))
k2.metric("▲ Improved (3-Yr)", int((both["Movement"] > 0).sum()))
k3.metric("▼ Dropped (3-Yr)", int((both["Movement"] < 0).sum()))
k4.metric("≈ Consistent (±1)", int(both["Movement"].between(-1, 1).sum()))
avg_mv = both["Movement"].mean() if len(both) else float("nan")
k5.metric("Avg Movement", f"{avg_mv:+.1f}" if not pd.isna(avg_mv) else "—")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Movement Leaderboard",
    "🏆 Top 10 Most Improved",
    "📉 Top 10 Biggest Drops",
    "🎯 Consistency",
    "✅ Eligibility",
    "📈 Scatter Plot",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Movement Leaderboard
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-title">Movement Leaderboard</div>', unsafe_allow_html=True)
    st.caption(
        "Movement = Season Rank − 3-Year Rank. "
        "**Green (positive)** = 3-year rank is better than this season. "
        "**Red (negative)** = 3-year rank is worse than this season."
    )

    disp = both[["Angler", "Club", "League", "SeasonRank", "ThreeYrRank", "Movement", "TotalPts"]].copy()
    disp["League"] = disp["League"].map(lambda x: LEAGUE_MAP.get(x, x) if pd.notna(x) else "")
    disp = disp.rename(columns={
        "SeasonRank": "Season Rank",
        "ThreeYrRank": "3-Yr Rank",
        "TotalPts": "Season Pts",
    })

    if view_mode == "Table":
        def _color_movement(val):
            if pd.isna(val):
                return ""
            if val > 0:
                return "background-color:#d4edda;color:#155724;font-weight:700"
            if val < 0:
                return "background-color:#f8d7da;color:#721c24;font-weight:700"
            return "background-color:#fff3cd;color:#856404;font-weight:700"

        st.dataframe(
            disp.style.applymap(_color_movement, subset=["Movement"]),
            use_container_width=True,
            height=520,
        )
    else:
        chart_df = both.nlargest(80, "Movement") if len(both) > 80 else both
        fig = px.bar(
            chart_df,
            x="Angler", y="Movement",
            color="Movement",
            color_continuous_scale=["#d32f2f", "#f5f5f5", "#2e7d32"],
            color_continuous_midpoint=0,
            labels={"Movement": "Movement (+ = improved)", "Angler": ""},
            title=f"Movement per Angler — top {len(chart_df)}",
            hover_data=["Club", "SeasonRank", "ThreeYrRank"],
        )
        fig.update_layout(xaxis_tickangle=-50, height=500, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Top 10 Most Improved
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-title">Top 10 Most Improved</div>', unsafe_allow_html=True)
    st.caption("Highest positive movement — 3-year rank significantly better than current season rank.")

    top10 = both.nlargest(10, "Movement")

    for i, row in enumerate(top10.itertuples(), 1):
        lg = LEAGUE_MAP.get(row.League, row.League or "")
        c1, c2, c3, c4 = st.columns([0.4, 3.2, 2.2, 1.8])
        c1.markdown(f"**#{i}**")
        c2.markdown(f"**{row.Angler}**  \n<small>{row.Club or ''} · {lg}</small>", unsafe_allow_html=True)
        c3.markdown(f"Season **{int(row.SeasonRank)}** → 3-Yr **{int(row.ThreeYrRank)}**")
        c4.markdown(f"<span class='badge-green'>▲ +{int(row.Movement)}</span>", unsafe_allow_html=True)

    if view_mode == "Chart":
        fig = px.bar(
            top10, x="Movement", y="Angler", orientation="h",
            color_discrete_sequence=["#2e7d32"],
            text="Movement",
            labels={"Movement": "Movement (+)", "Angler": ""},
        )
        fig.update_traces(texttemplate="+%{text}", textposition="outside")
        fig.update_layout(height=380, yaxis=dict(autorange="reversed"), margin=dict(l=160))
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Top 10 Biggest Drops
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-title">Top 10 Biggest Drops</div>', unsafe_allow_html=True)
    st.caption("Largest negative movement — strong this season but weaker historically.")

    bot10 = both.nsmallest(10, "Movement")

    for i, row in enumerate(bot10.itertuples(), 1):
        lg = LEAGUE_MAP.get(row.League, row.League or "")
        c1, c2, c3, c4 = st.columns([0.4, 3.2, 2.2, 1.8])
        c1.markdown(f"**#{i}**")
        c2.markdown(f"**{row.Angler}**  \n<small>{row.Club or ''} · {lg}</small>", unsafe_allow_html=True)
        c3.markdown(f"Season **{int(row.SeasonRank)}** → 3-Yr **{int(row.ThreeYrRank)}**")
        c4.markdown(f"<span class='badge-red'>▼ {int(row.Movement)}</span>", unsafe_allow_html=True)

    if view_mode == "Chart":
        fig = px.bar(
            bot10, x="Movement", y="Angler", orientation="h",
            color_discrete_sequence=["#c62828"],
            text="Movement",
            labels={"Movement": "Movement (−)", "Angler": ""},
        )
        fig.update_traces(texttemplate="%{text}", textposition="outside")
        fig.update_layout(height=380, yaxis=dict(autorange="reversed"), margin=dict(l=160))
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Consistency
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-title">Consistent Anglers  (Movement −1 to +1)</div>', unsafe_allow_html=True)
    st.caption("Anglers whose ranking is stable across both the season and the 3-year system.")

    consistent = both[both["Movement"].between(-1, 1)].sort_values("ThreeYrRank").reset_index(drop=True)

    disp_c = consistent[["Angler", "Club", "League", "SeasonRank", "ThreeYrRank", "Movement", "TotalPts"]].copy()
    disp_c["League"] = disp_c["League"].map(lambda x: LEAGUE_MAP.get(x, x) if pd.notna(x) else "")
    disp_c = disp_c.rename(columns={"SeasonRank": "Season Rank", "ThreeYrRank": "3-Yr Rank", "TotalPts": "Season Pts"})
    disp_c.index = disp_c.index + 1

    if view_mode == "Table":
        st.dataframe(
            disp_c.style.applymap(
                lambda v: "background-color:#fff3cd;color:#856404;font-weight:700",
                subset=["Movement"],
            ),
            use_container_width=True, height=460,
        )
    else:
        fig = px.scatter(
            consistent, x="ThreeYrRank", y="SeasonRank",
            color_discrete_sequence=["#f0a500"],
            hover_data=["Angler", "Club"],
            labels={"ThreeYrRank": "3-Year Rank", "SeasonRank": "Season Rank"},
            title="Consistent Anglers — near the diagonal",
        )
        mx = int(max(consistent["SeasonRank"].max(), consistent["ThreeYrRank"].max())) + 5
        fig.add_shape(type="line", x0=1, y0=1, x1=mx, y1=mx, line=dict(dash="dash", color="gray", width=1))
        fig.update_layout(height=460)
        st.plotly_chart(fig, use_container_width=True)

    st.caption(f"{len(consistent)} consistent anglers.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Eligibility
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="section-title">Division Eligibility — WCSAAA Bylaw C</div>', unsafe_allow_html=True)
    st.caption(
        "Eligibility is based on the 3-year positional ranking (50:30:20) and league classification. "
        "Blue rows = automatic selection per Bylaw C. "
        "Anglers nominate themselves; selectors use this list as input."
    )

    if not selected_divs:
        st.info("Select one or more divisions in the sidebar to view eligibility.")
    else:
        # Nomination summary across selected divisions
        nom_rows = []
        for div in selected_divs:
            cfg = DIVISIONS[div]
            elig = filt[filt[cfg["field"]].fillna(False)].sort_values(
                "ThreeYrRank" if cfg["cutoff"] else "SeasonRank"
            )
            nom_rows.append({"Division": div, "Eligible": len(elig), "Auto-Select": cfg["auto"], "Bylaw": cfg["bylaw"]})
        nom_df = pd.DataFrame(nom_rows)
        st.dataframe(nom_df, use_container_width=True, hide_index=True)

        st.divider()

        for div in selected_divs:
            cfg = DIVISIONS[div]
            field = cfg["field"]
            auto_n = cfg["auto"]

            eligible = filt[filt[field].fillna(False)].sort_values(
                "ThreeYrRank" if cfg["cutoff"] else "SeasonRank"
            ).reset_index(drop=True)

            desc_parts = []
            if cfg["cutoff"]:
                desc_parts.append(f"3-Yr Rank ≤ {cfg['cutoff']}")
            if cfg["league"]:
                desc_parts.append(f"League = {LEAGUE_MAP.get(cfg['league'], cfg['league'])}")
            desc = " & ".join(desc_parts) if desc_parts else "Age/gender category"

            with st.expander(
                f"**{div}** ({cfg['bylaw']}) — {desc} — **{len(eligible)} eligible**",
                expanded=True,
            ):
                if len(eligible) == 0:
                    st.warning("No eligible anglers match current filters.")
                    continue

                dcols = ["Angler", "Club", "League", "SeasonRank", "ThreeYrRank", "Movement", "TotalPts"]
                dcols = [c for c in dcols if c in eligible.columns]
                disp_e = eligible[dcols].copy()
                disp_e["League"] = disp_e["League"].map(lambda x: LEAGUE_MAP.get(x, x) if pd.notna(x) else "")
                disp_e.insert(0, "Auto", ["🔵 AUTO" if i < auto_n else "" for i in range(len(disp_e))])
                disp_e = disp_e.rename(columns={
                    "SeasonRank": "Season Rank",
                    "ThreeYrRank": "3-Yr Rank",
                    "TotalPts": "Season Pts",
                })
                disp_e.index = disp_e.index + 1

                def _hl_auto(row):
                    if row["Auto"] == "🔵 AUTO":
                        return ["background-color:#cce5ff;font-weight:700"] * len(row)
                    return [""] * len(row)

                st.dataframe(
                    disp_e.style.apply(_hl_auto, axis=1),
                    use_container_width=True,
                    height=min(400, 38 * len(disp_e) + 40),
                )
                st.caption(f"🔵 Blue = automatic selection (top {auto_n} per Bylaw C {cfg['bylaw']})")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — Scatter Plot
# ─────────────────────────────────────────────────────────────────────────────
with tab6:
    st.markdown('<div class="section-title">Season Rank vs 3-Year Rank</div>', unsafe_allow_html=True)
    st.caption(
        "**Above the diagonal** = 3-year rank is better than season rank (green, improved).  "
        "**Below the diagonal** = 3-year rank is worse than season rank (red, dropped).  "
        "**On the diagonal** = consistent."
    )

    scatter = both.copy()
    scatter["LeagueName"] = scatter["League"].map(lambda x: LEAGUE_MAP.get(x, x) if pd.notna(x) else "Unknown")
    scatter["MovementLabel"] = scatter["Movement"].apply(
        lambda v: f"▲ +{int(v)}" if v > 0 else (f"▼ {int(v)}" if v < 0 else "= 0")
        if pd.notna(v) else "—"
    )

    max_r = int(max(scatter["SeasonRank"].max(), scatter["ThreeYrRank"].max())) + 10

    fig_s = px.scatter(
        scatter,
        x="ThreeYrRank",
        y="SeasonRank",
        color="Movement",
        color_continuous_scale=["#c62828", "#f5f5f5", "#2e7d32"],
        color_continuous_midpoint=0,
        hover_name="Angler",
        hover_data={
            "Club": True,
            "LeagueName": True,
            "SeasonRank": True,
            "ThreeYrRank": True,
            "MovementLabel": True,
            "Movement": False,
        },
        labels={
            "ThreeYrRank": "3-Year Rank  (lower = better)",
            "SeasonRank": "Season Rank  (lower = better)",
            "LeagueName": "League",
            "MovementLabel": "Movement",
        },
        title="Season Rank vs 3-Year Rank",
        opacity=0.82,
    )

    # Diagonal reference line (y = x → no movement)
    fig_s.add_trace(go.Scatter(
        x=[1, max_r], y=[1, max_r],
        mode="lines",
        line=dict(dash="dash", color="#888", width=1),
        name="No movement (diagonal)",
        showlegend=True,
    ))

    # Division cutoff lines
    for div, cfg in DIVISIONS.items():
        if cfg["cutoff"] and div in selected_divs:
            fig_s.add_vline(
                x=cfg["cutoff"], line_dash="dot", line_color="#1a3c5e", line_width=1,
                annotation_text=f"{div} cutoff ({cfg['cutoff']})",
                annotation_position="top right",
                annotation_font_size=10,
            )

    fig_s.update_layout(height=650, coloraxis_colorbar=dict(title="Movement"))
    st.plotly_chart(fig_s, use_container_width=True)

    st.info(
        "**Vertical dotted lines** = division eligibility cutoffs (3-year rank) for selected divisions. "
        "Anglers to the **left** of a cutoff line are eligible for that division."
    )
