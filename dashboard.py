from __future__ import annotations

import html
import sys
from pathlib import Path

import folium
from folium.plugins import MarkerCluster
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from dashboard_data import (
    get_candidate_votes,
    get_filter_labels,
    get_map_points,
    get_site_detail,
    get_summary,
    open_data,
)


st.set_page_config(page_title="Ceará 2026 · Resultados", page_icon="◉", layout="wide")

st.markdown(
    """<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root { --ink:var(--text-color); --muted:color-mix(in srgb,var(--text-color) 68%,transparent); --line:var(--border-color); --card:var(--secondary-background-color); --accent:var(--primary-color); }
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--text-color); }
    .stApp { background:var(--background-color); color:var(--text-color); }
    [data-testid="stSidebar"] { background:var(--secondary-background-color); border-right:1px solid var(--border-color); }
    [data-testid="stSidebar"] > div { padding-top:1.2rem; }
    h1,h2,h3,h4 { font-family:'Manrope',sans-serif; letter-spacing:-.035em; color:var(--text-color) !important; }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { margin:0; }
    .hero { background:linear-gradient(112deg,#103d43 0%,#116d68 62%,#218b7e 100%); color:#fff; padding:28px 34px; border-radius:18px; margin:4px 0 22px; box-shadow:0 12px 28px #164f4a22; position:relative; overflow:hidden; }
    .hero:after { content:'CE'; position:absolute; right:30px; top:-47px; font:800 190px Manrope,sans-serif; color:#ffffff0d; }
    .hero small { text-transform:uppercase; letter-spacing:.16em; font-weight:700; color:#bfe8df; }
    .hero h1 { color:white; margin:7px 0 4px; font-size:34px; }
    .hero p { margin:0; color:#d8eeea; }
    .metric { background:var(--secondary-background-color); color:var(--text-color); border:1px solid var(--border-color); border-radius:14px; padding:17px 19px; min-height:105px; box-shadow:0 3px 12px #193c4010; }
    .metric-label { color:var(--muted); font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; }
    .metric-value { font:800 25px Manrope,sans-serif; margin-top:10px; color:var(--text-color); }
    .section-head { margin:23px 0 10px; }
    .section-head h3 { margin:0; font-size:19px; }
    .section-head p { color:var(--muted); margin:3px 0 0; font-size:13px; }
    .panel { background:var(--secondary-background-color); border:1px solid var(--border-color); border-radius:15px; padding:18px 20px; }
    div[data-testid="stPlotlyChart"] { background:var(--secondary-background-color); border:1px solid var(--border-color); border-radius:15px; padding:8px; }
    .site-card { background:var(--secondary-background-color); color:var(--text-color); border:1px solid var(--border-color); border-left:4px solid var(--primary-color); border-radius:12px; padding:14px 17px; margin:8px 0 14px; }
    .site-card strong { font:700 16px Manrope,sans-serif; }
    .site-card span { color:var(--muted); font-size:13px; }
    .filter-group { margin:16px 0 9px; padding:9px 11px; border-left:3px solid var(--primary-color); background:var(--background-color); border-radius:0 8px 8px 0; color:var(--text-color); font:700 12px Manrope,sans-serif; text-transform:uppercase; letter-spacing:.1em; }
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color:var(--text-color) !important; font-weight:600; }
    [data-testid="stSidebar"] [data-baseweb="select"] > div { background:var(--background-color); border-color:var(--border-color); color:var(--text-color); }
    [data-testid="stSidebar"] input { color:var(--text-color); }
    [data-testid="stMetric"] { background:var(--secondary-background-color); border:1px solid var(--border-color); border-radius:13px; padding:14px 17px; }
    @media (prefers-color-scheme: dark) { .hero { box-shadow:0 12px 35px #0005; } }
    </style>""",
    unsafe_allow_html=True,
)

def resource_root() -> Path:
    """Return project root in development or PyInstaller's onedir resource root."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


DATA_PATH = resource_root() / "data" / "ce_votos.parquet"


def fmt(value: object) -> str:
    try:
        if pd.isna(value):
            return "—"
        return f"{int(float(value)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def safe_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return html.escape(str(value), quote=True)


if not DATA_PATH.exists():
    st.markdown('<div class="hero"><small>Painel executivo · Ceará</small><h1>Eleições 2026</h1><p>Resultados oficiais, com leitura clara para cada território.</p></div>', unsafe_allow_html=True)
    st.error(f"Base de dados não encontrada em `{DATA_PATH.relative_to(Path(__file__).parent)}`.")
    st.info("Para preparar os dados, execute `python prepare_ce_data.py /caminho/para/bweb_1t_CE.csv --download-localities` na pasta do projeto e abra este painel novamente.")
    st.stop()


@st.cache_resource(show_spinner="Abrindo a base eleitoral…")
def connect(path: str):
    return open_data(path)


con = connect(str(DATA_PATH))
st.markdown('<div class="hero"><small>Painel executivo · Ceará</small><h1>Eleições 2026</h1><p>Um retrato dos votos e dos locais de votação no estado.</p></div>', unsafe_allow_html=True)

# On a changed ancestor, clear descendants before their widgets are instantiated.
territory_keys = ["municipio", "zona", "local", "secao"]
for idx, key in enumerate(territory_keys):
    widget_key = f"territory_{key}"
    previous_key = f"_previous_{widget_key}"
    current = st.session_state.get(widget_key)
    if previous_key in st.session_state and st.session_state[previous_key] != current:
        for descendant in territory_keys[idx + 1:]:
            st.session_state[f"territory_{descendant}"] = None
        st.session_state["selected_site_id"] = None
    st.session_state[previous_key] = current

if st.session_state.get("_previous_cargo", st.session_state.get("cargo")) != st.session_state.get("cargo"):
    st.session_state["partido"] = None
    st.session_state["candidato"] = None
    st.session_state["selected_site_id"] = None
if st.session_state.get("_previous_partido", st.session_state.get("partido")) != st.session_state.get("partido"):
    st.session_state["candidato"] = None
    st.session_state["selected_site_id"] = None
st.session_state["_previous_cargo"] = st.session_state.get("cargo")
st.session_state["_previous_partido"] = st.session_state.get("partido")


def clear_dashboard_filters() -> None:
    for key in ["territory_municipio", "territory_zona", "territory_local", "territory_secao", "cargo", "partido", "candidato"]:
        st.session_state[key] = None
    st.session_state["selected_site_id"] = None
    for key in ["_previous_territory_municipio", "_previous_territory_zona", "_previous_territory_local", "_previous_territory_secao", "_previous_cargo", "_previous_partido"]:
        st.session_state[key] = None

with st.sidebar:
    st.markdown("### Recorte da análise")
    st.caption("Escolha um recorte. Os filtros abaixo acompanham suas seleções.")
    st.markdown('<div class="filter-group">01 · Geografia</div>', unsafe_allow_html=True)
    territorial: dict[str, object] = {}
    for key, title in [("municipio", "Município"), ("zona", "Zona eleitoral"), ("local", "Local / escola"), ("secao", "Seção")]:
        labels = get_filter_labels(con, territorial, keys=[key]).get(key, {})
        widget_key = f"territory_{key}"
        if st.session_state.get(widget_key) not in [None, *labels.keys()]:
            st.session_state[widget_key] = None
        selected = st.selectbox(title, [None, *labels.keys()], key=widget_key,
                                format_func=lambda value, labels=labels: "Todos" if value is None else labels.get(value, str(value)))
        if selected is not None:
            territorial[key] = selected
    st.divider()
    st.markdown('<div class="filter-group">02 · Votação</div>', unsafe_allow_html=True)
    labels = get_filter_labels(con, territorial, keys=["cargo"]).get("cargo", {})
    if st.session_state.get("cargo") not in [None, *labels.keys()]:
        st.session_state["cargo"] = None
    cargo = st.selectbox("Cargo", [None, *labels.keys()], key="cargo",
                         format_func=lambda value, labels=labels: "Todos" if value is None else labels.get(value, str(value)))
    filters = dict(territorial)
    if cargo is not None:
        filters["cargo"] = cargo
    labels = get_filter_labels(con, filters, keys=["partido"]).get("partido", {})
    if st.session_state.get("partido") not in [None, *labels.keys()]:
        st.session_state["partido"] = None
    partido = st.selectbox("Partido", [None, *labels.keys()], key="partido",
                           format_func=lambda value, labels=labels: "Todos" if value is None else labels.get(value, str(value)))
    if partido is not None:
        filters["partido"] = partido
    labels = get_filter_labels(con, filters, keys=["candidato"]).get("candidato", {})
    if st.session_state.get("candidato") not in [None, *labels.keys()]:
        st.session_state["candidato"] = None
    # Candidate selection is the stable candidate_id; the display label is presentation only.
    candidato = st.selectbox("Candidato", [None, *labels.keys()], key="candidato",
                             format_func=lambda value, labels=labels: "Todos" if value is None else labels.get(value, str(value)))
    if candidato is not None:
        filters["candidato"] = candidato
    st.divider()
    st.button("Limpar todos os filtros", icon="🧹", width="stretch", key="clear_filters", on_click=clear_dashboard_filters)
    st.caption("Fonte: Boletins de Urna · TSE")

# Cascaded selections can become invalid when an ancestor changes. Keep only the active path.
summary = get_summary(con, filters)
st.markdown('<div class="section-head"><h3>Visão geral</h3><p>Indicadores do recorte selecionado</p></div>', unsafe_allow_html=True)
metrics = [("Votos apurados", "votos_total"), ("Votos válidos", "validos"), ("Brancos", "brancos"), ("Nulos", "nulos"), ("Eleitores aptos", "aptos"), ("Compareceram", "comparecimento"), ("Abstenções", "abstencoes")]
aptos = pd.to_numeric(summary.get("aptos", 0), errors="coerce")
compareceram = pd.to_numeric(summary.get("comparecimento", 0), errors="coerce")
taxa_comparecimento = (100 * compareceram / aptos) if pd.notna(aptos) and aptos > 0 and pd.notna(compareceram) else 0
metrics.append(("Taxa de comparecimento", "taxa_comparecimento"))
cols = st.columns(4)
for i, (title, key) in enumerate(metrics):
    value = summary.get(key)
    shown = f"{taxa_comparecimento:.1f}%".replace(".", ",") if key == "taxa_comparecimento" else fmt(value)
    cols[i % 4].markdown(f'<div class="metric"><div class="metric-label">{title}</div><div class="metric-value">{shown}</div></div>', unsafe_allow_html=True)

st.markdown('<div class="section-head"><h3>Votos por candidato</h3><p>Comparação no cargo e território selecionados</p></div>', unsafe_allow_html=True)
votes = get_candidate_votes(con, filters)
if votes is None or votes.empty:
    st.info("Não há votos de candidatos para os filtros selecionados.")
else:
    import plotly.express as px
    # Backend contract returns nominal candidate votes; do not add legend rows here.
    chart_data = votes.copy()
    chart_data["Candidato"] = chart_data["NM_VOTAVEL"].astype(str)
    chart_data["Partido"] = chart_data["SG_PARTIDO"].fillna("").astype(str)
    chart_data["Rótulo"] = chart_data.apply(lambda r: f"{r['Candidato']} · {r['Partido']}" if r["Partido"] else r["Candidato"], axis=1)
    chart_data["QT_VOTOS"] = pd.to_numeric(chart_data["QT_VOTOS"], errors="coerce").fillna(0)
    chart_data = chart_data.nlargest(15, "QT_VOTOS").sort_values("QT_VOTOS")
    fig = px.bar(chart_data, x="QT_VOTOS", y="Rótulo", orientation="h", text="QT_VOTOS", color_discrete_sequence=["#087e78"])
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False, hovertemplate="%{y}<br>%{x:,.0f} votos<extra></extra>")
    fig.update_layout(height=max(300, len(chart_data)*34), margin=dict(l=10,r=55,t=10,b=10), showlegend=False, xaxis_title="Votos", yaxis_title="", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(family="DM Sans"), xaxis=dict(showgrid=True,gridcolor="rgba(128,128,128,.2)",zeroline=False), yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch", theme="streamlit", config={"displayModeBar": False})

st.markdown('<div class="section-head"><h3>Locais de votação</h3><p>Selecione um ponto para consultar o resumo do local.</p></div>', unsafe_allow_html=True)
points = get_map_points(con, filters)
if points is None or points.empty:
    st.session_state["selected_site_id"] = None
    st.info("Nenhum local corresponde aos filtros atuais.")
else:
    points = points.copy()
    if "site_id" not in points.columns:
        st.session_state["selected_site_id"] = None
        st.error("A resposta de locais não contém o identificador estável `site_id`.")
        st.stop()
    points["VL_LATITUDE"] = pd.to_numeric(points["VL_LATITUDE"], errors="coerce")
    points["VL_LONGITUDE"] = pd.to_numeric(points["VL_LONGITUDE"], errors="coerce")
    located = points.dropna(subset=["VL_LATITUDE", "VL_LONGITUDE"])
    if located.empty:
        st.warning("Há locais neste recorte, mas nenhum possui coordenadas disponíveis. Confira a preparação da base de localidades.")
    else:
        center = [located["VL_LATITUDE"].mean(), located["VL_LONGITUDE"].mean()]
        fmap = folium.Map(location=center, zoom_start=8, tiles="OpenStreetMap", control_scale=True)
        marker_cluster = MarkerCluster(
            name="Locais de votação",
            options={"showCoverageOnHover": False, "spiderfyOnMaxZoom": True, "maxClusterRadius": 48},
        ).add_to(fmap)
        for _, row in located.iterrows():
            site_id = str(row["site_id"])
            name = safe_text(row.get("NM_LOCAL_VOTACAO") or "Local de votação")
            municipio_nome = safe_text(row.get("NM_MUNICIPIO", ""))
            zona_nome = safe_text(row.get("NR_ZONA", ""))
            local_codigo = safe_text(row.get("NR_LOCAL_VOTACAO", ""))
            tooltip = f"{name} · {municipio_nome}"
            popup_html = f'<div data-site-id="{safe_text(site_id)}"><b>{name}</b><br>{municipio_nome} · Zona {zona_nome}<br>Local {local_codigo}<br>Votos: {fmt(row.get("TOTAL_VOTOS"))}</div>'
            popup = folium.Popup(popup_html, max_width=280)
            icon = folium.DivIcon(
                html='<span style="display:block;width:13px;height:13px;border-radius:50%;background:#20a393;border:2px solid #fff;box-shadow:0 1px 5px #1238;"></span>',
                icon_size=(17, 17),
                icon_anchor=(8, 8),
                class_name="site-marker-icon",
            )
            # MarkerCluster operates on L.Marker; CircleMarker (an L.Path) is not supported.
            folium.Marker(
                [row["VL_LATITUDE"], row["VL_LONGITUDE"]],
                icon=icon,
                tooltip=tooltip,
                popup=popup,
                title=f"Local {site_id}",
            ).add_to(marker_cluster)
        map_result = st_folium(fmap, use_container_width=True, height=470, key="results_map", returned_objects=["last_object_clicked", "last_object_clicked_popup"])
        clicked = map_result.get("last_object_clicked") if map_result else None
        clicked_popup = map_result.get("last_object_clicked_popup") if map_result else None
        resolved_id = None
        if clicked_popup:
            import re
            match = re.search(r'data-site-id=["\']([^"\']+)', str(clicked_popup))
            if match:
                resolved_id = html.unescape(match.group(1))
        if resolved_id and (points["site_id"].astype(str) == resolved_id).any():
            st.session_state["selected_site_id"] = resolved_id
        elif clicked:
            # Documented fallback: popup return can be absent; coordinates may be ambiguous for coincident markers.
            lat, lon = clicked.get("lat"), clicked.get("lng")
            if lat is not None and lon is not None:
                nearest = ((located["VL_LATITUDE"]-float(lat))**2 + (located["VL_LONGITUDE"]-float(lon))**2).idxmin()
                st.session_state["selected_site_id"] = str(located.loc[nearest, "site_id"])
        selected_id = st.session_state.get("selected_site_id")
        if selected_id and not (points["site_id"].astype(str) == str(selected_id)).any():
            st.session_state["selected_site_id"] = None
            selected_id = None
        if selected_id and (points["site_id"].astype(str) == selected_id).any():
            selected = points.loc[points["site_id"].astype(str) == selected_id].iloc[0]
            st.markdown(f'<div class="site-card"><strong>{safe_text(selected.get("NM_LOCAL_VOTACAO", "Local de votação"))}</strong><br><span>{safe_text(selected.get("NM_MUNICIPIO", ""))} · Zona {safe_text(selected.get("NR_ZONA", ""))} · Local {safe_text(selected.get("NR_LOCAL_VOTACAO", ""))}</span><br><span>{safe_text(selected.get("DS_ENDERECO", ""))}{" · " + safe_text(selected.get("DS_BAIRRO")) if selected.get("DS_BAIRRO") else ""}</span></div>', unsafe_allow_html=True)
            detail = get_site_detail(con, selected_id, filters)
            if detail is not None and not detail.empty:
                st.dataframe(detail, width="stretch", hide_index=True)
