import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import json
from PIL import Image

from auth import require_login, logout, current_user

st.set_page_config(
    page_title="WCSAAA Ranking Dashboard",
    page_icon="🎣",
    layout="wide",
    initial_sidebar_state="expanded",
)
require_login()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
[data-testid="stMetricLabel"] { font-size: 0.8rem; color: #666; }
.badge-green  { color:#155724;background:#d4edda;padding:2px 10px;border-radius:20px;font-weight:700;font-size:.9rem; }
.badge-red    { color:#721c24;background:#f8d7da;padding:2px 10px;border-radius:20px;font-weight:700;font-size:.9rem; }
.badge-neutral{ color:#856404;background:#fff3cd;padding:2px 10px;border-radius:20px;font-weight:700;font-size:.9rem; }
.section-title{ font-size:1.15rem;font-weight:700;color:#1a3c5e;border-left:4px solid #1a3c5e;padding-left:10px;margin:1rem 0 .4rem; }
div[data-testid="stTabs"] button { font-size:.9rem;font-weight:600; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
LEAGUE_MAP = {"S":"Senior","M":"Masters","G":"Grandmasters","J":"Junior (U21)","L":"Ladies","K":"Kadet (U16)"}

DIVISIONS = {
    "Senior A":     dict(field="EligSeniorA",  cutoff=40,   league=None, auto=6, bylaw="§8.3",  team=12, reserve=1),
    "Senior B":     dict(field="EligSeniorB",  cutoff=60,   league=None, auto=4, bylaw="§8.4",  team=9,  reserve=1),
    "Development":  dict(field="EligDev",      cutoff=80,   league=None, auto=3, bylaw="§8.5",  team=6,  reserve=1),
    "Masters":      dict(field="EligMasters",  cutoff=None, league="M",  auto=4, bylaw="§8.6",  team=9,  reserve=1),
    "Grandmasters": dict(field="EligGM",       cutoff=None, league="G",  auto=2, bylaw="§8.7",  team=3,  reserve=1),
    "Ladies":       dict(field="EligLadies",   cutoff=None, league="L",  auto=2, bylaw="§8.8",  team=6,  reserve=1),
    "Junior (U21)": dict(field="EligU21",      cutoff=80,   league="J",  auto=4, bylaw="§8.9",  team=7,  reserve=1),
    "Kadet (U16)":  dict(field="EligU16",      cutoff=None, league="K",  auto=3, bylaw="§8.10", team=0,  reserve=0),
}

DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH        = os.path.join(ASSETS_DIR, "logo.png")
NOMINATIONS_PATH = os.path.join(DATA_DIR,   "nominations.json")
SELECTORS_PATH   = os.path.join(DATA_DIR,   "selectors_votes.json")
SEL_NAMES_PATH   = os.path.join(DATA_DIR,   "selector_names.json")

DEFAULT_SELECTORS = ["Selector 1", "Selector 2", "Selector 3", "Selector 4", "Selector 5"]

# ── Persistence helpers ───────────────────────────────────────────────────────
def _load(path):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except Exception: pass
    return {}

def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(data, f, indent=2)

# ── Data ──────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    s_raw = pd.read_excel(os.path.join(DATA_DIR,"season_ranking.xlsx"), sheet_name="Sheet", header=None)
    season = s_raw.iloc[2:, [0,1,2,3,28,29,30]].copy()
    season.columns = ["SeasonRank","WP_No","AnglerS","ClubS","TotalPts","SeasonPosRank","League"]
    season = season[season["SeasonRank"].notna()].reset_index(drop=True)
    for c in ["SeasonRank","TotalPts","SeasonPosRank"]:
        season[c] = pd.to_numeric(season[c], errors="coerce")
    season["WP_No"] = season["WP_No"].astype(str).str.strip()
    season["AnglerS"] = season["AnglerS"].astype(str).str.replace(r"\s+(TWO|FOUR|BLUE)$","",regex=True).str.strip()

    t_raw = pd.read_excel(os.path.join(DATA_DIR,"3year_ranking.xlsx"), sheet_name="Position", header=None)
    three = t_raw.iloc[4:, [1,2,3,4,6,7,9,10,12,13,15]].copy()
    three.columns = ["ThreeYrRank","WP_No","Angler3Yr","Club3Yr","Pts2526","PosRank2526","Pts2425","PosRank2425","Pts2324","PosRank2324","ThreeYrScore"]
    three = three[three["ThreeYrRank"].notna()].reset_index(drop=True)
    for c in ["ThreeYrRank","ThreeYrScore","Pts2526","Pts2425","Pts2324","PosRank2526","PosRank2425","PosRank2324"]:
        three[c] = pd.to_numeric(three[c], errors="coerce")
    three["WP_No"] = three["WP_No"].astype(str).str.strip()

    df = pd.merge(
        season.rename(columns={"AnglerS":"AnglerSeason","ClubS":"ClubSeason"}),
        three.rename(columns={"Angler3Yr":"Angler3Yr","Club3Yr":"Club3Yr"}),
        on="WP_No", how="outer",
    )
    df["Angler"]   = df["Angler3Yr"].combine_first(df["AnglerSeason"])
    df["Club"]     = df["Club3Yr"].combine_first(df["ClubSeason"])
    df["Movement"] = df["SeasonRank"] - df["ThreeYrRank"]

    for div, cfg in DIVISIONS.items():
        cutoff, league = cfg["cutoff"], cfg["league"]
        if cutoff and league:   df[cfg["field"]] = (df["ThreeYrRank"] <= cutoff) & (df["League"] == league)
        elif cutoff:            df[cfg["field"]] = df["ThreeYrRank"] <= cutoff
        elif league:            df[cfg["field"]] = df["League"] == league
        else:                   df[cfg["field"]] = False
    return df

df = load_data()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.caption(f"Signed in as **{current_user()}**")
    if st.button("Sign out", key="logout_home"):
        logout()
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width="stretch")
    uploaded_logo = st.file_uploader("Upload logo", type=["png","jpg","jpeg"], label_visibility="collapsed")
    if uploaded_logo:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        with open(LOGO_PATH,"wb") as _f: _f.write(uploaded_logo.read())
        st.rerun()

    st.markdown("## 🎣 WCSAAA Dashboard")
    st.caption("Position Ranking · Bylaw C Eligibility")
    st.divider()

    st.markdown("### 📋 Divisions")
    selected_divs = st.multiselect("Show divisions:", list(DIVISIONS.keys()),
                                   default=["Senior A","Senior B","Development"])

    st.markdown("### 🔍 Filters")
    clubs = sorted(df["Club"].dropna().unique())
    sel_clubs = st.multiselect("Club", clubs)
    league_opts = sorted(df["League"].dropna().unique())
    league_labels = [f"{c}  —  {LEAGUE_MAP.get(c,c)}" for c in league_opts]
    sel_league_labels = st.multiselect("League / Division", league_labels)
    sel_leagues = [x.split("  —  ")[0].strip() for x in sel_league_labels]
    only_eligible = st.checkbox("Only eligible anglers (selected divisions)", value=False)

    st.markdown("### 📊 View Mode")
    view_mode = st.radio("Display as:", ["Table","Chart"], horizontal=True)

    st.divider()
    n_season = int(df["SeasonRank"].notna().sum())
    n_3yr    = int(df["ThreeYrRank"].notna().sum())
    n_both   = int((df["SeasonRank"].notna() & df["ThreeYrRank"].notna()).sum())
    st.caption(f"Season: **{n_season}** anglers  \n3-Year: **{n_3yr}** anglers  \nIn both: **{n_both}** anglers")

# ── Filter ────────────────────────────────────────────────────────────────────
filt = df.copy()
if sel_clubs:   filt = filt[filt["Club"].isin(sel_clubs)]
if sel_leagues: filt = filt[filt["League"].isin(sel_leagues)]
if only_eligible and selected_divs:
    mask = pd.Series(False, index=filt.index)
    for d in selected_divs: mask |= filt[DIVISIONS[d]["field"]].fillna(False)
    filt = filt[mask]

both = filt[filt["SeasonRank"].notna() & filt["ThreeYrRank"].notna()].copy().sort_values("Movement", ascending=False).reset_index(drop=True)

# ── Header ────────────────────────────────────────────────────────────────────
if os.path.exists(LOGO_PATH):
    _c1,_c2,_c3 = st.columns([1,2,1])
    with _c2: st.image(LOGO_PATH, width="stretch")

st.markdown(
    "<h1 style='text-align:center;color:#1a3c5e;'>🎣 WCSAAA Position Ranking Dashboard</h1>"
    "<p style='text-align:center;color:#666;margin-top:-8px;'>"
    "2025/26 Season vs 3-Year (50:30:20) Weighted Ranking · Selection Criteria per Bylaw C</p>",
    unsafe_allow_html=True,
)

k1,k2,k3,k4,k5 = st.columns(5)
k1.metric("Matched Anglers", len(both))
k2.metric("▲ Improved (3-Yr)",  int((both["Movement"]>0).sum()))
k3.metric("▼ Dropped (3-Yr)",   int((both["Movement"]<0).sum()))
k4.metric("≈ Consistent (±1)",  int(both["Movement"].between(-1,1).sum()))
avg_mv = both["Movement"].mean() if len(both) else float("nan")
k5.metric("Avg Movement", f"{avg_mv:+.1f}" if not pd.isna(avg_mv) else "—")
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8 = st.tabs([
    "📊 Movement Leaderboard",
    "🏆 Top 10 Most Improved",
    "📉 Top 10 Biggest Drops",
    "🎯 Consistency",
    "✅ Eligibility",
    "📋 Nominations",
    "🗳️ Selectors",
    "📈 Scatter Plot",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Movement Leaderboard
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-title">Movement Leaderboard</div>', unsafe_allow_html=True)
    st.caption("Movement = Season Rank − 3-Year Rank. **Green** = 3-yr rank better · **Red** = 3-yr rank worse.")

    disp = both[["Angler","Club","League","SeasonRank","ThreeYrRank","Movement","TotalPts"]].copy()
    disp["League"] = disp["League"].map(lambda x: LEAGUE_MAP.get(x,x) if pd.notna(x) else "")
    disp = disp.rename(columns={"SeasonRank":"Season Rank","ThreeYrRank":"3-Yr Rank","TotalPts":"Season Pts"})

    if view_mode == "Table":
        def _color_movement(val):
            if pd.isna(val): return ""
            if val > 0: return "background-color:#d4edda;color:#155724;font-weight:700"
            if val < 0: return "background-color:#f8d7da;color:#721c24;font-weight:700"
            return "background-color:#fff3cd;color:#856404;font-weight:700"
        st.dataframe(disp.style.map(_color_movement, subset=["Movement"]), width='stretch', height=520)
    else:
        chart_df = both.nlargest(80,"Movement") if len(both)>80 else both
        fig = px.bar(chart_df, x="Angler", y="Movement", color="Movement",
                     color_continuous_scale=["#d32f2f","#f5f5f5","#2e7d32"], color_continuous_midpoint=0,
                     labels={"Movement":"Movement (+ = improved)","Angler":""},
                     title=f"Movement per Angler — top {len(chart_df)}",
                     hover_data=["Club","SeasonRank","ThreeYrRank"])
        fig.update_layout(xaxis_tickangle=-50, height=500, coloraxis_showscale=False)
        st.plotly_chart(fig, width='stretch')

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Top 10 Most Improved
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-title">Top 10 Most Improved</div>', unsafe_allow_html=True)
    st.caption("Highest positive movement — 3-year rank significantly better than current season rank.")
    top10 = both.nlargest(10,"Movement")
    for i,row in enumerate(top10.itertuples(),1):
        lg = LEAGUE_MAP.get(row.League, row.League or "")
        c1,c2,c3,c4 = st.columns([0.4,3.2,2.2,1.8])
        c1.markdown(f"**#{i}**")
        c2.markdown(f"**{row.Angler}**  \n<small>{row.Club or ''} · {lg}</small>", unsafe_allow_html=True)
        c3.markdown(f"Season **{int(row.SeasonRank)}** → 3-Yr **{int(row.ThreeYrRank)}**")
        c4.markdown(f"<span class='badge-green'>▲ +{int(row.Movement)}</span>", unsafe_allow_html=True)
    if view_mode == "Chart":
        fig = px.bar(top10, x="Movement", y="Angler", orientation="h",
                     color_discrete_sequence=["#2e7d32"], text="Movement",
                     labels={"Movement":"Movement (+)","Angler":""})
        fig.update_traces(texttemplate="+%{text}", textposition="outside")
        fig.update_layout(height=380, yaxis=dict(autorange="reversed"), margin=dict(l=160))
        st.plotly_chart(fig, width='stretch')

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Top 10 Biggest Drops
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-title">Top 10 Biggest Drops</div>', unsafe_allow_html=True)
    st.caption("Largest negative movement — strong this season but weaker historically.")
    bot10 = both.nsmallest(10,"Movement")
    for i,row in enumerate(bot10.itertuples(),1):
        lg = LEAGUE_MAP.get(row.League, row.League or "")
        c1,c2,c3,c4 = st.columns([0.4,3.2,2.2,1.8])
        c1.markdown(f"**#{i}**")
        c2.markdown(f"**{row.Angler}**  \n<small>{row.Club or ''} · {lg}</small>", unsafe_allow_html=True)
        c3.markdown(f"Season **{int(row.SeasonRank)}** → 3-Yr **{int(row.ThreeYrRank)}**")
        c4.markdown(f"<span class='badge-red'>▼ {int(row.Movement)}</span>", unsafe_allow_html=True)
    if view_mode == "Chart":
        fig = px.bar(bot10, x="Movement", y="Angler", orientation="h",
                     color_discrete_sequence=["#c62828"], text="Movement",
                     labels={"Movement":"Movement (−)","Angler":""})
        fig.update_traces(texttemplate="%{text}", textposition="outside")
        fig.update_layout(height=380, yaxis=dict(autorange="reversed"), margin=dict(l=160))
        st.plotly_chart(fig, width='stretch')

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Consistency
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-title">Consistent Anglers  (Movement −1 to +1)</div>', unsafe_allow_html=True)
    st.caption("Anglers whose ranking is stable across both the season and the 3-year system.")
    consistent = both[both["Movement"].between(-1,1)].sort_values("ThreeYrRank").reset_index(drop=True)
    disp_c = consistent[["Angler","Club","League","SeasonRank","ThreeYrRank","Movement","TotalPts"]].copy()
    disp_c["League"] = disp_c["League"].map(lambda x: LEAGUE_MAP.get(x,x) if pd.notna(x) else "")
    disp_c = disp_c.rename(columns={"SeasonRank":"Season Rank","ThreeYrRank":"3-Yr Rank","TotalPts":"Season Pts"})
    disp_c.index = disp_c.index + 1
    if view_mode == "Table":
        st.dataframe(disp_c.style.map(lambda v:"background-color:#fff3cd;color:#856404;font-weight:700", subset=["Movement"]),
                     width='stretch', height=460)
    else:
        fig = px.scatter(consistent, x="ThreeYrRank", y="SeasonRank",
                         color_discrete_sequence=["#f0a500"], hover_data=["Angler","Club"],
                         labels={"ThreeYrRank":"3-Year Rank","SeasonRank":"Season Rank"},
                         title="Consistent Anglers — near the diagonal")
        mx = int(max(consistent["SeasonRank"].max(), consistent["ThreeYrRank"].max())) + 5
        fig.add_shape(type="line", x0=1, y0=1, x1=mx, y1=mx, line=dict(dash="dash",color="gray",width=1))
        fig.update_layout(height=460)
        st.plotly_chart(fig, width='stretch')
    st.caption(f"{len(consistent)} consistent anglers.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Eligibility
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="section-title">Division Eligibility — WCSAAA Bylaw C</div>', unsafe_allow_html=True)
    st.caption("Blue rows = automatic selection. Eligibility based on 3-year positional ranking (50:30:20) and league code.")

    if not selected_divs:
        st.info("Select one or more divisions in the sidebar.")
    else:
        summary = []
        for div in selected_divs:
            cfg = DIVISIONS[div]
            elig = filt[filt[cfg["field"]].fillna(False)]
            summary.append({"Division":div,"Eligible":len(elig),"Auto-Select":cfg["auto"],"Team":cfg["team"],"Reserve":cfg["reserve"],"Bylaw":cfg["bylaw"]})
        st.dataframe(pd.DataFrame(summary), width='stretch', hide_index=True)
        st.divider()

        for div in selected_divs:
            cfg = DIVISIONS[div]
            auto_n = cfg["auto"]
            sort_col = "ThreeYrRank" if cfg["cutoff"] else "SeasonRank"
            eligible = filt[filt[cfg["field"]].fillna(False)].sort_values(sort_col).reset_index(drop=True)

            desc_parts = []
            if cfg["cutoff"]: desc_parts.append(f"3-Yr Rank ≤ {cfg['cutoff']}")
            if cfg["league"]: desc_parts.append(f"League = {LEAGUE_MAP.get(cfg['league'],cfg['league'])}")
            desc = " & ".join(desc_parts) if desc_parts else "Age/gender category"

            with st.expander(f"**{div}** ({cfg['bylaw']}) — {desc} — **{len(eligible)} eligible**", expanded=True):
                if not len(eligible):
                    st.warning("No eligible anglers match current filters.")
                    continue
                dcols = [c for c in ["Angler","Club","League","SeasonRank","ThreeYrRank","Movement","TotalPts"] if c in eligible.columns]
                disp_e = eligible[dcols].copy()
                disp_e["League"] = disp_e["League"].map(lambda x: LEAGUE_MAP.get(x,x) if pd.notna(x) else "")
                disp_e.insert(0,"Auto",["🔵 AUTO" if i < auto_n else "" for i in range(len(disp_e))])
                disp_e = disp_e.rename(columns={"SeasonRank":"Season Rank","ThreeYrRank":"3-Yr Rank","TotalPts":"Season Pts"})
                disp_e.index = disp_e.index + 1

                def _hl_auto(row):
                    return (["background-color:#cce5ff;font-weight:700"]*len(row) if row["Auto"]=="🔵 AUTO" else [""]*len(row))

                st.dataframe(disp_e.style.apply(_hl_auto, axis=1), width='stretch', height=min(400,38*len(disp_e)+40))
                st.caption(f"🔵 Auto-selected: top {auto_n} per Bylaw C {cfg['bylaw']}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — Nominations
# ─────────────────────────────────────────────────────────────────────────────
with tab6:
    st.markdown('<div class="section-title">Nominations Tick Sheet</div>', unsafe_allow_html=True)

    if not selected_divs:
        st.info("Select one or more divisions in the sidebar.")
    else:
        if "nominations" not in st.session_state:
            st.session_state.nominations = _load(NOMINATIONS_PATH)

        # ── Summary ────────────────────────────────────────────────────────
        summ = []
        for div in selected_divs:
            cfg     = DIVISIONS[div]
            elig_wp = set(df[df[cfg["field"]].fillna(False)]["WP_No"].tolist())
            saved   = [wp for wp in st.session_state.nominations.get(div,[]) if wp in elig_wp]
            summ.append({"Division":div,"Eligible":len(elig_wp),"Nominated":len(saved),"Still to nominate":len(elig_wp)-len(saved)})
        st.dataframe(pd.DataFrame(summ), width='stretch', hide_index=True)
        st.divider()

        # ── Mode toggle ────────────────────────────────────────────────────
        nom_mode = st.radio(
            "Entry mode:",
            ["By Angler — tick multiple divisions per row", "By Division — one division at a time"],
            horizontal=True, key="nom_mode",
        )

        # ══════════════════════════════════════════════════════════════════
        # MODE A — By Angler (multi-division matrix)
        # ══════════════════════════════════════════════════════════════════
        if nom_mode.startswith("By Angler"):
            st.caption(
                "Rows = anglers eligible for **at least one** selected division. "
                "Tick every division the angler has nominated for. "
                "Only eligible combinations are editable — grey cells = not eligible for that division. "
                "Click **💾 Save All** when done."
            )

            # Collect all anglers eligible for any selected division
            all_wp = set()
            elig_per_div = {}
            for div in selected_divs:
                cfg = DIVISIONS[div]
                wp_set = set(df[df[cfg["field"]].fillna(False)]["WP_No"].tolist())
                elig_per_div[div] = wp_set
                all_wp |= wp_set

            if not all_wp:
                st.warning("No eligible anglers found for the selected divisions.")
            else:
                # Base angler info — sort by 3-yr rank
                base = (
                    df[df["WP_No"].isin(all_wp)]
                    .drop_duplicates("WP_No")
                    .sort_values("ThreeYrRank", na_position="last")
                    .reset_index(drop=True)
                )

                # Build matrix dataframe
                matrix = {
                    "Angler":      base["Angler"].fillna("").values,
                    "WP #":        base["WP_No"].values,
                    "Club":        base["Club"].fillna("").values,
                    "3-Yr Rank":   base["ThreeYrRank"].apply(lambda x: int(x) if pd.notna(x) else "").values,
                }
                for div in selected_divs:
                    saved_div = set(st.session_state.nominations.get(div, []))
                    # True = nominated; False = not yet; None-ish for ineligible (we use False + note)
                    matrix[div] = [
                        (wp in saved_div) if wp in elig_per_div[div] else False
                        for wp in base["WP_No"]
                    ]

                matrix_df = pd.DataFrame(matrix)

                # Column config — division cols are checkboxes; ineligible cells stay False
                col_cfg = {
                    "Angler":    st.column_config.TextColumn("Angler",   disabled=True),
                    "WP #":      st.column_config.TextColumn("WP #",     disabled=True, width="small"),
                    "Club":      st.column_config.TextColumn("Club",     disabled=True),
                    "3-Yr Rank": st.column_config.NumberColumn("3-Yr Rank", disabled=True, width="small"),
                }
                for div in selected_divs:
                    col_cfg[div] = st.column_config.CheckboxColumn(div, default=False)

                edited_matrix = st.data_editor(
                    matrix_df,
                    column_config=col_cfg,
                    hide_index=True,
                    width='stretch',
                    height=min(700, 38*len(matrix_df)+60),
                    key="nom_matrix",
                )

                c_save, c_clear, c_note = st.columns([1, 1, 5])
                if c_save.button("💾 Save All", key="save_matrix"):
                    for div in selected_divs:
                        # Only save if angler is actually eligible for that div
                        ticked = [
                            base["WP_No"].iloc[i]
                            for i, v in enumerate(edited_matrix[div].values)
                            if v and base["WP_No"].iloc[i] in elig_per_div[div]
                        ]
                        st.session_state.nominations[div] = ticked
                    _save(NOMINATIONS_PATH, st.session_state.nominations)
                    total = sum(len(st.session_state.nominations.get(d,[])) for d in selected_divs)
                    st.success(f"Saved — {total} nominations across {len(selected_divs)} division(s).")
                if c_clear.button("🗑 Clear All", key="clear_matrix"):
                    for div in selected_divs:
                        st.session_state.nominations[div] = []
                    _save(NOMINATIONS_PATH, st.session_state.nominations)
                    st.rerun()
                c_note.caption("Ticking a division where the angler is ineligible has no effect — it will not be saved.")

        # ══════════════════════════════════════════════════════════════════
        # MODE B — By Division (one expander per division)
        # ══════════════════════════════════════════════════════════════════
        else:
            st.caption("Tick each angler who has submitted a nomination for that division. Click **💾 Save** per division.")

            for div in selected_divs:
                cfg      = DIVISIONS[div]
                sort_col = "ThreeYrRank" if cfg["cutoff"] else "SeasonRank"
                eligible = df[df[cfg["field"]].fillna(False)].sort_values(sort_col).reset_index(drop=True)

                if not len(eligible):
                    with st.expander(f"**{div}** — no eligible anglers", expanded=False):
                        st.warning("No eligible anglers found.")
                    continue

                saved_wp = set(st.session_state.nominations.get(div, []))

                with st.expander(
                    f"**{div}** ({cfg['bylaw']}) — "
                    f"{len([w for w in eligible['WP_No'] if w in saved_wp])} / {len(eligible)} nominated",
                    expanded=True,
                ):
                    tick_df = pd.DataFrame({
                        "Nominated":   [wp in saved_wp for wp in eligible["WP_No"]],
                        "Angler":      eligible["Angler"].fillna("").values,
                        "WP #":        eligible["WP_No"].values,
                        "Club":        eligible["Club"].fillna("").values,
                        "3-Yr Rank":   eligible[sort_col].apply(lambda x: int(x) if pd.notna(x) else "").values,
                        "Season Rank": eligible["SeasonRank"].apply(lambda x: int(x) if pd.notna(x) else "").values,
                    })

                    edited = st.data_editor(
                        tick_df,
                        column_config={
                            "Nominated":   st.column_config.CheckboxColumn("✓ Nominated", default=False, width="small"),
                            "Angler":      st.column_config.TextColumn("Angler",      disabled=True),
                            "WP #":        st.column_config.TextColumn("WP #",        disabled=True, width="small"),
                            "Club":        st.column_config.TextColumn("Club",        disabled=True),
                            "3-Yr Rank":   st.column_config.NumberColumn("3-Yr Rank",   disabled=True, width="small"),
                            "Season Rank": st.column_config.NumberColumn("Season Rank", disabled=True, width="small"),
                        },
                        hide_index=True,
                        width='stretch',
                        height=min(600, 38*len(tick_df)+60),
                        key=f"tick_{div}",
                    )

                    cs, cc, ci = st.columns([1, 1, 5])
                    if cs.button("💾 Save", key=f"savenom_{div}"):
                        nominated_wp = eligible["WP_No"][edited["Nominated"].values].tolist()
                        st.session_state.nominations[div] = nominated_wp
                        _save(NOMINATIONS_PATH, st.session_state.nominations)
                        st.success(f"Saved — {len(nominated_wp)} nominations for {div}.")
                    if cc.button("🗑 Clear", key=f"clearnom_{div}"):
                        st.session_state.nominations[div] = []
                        _save(NOMINATIONS_PATH, st.session_state.nominations)
                        st.rerun()
                    ci.caption("Tick each angler who has submitted their nomination, then hit 💾 Save.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 7 — Selectors  (5 selectors vote on remaining spots)
# ─────────────────────────────────────────────────────────────────────────────
with tab7:
    st.markdown('<div class="section-title">Selectors Panel</div>', unsafe_allow_html=True)
    st.caption(
        "Each selector independently votes on the remaining spots after auto-selection. "
        "Votes are saved per selector. The tally shows how many selectors chose each angler."
    )

    if not selected_divs:
        st.info("Select one or more divisions in the sidebar.")
    else:
        # ── Load persistent data ───────────────────────────────────────────
        if "nominations" not in st.session_state:
            st.session_state.nominations = _load(NOMINATIONS_PATH)
        if "sel_votes" not in st.session_state:
            st.session_state.sel_votes = _load(SELECTORS_PATH)
        if "sel_names" not in st.session_state:
            stored = _load(SEL_NAMES_PATH)
            st.session_state.sel_names = stored.get("names", DEFAULT_SELECTORS[:])

        # ── Configure selector names ───────────────────────────────────────
        with st.expander("⚙️ Configure selector names", expanded=False):
            st.caption("Set the names of the 5 selectors. Click Save Names when done.")
            name_cols = st.columns(5)
            new_names = [
                name_cols[i].text_input(f"Selector {i+1}", value=st.session_state.sel_names[i], key=f"selname_{i}")
                for i in range(5)
            ]
            if st.button("💾 Save Names"):
                st.session_state.sel_names = new_names
                _save(SEL_NAMES_PATH, {"names": new_names})
                st.success("Selector names saved.")

        SELECTOR_NAMES = st.session_state.sel_names
        st.divider()

        # ── Selector identity ──────────────────────────────────────────────
        current_selector = st.selectbox(
            "**I am:**",
            SELECTOR_NAMES,
            help="Choose your name to record your votes.",
        )
        st.divider()

        # ── Per-division voting ────────────────────────────────────────────
        for div in selected_divs:
            cfg      = DIVISIONS[div]
            sort_col = "ThreeYrRank" if cfg["cutoff"] else "SeasonRank"
            auto_n   = cfg["auto"]
            team_sz  = cfg["team"]
            reserve  = cfg["reserve"]

            # All eligible anglers for this division (from full df, ignoring sidebar filters)
            eligible = df[df[cfg["field"]].fillna(False)].sort_values(sort_col).reset_index(drop=True)
            if not len(eligible):
                continue

            # Only nominated anglers
            elig_wp   = set(eligible["WP_No"].tolist())
            saved_noms = [wp for wp in st.session_state.nominations.get(div,[]) if wp in elig_wp]

            # Split into auto-selected and remaining nominees
            nominated_elig = eligible[eligible["WP_No"].isin(saved_noms)].sort_values(sort_col).reset_index(drop=True)
            auto_rows      = nominated_elig.iloc[:auto_n]
            remaining      = nominated_elig.iloc[auto_n:].reset_index(drop=True)

            selector_spots = max(0, team_sz - auto_n) if team_sz else None
            spots_label    = f" — selectors fill **{selector_spots}** spot(s) + **{reserve}** reserve" if selector_spots else ""

            with st.expander(
                f"**{div}** ({cfg['bylaw']}) — {len(saved_noms)} nominees{spots_label}",
                expanded=True,
            ):
                if not len(saved_noms):
                    st.warning("No nominations recorded for this division yet. Go to the Nominations tab first.")
                    continue

                # Auto-selected (locked)
                st.markdown("**🔵 Auto-selected** (locked — top by 3-year rank):")
                if len(auto_rows):
                    auto_disp = auto_rows[["Angler","WP_No","Club","SeasonRank","ThreeYrRank"]].copy()
                    auto_disp.columns = ["Angler","WP #","Club","Season Rank","3-Yr Rank"]
                    auto_disp.index   = auto_disp.index + 1
                    st.dataframe(
                        auto_disp.style.apply(lambda r: ["background-color:#cce5ff;font-weight:700"]*len(r), axis=1),
                        width='stretch', height=min(300, 38*len(auto_disp)+40), hide_index=False,
                    )
                else:
                    st.info("No auto-selected anglers yet (not enough nominations).")

                if not len(remaining):
                    st.info("No remaining nominees for selectors to vote on.")
                    continue

                st.markdown(f"**⚪ Remaining nominees** — selectors vote:")

                # Current votes for this selector on this division
                my_votes = set(st.session_state.sel_votes.get(div,{}).get(current_selector,[]))

                vote_df = pd.DataFrame({
                    "Vote": [wp in my_votes for wp in remaining["WP_No"]],
                    "Angler":      remaining["Angler"].fillna("").values,
                    "WP #":        remaining["WP_No"].values,
                    "Club":        remaining["Club"].fillna("").values,
                    "3-Yr Rank":   remaining[sort_col].apply(lambda x: int(x) if pd.notna(x) else "").values,
                    "Season Rank": remaining["SeasonRank"].apply(lambda x: int(x) if pd.notna(x) else "").values,
                })

                voted_df = st.data_editor(
                    vote_df,
                    column_config={
                        "Vote":       st.column_config.CheckboxColumn("✓ Select", default=False, width="small"),
                        "Angler":     st.column_config.TextColumn("Angler",     disabled=True),
                        "WP #":       st.column_config.TextColumn("WP #",       disabled=True, width="small"),
                        "Club":       st.column_config.TextColumn("Club",       disabled=True),
                        "3-Yr Rank":  st.column_config.NumberColumn("3-Yr Rank",  disabled=True, width="small"),
                        "Season Rank":st.column_config.NumberColumn("Season Rank",disabled=True, width="small"),
                    },
                    hide_index=True,
                    width='stretch',
                    height=min(500, 38*len(vote_df)+60),
                    key=f"vote_{div}_{current_selector}",
                )

                if st.button(f"💾 Save my votes for {div}", key=f"savevote_{div}_{current_selector}"):
                    chosen = remaining["WP_No"][voted_df["Vote"].values].tolist()
                    if div not in st.session_state.sel_votes:
                        st.session_state.sel_votes[div] = {}
                    st.session_state.sel_votes[div][current_selector] = chosen
                    _save(SELECTORS_PATH, st.session_state.sel_votes)
                    st.success(f"{current_selector} voted for {len(chosen)} angler(s) in {div}.")

                # ── Tally ──────────────────────────────────────────────────
                st.divider()
                st.markdown("**📊 Vote Tally — all selectors:**")

                tally_rows = []
                for _, row in remaining.iterrows():
                    wp = row["WP_No"]
                    votes_for = [s for s in SELECTOR_NAMES if wp in st.session_state.sel_votes.get(div,{}).get(s,[])]
                    n_votes = len(votes_for)
                    if n_votes == 5:   status = "✅ Unanimous"
                    elif n_votes >= 3: status = "🟢 Majority"
                    elif n_votes >= 1: status = "🟡 Minority"
                    else:              status = "—"
                    tally_rows.append({
                        "Angler":    row["Angler"],
                        "WP #":      wp,
                        "Club":      row["Club"] if pd.notna(row["Club"]) else "",
                        "3-Yr Rank": int(row[sort_col]) if pd.notna(row[sort_col]) else "—",
                        "Votes":     n_votes,
                        "Status":    status,
                        "Voted by":  ", ".join(votes_for) if votes_for else "—",
                    })

                tally_df = pd.DataFrame(tally_rows).sort_values("Votes", ascending=False).reset_index(drop=True)

                def _hl_tally(row):
                    if row["Status"] == "✅ Unanimous":  return ["background-color:#d4edda;font-weight:700"]*len(row)
                    if row["Status"] == "🟢 Majority":   return ["background-color:#d1ecf1"]*len(row)
                    if row["Status"] == "🟡 Minority":   return ["background-color:#fff3cd"]*len(row)
                    return [""]*len(row)

                st.dataframe(
                    tally_df.style.apply(_hl_tally, axis=1),
                    width='stretch',
                    height=min(500, 38*len(tally_df)+60),
                    hide_index=True,
                )

                # Who has voted / not voted
                voted_selectors    = [s for s in SELECTOR_NAMES if st.session_state.sel_votes.get(div,{}).get(s) is not None]
                not_voted_yet      = [s for s in SELECTOR_NAMES if s not in voted_selectors]
                st.caption(
                    f"**Voted:** {', '.join(voted_selectors) if voted_selectors else 'none yet'}  |  "
                    f"**Still to vote:** {', '.join(not_voted_yet) if not_voted_yet else '✅ all done'}"
                )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 8 — Scatter Plot
# ─────────────────────────────────────────────────────────────────────────────
with tab8:
    st.markdown('<div class="section-title">Season Rank vs 3-Year Rank</div>', unsafe_allow_html=True)
    st.caption("**Above diagonal** = 3-yr rank better · **Below diagonal** = 3-yr rank worse · **On diagonal** = consistent.")

    scatter = both.copy()
    scatter["LeagueName"]    = scatter["League"].map(lambda x: LEAGUE_MAP.get(x,x) if pd.notna(x) else "Unknown")
    scatter["MovementLabel"] = scatter["Movement"].apply(
        lambda v: f"▲ +{int(v)}" if v>0 else (f"▼ {int(v)}" if v<0 else "= 0") if pd.notna(v) else "—"
    )
    max_r = int(max(scatter["SeasonRank"].max(), scatter["ThreeYrRank"].max())) + 10

    fig_s = px.scatter(scatter, x="ThreeYrRank", y="SeasonRank", color="Movement",
                       color_continuous_scale=["#c62828","#f5f5f5","#2e7d32"], color_continuous_midpoint=0,
                       hover_name="Angler",
                       hover_data={"Club":True,"LeagueName":True,"SeasonRank":True,"ThreeYrRank":True,"MovementLabel":True,"Movement":False},
                       labels={"ThreeYrRank":"3-Year Rank  (lower = better)","SeasonRank":"Season Rank  (lower = better)","LeagueName":"League","MovementLabel":"Movement"},
                       title="Season Rank vs 3-Year Rank", opacity=0.82)
    fig_s.add_trace(go.Scatter(x=[1,max_r], y=[1,max_r], mode="lines",
                               line=dict(dash="dash",color="#888",width=1),
                               name="No movement (diagonal)", showlegend=True))
    for div, cfg in DIVISIONS.items():
        if cfg["cutoff"] and div in selected_divs:
            fig_s.add_vline(x=cfg["cutoff"], line_dash="dot", line_color="#1a3c5e", line_width=1,
                            annotation_text=f"{div} cutoff ({cfg['cutoff']})",
                            annotation_position="top right", annotation_font_size=10)
    fig_s.update_layout(height=650, coloraxis_colorbar=dict(title="Movement"))
    st.plotly_chart(fig_s, width='stretch')
    st.info("**Vertical dotted lines** = division eligibility cutoffs for selected divisions. Anglers to the **left** are eligible.")
