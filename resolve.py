import io
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image
import re


# ---------------------------
# Page config and base styles
# ---------------------------
st.set_page_config(
    page_title="Meta Ads - Performance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
            :root {
                --card-bg: #ffffff;
                --card-border: #e6e6e6;
                --muted: #6b7280;
                --primary: #2563eb;
                --accent: #10b981;
            }
            .kpi-card {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 14px;
                padding: 18px 16px;
                margin-bottom: 12px;
                box-shadow: 0 1px 2px rgba(0,0,0,0.06);
            }
            .kpi-label {
                color: var(--muted);
                font-size: 0.88rem;
                margin-bottom: 6px;
            }
            .kpi-value {
                font-size: 1.6rem;
                font-weight: 700;
                color: black;
            }
            .section {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 14px;
                padding: 14px;
                box-shadow: 0 1px 2px rgba(0,0,0,0.06);
            }
            .subtle {
                color: var(--muted);
            }
            .creative-card {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 14px;
                padding: 10px;
                box-shadow: 0 1px 2px rgba(0,0,0,0.06);
                height: 100%;
            }
            .creative-image {
                width: 100%;
                height: 180px;
                object-fit: cover;
                border-radius: 10px;
                border: 1px solid var(--card-border);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()


# ---------------------------
# Data Loading
# ---------------------------
DATA_FILE = os.path.join(os.getcwd(), "dados_meta_ads.xlsx")
IMAGES_DIR = os.path.join(os.getcwd(), "images")


@st.cache_data(show_spinner=True)
def load_data(path: str) -> pd.DataFrame:
    # Read all sheets from the Excel file and combine into a single DataFrame
    try:
        xls = pd.ExcelFile(path)
        frames = []
        for sheet_name in xls.sheet_names:
            tmp = pd.read_excel(xls, sheet_name=sheet_name)
            tmp["__sheet__"] = sheet_name
            frames.append(tmp)
        df = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    except Exception:
        # Fallback to single-sheet read
        df = pd.read_excel(path)

    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]

    # Parse dates
    for col in ["Início dos relatórios", "Término dos relatórios"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Coerce numeric fields when possible
    numeric_like = [
        "Resultados",
        "Alcance",
        "Frequência",
        "Custo por resultados",
        "Valor usado (BRL)",
        "Impressões",
        "CPM (custo por 1.000 impressões) (BRL)",
        "Cliques no link",
        "CPC (custo por clique no link) (BRL)",
        "CTR (taxa de cliques no link)",
        "Cliques (todos)",
        "CTR (todos)",
        "CPC (todos) (BRL)",
        "actions:omni_landing_page_view",
    ]
    for c in numeric_like:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Derived helpers
    # Prefer link-based CTR/CPC if available, fallback to general
    if "CTR (taxa de cliques no link)" in df.columns and df[
        "CTR (taxa de cliques no link)"
    ].notna().any():
        df["CTR_calc"] = df["CTR (taxa de cliques no link)"]
    elif "CTR (todos)" in df.columns:
        df["CTR_calc"] = df["CTR (todos)"]
    else:
        df["CTR_calc"] = np.nan

    if (
        "CPC (custo por clique no link) (BRL)" in df.columns
        and df["CPC (custo por clique no link) (BRL)"].notna().any()
    ):
        df["CPC_calc"] = df["CPC (custo por clique no link) (BRL)"]
    elif "CPC (todos) (BRL)" in df.columns:
        df["CPC_calc"] = df["CPC (todos) (BRL)"]
    else:
        df["CPC_calc"] = np.nan

    # Visits proxy
    if "actions:omni_landing_page_view" in df.columns:
        df["Visitas"] = df["actions:omni_landing_page_view"].fillna(0)
    else:
        df["Visitas"] = np.nan

    # Conversions proxy (Resultados)
    if "Resultados" in df.columns:
        df["Conversões"] = df["Resultados"].fillna(0)
    else:
        df["Conversões"] = np.nan

    # Unify a single date for timeline (start date preferred)
    if "Início dos relatórios" in df.columns:
        df["Data"] = df["Início dos relatórios"].dt.date
    elif "Término dos relatórios" in df.columns:
        df["Data"] = df["Término dos relatórios"].dt.date
    else:
        df["Data"] = pd.NaT

    return df


def try_open_image(base_name: str) -> Image.Image | None:
    if not os.path.isdir(IMAGES_DIR):
        return None
    candidates = [
        os.path.join(IMAGES_DIR, f"{base_name}.png"),
        os.path.join(IMAGES_DIR, f"{base_name}.jpg"),
        os.path.join(IMAGES_DIR, f"{base_name}.jpeg"),
        os.path.join(IMAGES_DIR, f"{base_name}.webp"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return Image.open(path)
            except Exception:
                continue
    return None


def extract_ad_code(ad_name: str) -> str | None:
    if not isinstance(ad_name, str):
        return None
    s = ad_name.strip().replace("_", " ")
    # Accept variants: AD01, AD 01, AD-01, ad01, [AD01], etc. Normalize to AD01..AD10
    match = re.search(r"(?i)\bAD\s*[-:]?\s*0?(10|[1-9])\b", s)
    if match:
        num = int(match.group(1))
        return f"AD{num:02d}"
    # Fallback: within tokens without word boundaries
    match2 = re.search(r"(?i)AD\s*[-:]?\s*0?(10|[1-9])", s)
    if match2:
        num = int(match2.group(1))
        return f"AD{num:02d}"
    return None


# ---------------------------
# Load data and Sidebar
# ---------------------------
if not os.path.exists(DATA_FILE):
    st.error(
        "Arquivo de dados não encontrado. Certifique-se de que 'dados_meta_ads.xlsx' está na mesma pasta do app."
    )
    st.stop()

df_raw = load_data(DATA_FILE)

st.sidebar.title("Filtros")

# Date filter (fixed)
start_date = datetime(2025, 8, 12).date()
end_date = datetime(2025, 10, 8).date()
st.sidebar.info("Período fixo: 12/08/2025 até 08/10/2025")

# Budget type filter
budget_types = [
    v for v in df_raw.get("Tipo de orçamento do conjunto de anúncios", pd.Series()).dropna().unique()
]
budget_selected = st.sidebar.multiselect(
    "Tipo de orçamento",
    options=sorted(budget_types) if budget_types else [],
    default=budget_types if budget_types else [],
)

# Ad name filter
ad_names = [v for v in df_raw.get("Nome do anúncio", pd.Series()).dropna().unique()]
ad_selected = st.sidebar.multiselect(
    "Nome do anúncio",
    options=sorted(ad_names) if ad_names else [],
)

st.sidebar.markdown("---")
st.sidebar.caption("Dica: Clique nas legendas dos gráficos para ativar/desativar séries.")

# Apply filters
df = df_raw.copy()

if start_date and end_date and "Data" in df.columns:
    mask_date = (pd.to_datetime(df["Data"]) >= pd.to_datetime(start_date)) & (
        pd.to_datetime(df["Data"]) <= pd.to_datetime(end_date)
    )
    df = df.loc[mask_date]

if budget_selected and "Tipo de orçamento do conjunto de anúncios" in df.columns:
    df = df[df["Tipo de orçamento do conjunto de anúncios"].isin(budget_selected)]

if ad_selected and "Nome do anúncio" in df.columns:
    df = df[df["Nome do anúncio"].isin(ad_selected)]


# ---------------------------
# KPI Summary
# ---------------------------
st.markdown("## 📊 Meta Ads - Dashboard de Desempenho")
st.caption("Análise interativa de campanhas: visão geral, funil, linha do tempo, criativos e comparações.")

def kpi_card(label: str, value: str):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

# KPI cards now reflect the FULL dataset (todas as abas/linhas do XLSX)
alcance_total = float(df_raw.get("Alcance", pd.Series(dtype=float)).sum())
impressoes_total = float(df_raw.get("Impressões", pd.Series(dtype=float)).sum())
cliques_total = float(df_raw.get("Cliques no link", pd.Series(dtype=float)).sum())
ctr_medio = float(df_raw.get("CTR_calc", pd.Series(dtype=float)).mean())
cpc_medio = float(df_raw.get("CPC_calc", pd.Series(dtype=float)).mean())
custo_total = float(df_raw.get("Valor usado (BRL)", pd.Series(dtype=float)).sum())
conversoes_total = float(df_raw.get("Conversões", pd.Series(dtype=float)).sum())

col1_kpi = f"{alcance_total:,.0f}" if np.isfinite(alcance_total) else "-"
col2_kpi = f"{impressoes_total:,.0f}" if np.isfinite(impressoes_total) else "-"
col3_kpi = f"{cliques_total:,.0f}" if np.isfinite(cliques_total) else "-"
col4_kpi = f"{ctr_medio:,.2f}%" if np.isfinite(ctr_medio) else "-"
col5_kpi = f"R$ {cpc_medio:,.2f}" if np.isfinite(cpc_medio) else "-"
col6_kpi = f"R$ {custo_total:,.2f}" if np.isfinite(custo_total) else "-"
col7_kpi = f"{conversoes_total:,.0f}" if np.isfinite(conversoes_total) else "-"

with col1:
    kpi_card("Alcance", col1_kpi)
with col2:
    kpi_card("Impressões", col2_kpi)
with col3:
    kpi_card("Cliques", col3_kpi)
with col4:
    kpi_card("CTR médio", col4_kpi)
with col5:
    kpi_card("CPC médio", col5_kpi)
with col6:
    kpi_card("Custo total", col6_kpi)
with col7:
    kpi_card("Conversões", col7_kpi)


# ---------------------------
# Tabs Navigation
# ---------------------------
tab_overview, tab_funnel, tab_creatives, tab_compare, tab_data = st.tabs(
    ["Visão Geral", "Funil de Vendas", "Anúncios (AD01–AD10)", "Comparações", "Dados"]
)

with tab_overview:
    st.markdown("### 🧭 Visão Geral (todos os dados)")
    st.dataframe(df_raw, use_container_width=True, hide_index=True)

    def to_excel_bytes_full(dataframe: pd.DataFrame) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="todos_os_dados")
        return output.getvalue()

    excel_full = to_excel_bytes_full(df_raw)
    st.download_button(
        label="⬇️ Baixar XLSX (todos os dados)",
        data=excel_full,
        file_name=f"meta_ads_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------
# Funil de Vendas
# ---------------------------
with tab_funnel:
    st.markdown("### 🔻 Funil de Vendas")

    funnel_order = [
        ("Alcance", float(df.get("Alcance", pd.Series(dtype=float)).sum())),
        ("Impressões", float(df.get("Impressões", pd.Series(dtype=float)).sum())),
        ("Cliques", float(df.get("Cliques no link", pd.Series(dtype=float)).sum())),
        ("Visitas ao site", float(df.get("Visitas", pd.Series(dtype=float)).sum())),
        ("Conversões", float(df.get("Conversões", pd.Series(dtype=float)).sum())),
    ]

    funnel_df = pd.DataFrame(funnel_order, columns=["Etapa", "Valor"])\
        .replace({np.inf: np.nan, -np.inf: np.nan}).fillna(0)

    fig_funnel = px.funnel(
        funnel_df,
        x="Valor",
        y="Etapa",
        color="Etapa",
        color_discrete_sequence=px.colors.sequential.Blues,
    )
    fig_funnel.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_funnel, use_container_width=True)


# (Seção de Linha do Tempo removida conforme solicitado)


# ---------------------------
# Best Creatives
# ---------------------------
with tab_creatives:
    st.markdown("### 🖼️ Anúncios AD01–AD10")

    # Map each row to an AD code for grouping
    # Use ALL data (ignore date filters) as requested
    df_codes = df_raw.copy()
    df_codes["AD_Code"] = df_codes.get("Nome do anúncio", pd.Series(dtype=str)).apply(extract_ad_code)

    agg_cols = {
        "Impressões": "sum",
        "Cliques no link": "sum",
        "Conversões": "sum",
        "Valor usado (BRL)": "sum",
        "CTR_calc": "mean",
        "CPC_calc": "mean",
    }
    agg_cols = {k: v for k, v in agg_cols.items() if k in df_codes.columns}

    by_adcode = (
        df_codes.dropna(subset=["AD_Code"]).groupby("AD_Code").agg(agg_cols).reset_index()
        if "AD_Code" in df_codes.columns and not df_codes["AD_Code"].isna().all()
        else pd.DataFrame(columns=["AD_Code"] + list(agg_cols.keys()))
    )

    ad_list = [f"AD{i:02d}" for i in range(1, 11)]
    cols = st.columns(5)
    for idx, code in enumerate(ad_list):
        # fetch row if exists
        if not by_adcode.empty and code in by_adcode["AD_Code"].values:
            row = by_adcode.loc[by_adcode["AD_Code"] == code].iloc[0]
            ctr_val = float(row["CTR_calc"]) if "CTR_calc" in row and pd.notna(row["CTR_calc"]) else 0.0
            cpc_val = float(row["CPC_calc"]) if "CPC_calc" in row and pd.notna(row["CPC_calc"]) else 0.0
            conv_val = int(row["Conversões"]) if "Conversões" in row and pd.notna(row["Conversões"]) else 0
        else:
            ctr_val, cpc_val, conv_val = 0.0, 0.0, 0

        col = cols[idx % 5]
        with col:
            with st.container():
                st.markdown("<div class='creative-card'>", unsafe_allow_html=True)
                img = try_open_image(code)
                if img is not None:
                    st.image(img, use_container_width=True, caption=code)
                else:
                    st.image(
                        np.zeros((180, 320, 3), dtype=np.uint8) + 240,
                        use_container_width=True,
                        caption=f"{code} (imagem não encontrada)",
                    )

                st.markdown(
                    f"<div class='subtle'>CTR médio</div><div><b>{ctr_val:.2f}%</b></div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='subtle'>CPC médio</div><div><b>R$ {cpc_val:.2f}</b></div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='subtle'>Conversões</div><div><b>{conv_val}</b></div>",
                    unsafe_allow_html=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------
# Comparisons & Advanced
# ---------------------------
with tab_compare:
    st.markdown("### 📊 Comparações e Análises Avançadas")

    left, right = st.columns(2)

    dims_available = [
        c
        for c in [
            "Nome do anúncio",
            "Tipo de orçamento do conjunto de anúncios",
            "Data",
        ]
        if c in df.columns
    ]

    metrics_available = [
        c
        for c in [
            "Impressões",
            "Cliques no link",
            "Conversões",
            "Valor usado (BRL)",
            "CPC_calc",
            "CTR_calc",
            "CPM (custo por 1.000 impressões) (BRL)",
        ]
        if c in df.columns
    ]

    with left:
        x_axis = st.selectbox("Eixo X", options=metrics_available, index=metrics_available.index("Impressões") if "Impressões" in metrics_available else 0)
        y_axis = st.selectbox(
            "Eixo Y",
            options=metrics_available,
            index=metrics_available.index("Cliques no link") if "Cliques no link" in metrics_available else 0,
        )
        color_dim = st.selectbox("Cor por", options=[None] + dims_available, index=0)

        fig_scatter = px.scatter(
            df.replace({np.inf: np.nan, -np.inf: np.nan}).dropna(subset=[x_axis, y_axis]),
            x=x_axis,
            y=y_axis,
            color=color_dim,
            hover_name="Nome do anúncio" if "Nome do anúncio" in df.columns else None,
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_scatter.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_scatter, use_container_width=True)

    with right:
        box_metric = st.selectbox("Métrica (boxplot)", options=metrics_available, index=0)
        group_dim = st.selectbox(
            "Agrupar por",
            options=dims_available if dims_available else [None],
            index=0,
        )
        if group_dim is not None and group_dim in df.columns:
            fig_box = px.box(
                df.replace({np.inf: np.nan, -np.inf: np.nan}).dropna(subset=[box_metric]),
                x=group_dim,
                y=box_metric,
                color=group_dim,
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig_box.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            st.info("Selecione um agrupamento válido para o boxplot.")

    st.markdown("#### 🔥 Correlação entre Métricas")
    corr_cols = [c for c in metrics_available if c in df.columns]
    if len(corr_cols) >= 2:
        corr = df[corr_cols].replace({np.inf: np.nan, -np.inf: np.nan}).dropna().corr(numeric_only=True)
        fig_heat = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu", origin="lower")
        fig_heat.update_layout(height=480, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("Métricas insuficientes para calcular correlação.")


# ---------------------------
# Raw Data + Export + Insights
# ---------------------------
with tab_data:
    st.markdown("### 🧾 Dados Filtrados e Exportação")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Export to Excel of the filtered dataset
    def to_excel_bytes(dataframe: pd.DataFrame) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="dados")
        return output.getvalue()

    excel_bytes = to_excel_bytes(df)
    st.download_button(
        label="⬇️ Baixar XLSX (dados filtrados)",
        data=excel_bytes,
        file_name=f"meta_ads_filtrado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### 💡 Insights Automáticos")
    insights = []

    # Best CTR
    if "Nome do anúncio" in df.columns and df["Nome do anúncio"].notna().any():
        by_ad_ins = (
            df.groupby("Nome do anúncio")
            .agg({"CTR_calc": "mean", "CPC_calc": "mean", "Conversões": "sum"})
            .reset_index()
        )
        if not by_ad_ins.empty:
            best_ctr_row = by_ad_ins.loc[by_ad_ins["CTR_calc"].idxmax()]
            insights.append(
                f"O anúncio {best_ctr_row['Nome do anúncio']} teve o maior CTR médio de {best_ctr_row['CTR_calc']*100:.2f}%."
            )
            best_cpc_row = by_ad_ins.loc[by_ad_ins["CPC_calc"].idxmin()]
            insights.append(
                f"O anúncio {best_cpc_row['Nome do anúncio']} teve o menor CPC médio de R$ {best_cpc_row['CPC_calc']:.2f}."
            )
            best_conv_row = by_ad_ins.loc[by_ad_ins["Conversões"].idxmax()]
            insights.append(
                f"O anúncio {best_conv_row['Nome do anúncio']} gerou mais conversões ({int(best_conv_row['Conversões'])})."
            )

    if custo_total > 0 and conversoes_total >= 0:
        # Simple ROI proxy if conversions value unknown: assume R$0 per conversion, so ROI not computable.
        # Here we only show CPA if conversions exist.
        if conversoes_total > 0:
            cpa = custo_total / conversoes_total
            insights.append(f"CPA médio estimado: R$ {cpa:.2f}.")

    if not insights:
        st.info("Sem insights automáticos para o filtro atual.")
    else:
        for tip in insights:
            st.markdown(f"- {tip}")


# Footer note
st.caption(
    "Construído com Streamlit, Plotly e Pandas • Dica: use a barra lateral para filtrar."
)


