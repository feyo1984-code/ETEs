# -*- coding: utf-8 -*-
import json
import os
from pathlib import Path

import ee
import geemap.foliumap as geemap
import pandas as pd
import plotly.express as px
import streamlit as st




# Autenticação via Secrets do Streamlit Cloud
service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
credentials = ee.ServiceAccountCredentials(
    service_account_info["client_email"],
    key_data=json.dumps(service_account_info)
)
ee.Initialize(credentials)






# =========================
# Nome do arquivo GeoJSON local (ATUALIZADO PARA O CAMINHO ABSOLUTO REVISADO)
# =========================
LOCAL_GEOJSON_FILE = Path("Futuras_buffer_500_v2.geojson")

# =========================
# Mapeamento de Classes e Cores MapBiomas (Coleção 10)
# Usado para renomear as classes e colorir os gráficos
# =========================
MAPBIOMAS_CLASSES = {
    3: {"name": "Formação Florestal", "color": "#129918"},
    4: {"name": "Formação Savânica", "color": "#006400"},
    5: {"name": "Mangue", "color": "#004529"},
    9: {"name": "Silvicultura", "color": "#33A2DC"},
    11: {"name": "Campo Alagado e Área Pantanosa", "color": "#B8AF4F"},
    12: {"name": "Formação Campestre", "color": "#6A6A51"},
    15: {"name": "Outras Áreas Não Florestais", "color": "#A1FDFF"},
    18: {"name": "Agricultura", "color": "#E5E500"},
    19: {"name": "Pastagem", "color": "#FFEEAD"},
    21: {"name": "Mosaico de Agricultura e Pastagem", "color": "#F1C232"},
    24: {"name": "Outras Áreas Não Vegetadas", "color": "#A5A5A5"},
    25: {"name": "Praia e Duna", "color": "#F8A033"},
    26: {"name": "Afloramento Rochoso", "color": "#FAFAD2"},
    29: {"name": "Mineração", "color": "#FF00FF"},
    30: {"name": "Área Urbana", "color": "#FFC0CB"},
    33: {"name": "Rio, Lago e Oceano", "color": "#0000FF"},
    39: {"name": "AQUICULTURA", "color": "#6EADF0"},
    62: {"name": "Outras Culturas (permanente)", "color": "#C3B19D"},
    63: {"name": "Cana", "color": "#A0522D"},
    0: {"name": "Não Observado", "color": "#FFFFFF"},
    # Adicione outras classes necessárias aqui, de 1 a 69.
}
# Lista de cores na ordem do MapBiomas, usada para o mapa GEE (se for usar o range 0-69)
# A paleta original estava simplificada. Vou usar apenas as cores definidas acima
# e garantir que a vis_params do GEE tenha cores para o range 0-69 se necessário.
# Para manter a compatibilidade com a paleta original, vamos continuar usando-a,
# mas corrigindo o mapeamento de classes para os gráficos.

# =========================
# Configuração da página
# =========================
st.set_page_config(page_title="MapBiomas – ROI (Coleção 10)", layout="wide")
st.title("Coleção MapBiomas 10 – Análise de Região de Interesse (ROI) - Lista de 33 ETEs")

st.markdown("""
Este app permite **visualizar e analisar** a classificação do MapBiomas para um **ano** e a **ROI (GeoJSON)** das ETEs.

**Como usar:**
1. Selecione o **ano** no menu lateral.
2. **Selecione a ROI** no menu lateral (baseado no campo 'Name' do GeoJSON).
3. Clique em **Executar Análise** para recortar a imagem e calcular a **área por classe**.
""")

# =========================
# Inicialização do EE (robusta)
# =========================
def init_ee():
    try:
        ee.Initialize()
        st.success("✅ Earth Engine inicializado.")
    except Exception:
        st.info("Realizando autenticação do Earth Engine…")
        try:
            ee.Authenticate()
            ee.Initialize()
            st.success("✅ Earth Engine autenticado e inicializado.")
        except Exception as e:
            st.error(f"Falha ao autenticar/Inicializar o Earth Engine: {e}")
            st.stop()

init_ee()

# =========================
# Utilitário: remover coordenada Z (3D → 2D)
# (Mantido)
# =========================
def drop_z_coords(coords):
    # ... código da função ...
    if not isinstance(coords, (list, tuple)):
        return coords
    if len(coords) > 0 and isinstance(coords[0], (int, float)):
        return coords[:2]
    return [drop_z_coords(c) for c in coords]

def normalize_geometry_dict(geom_dict):
    # ... código da função ...
    if not isinstance(geom_dict, dict):
        raise ValueError("Geometria inválida: não é um dict.")
    out = dict(geom_dict)
    if "coordinates" in out:
        out["coordinates"] = drop_z_coords(out["coordinates"])
    return out

# =========================
# Conversão GeoJSON → EE (robusta)
# (Mantido)
# =========================
def geojson_to_ee_objs(geojson_obj):
    # ... código da função ...
    try:
        ee_obj = geemap.geojson_to_ee(geojson_obj)
        if isinstance(ee_obj, ee.Geometry):
            fc = ee.FeatureCollection([ee.Feature(ee_obj)])
            geom = ee_obj
        elif isinstance(ee_obj, ee.FeatureCollection):
            fc = ee_obj
            geom = fc.geometry()
        else:
            fc = ee.FeatureCollection([ee_obj])
            geom = fc.geometry()
        return fc, geom
    except Exception:
        # Fallback manual
        t = geojson_obj.get("type", None)
        if t == "FeatureCollection":
            feats = geojson_obj.get("features", [])
            if not feats:
                raise ValueError("FeatureCollection vazia.")
            norm_feats = []
            for f in feats:
                geom = f.get("geometry")
                if geom is None:
                    continue
                geom = normalize_geometry_dict(geom)
                norm_feats.append(ee.Feature(ee.Geometry(geom)))
            if not norm_feats:
                raise ValueError("Nenhuma geometria válida encontrada na FeatureCollection.")
            fc = ee.FeatureCollection(norm_feats)
            geom = fc.geometry()
            return fc, geom

        elif t == "Feature":
            geom = geojson_obj.get("geometry")
            if geom is None:
                raise ValueError("Feature sem 'geometry'.")
            geom = normalize_geometry_dict(geom)
            ee_geom = ee.Geometry(geom)
            fc = ee.FeatureCollection([ee.Feature(ee_geom)])
            return fc, ee_geom

        elif t in (
            "Point", "MultiPoint", "LineString", "MultiLineString",
            "Polygon", "MultiPolygon", "GeometryCollection"
        ):
            geom = normalize_geometry_dict(geojson_obj)
            ee_geom = ee.Geometry(geom)
            fc = ee.FeatureCollection([ee.Feature(ee_geom)])
            return fc, ee_geom

        else:
            raise ValueError(f"Tipo GeoJSON não suportado: {t}")

# =========================
# Carregamento e filtragem da ROI
# (Mantido)
# =========================

@st.cache_data
def load_and_parse_geojson(filepath):
    # ... código da função ...
    if not filepath.exists():
        st.error(f"Arquivo GeoJSON não encontrado: {filepath}. Verifique o caminho absoluto.")
        st.stop()
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    if data.get("type") != "FeatureCollection":
         st.error(f"O GeoJSON deve ser do tipo 'FeatureCollection'.")
         st.stop()
    return data

@st.cache_data
def get_roi_names(geojson_data):
    # ... código da função ...
    names = []
    for feature in geojson_data.get("features", []):
        name = feature.get("properties", {}).get("Name")
        if name:
            names.append(str(name))
    return sorted(names)

def get_feature_by_name(geojson_data, name):
    # ... código da função ...
    for feature in geojson_data.get("features", []):
        if feature.get("properties", {}).get("Name") == name:
            return feature
    return None

# Carrega os dados uma vez
try:
    all_geojson_data = load_and_parse_geojson(LOCAL_GEOJSON_FILE)
    roi_names = get_roi_names(all_geojson_data)
except Exception:
    pass

# =========================
# Sidebar: parâmetros
# (Mantido)
# =========================
with st.sidebar:
    st.header("Configurações")
    ano_novo = st.selectbox("📅 Ano", list(range(1985, 2025)), index=2024 - 1985)
    
    if not roi_names:
        if 'all_geojson_data' in locals() and all_geojson_data:
             st.error("Nenhuma 'Feature' com a coluna 'Name' encontrada no GeoJSON. Verifique se o nome da coluna está correto (case sensitive).")
        st.stop()
        
    selected_roi_name = st.selectbox(
        "🗺️ Selecione a ROI (Name)", 
        roi_names
    )
    
    run_btn = st.button("🚀 Executar Análise")

# Persistência do ano
if "ano_atual" not in st.session_state:
    st.session_state["ano_atual"] = 2024
if run_btn:
    st.session_state["ano_atual"] = ano_novo
ano = st.session_state["ano_atual"]

# =========================
# MapBiomas – Coleção 10
# =========================
MAPBIOMAS_ID = "projects/mapbiomas-public/assets/brazil/lulc/collection10/mapbiomas_brazil_collection10_integration_v2"
image = ee.Image(MAPBIOMAS_ID)
lulc = image.select(f"classification_{ano}")

# Paleta original (simplificada)
palette = [
    "#ffffff", "#32a65e", "#1f8d49", "#7dc975", "#04381d", "#026975", "#000000",
    "#7a6c00", "#ad975a", "#519799", "#d6bc74", "#d89f5c", "#FFFFB2", "#edde8e",
    "#f5b3c8", "#C27BA0", "#db7093", "#ffefc3", "#db4d4f", "#ffa07a", "#d4271e",
    "#0000FF", "#2532e4", "#091077", "#fc8114", "#93dfe6", "#9065d0", "#d082de",
]
vis_params = {"min": 0, "max": 69, "palette": palette}

# =========================
# Mapa base
# CORREÇÃO 1: Inicializa o mapa uma única vez.
# =========================
m = geemap.Map(location=[-14.5, -52], zoom=4)
m.setOptions("HYBRID")
# Adiciona a camada MapBiomas completa.
m.addLayer(lulc, vis_params, f"MapBiomas Col10 – {ano}")

# =========================
# Lógica da ROI e análise
# =========================
# (analisar_roi e calcular_area_por_classe são mantidas)

def analisar_roi(geojson_feature):
    # ... código da função ...
    try:
        fc, geom = geojson_to_ee_objs(geojson_feature)
    except Exception as e:
        raise ValueError(f"Falha ao converter GeoJSON em geometria do EE: {e}")
    # ... validação ...
    return fc, geom

def calcular_area_por_classe(geom):
    # ... código da função ...
    pixel_area = ee.Image.pixelArea().divide(1e4)  # hectares
    image_area = pixel_area.addBands(lulc)

    area_por_classe = image_area.reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
        geometry=geom,
        scale=30,
        maxPixels=1e13,
        bestEffort=True
    )

    stats = area_por_classe.getInfo()
    groups = stats.get("groups", [])

    if not groups:
        return pd.DataFrame(columns=["Classe", "Área (ha)"])

    df = pd.DataFrame(groups)
    df = df.rename(columns={"class": "Classe", "sum": "Área (ha)"})
    df = df.sort_values("Área (ha)", ascending=False)
    
    # CORREÇÃO 2a: Mapeia os códigos de classe para Nomes e Cores
    df["Nome da Classe"] = df["Classe"].apply(lambda x: MAPBIOMAS_CLASSES.get(x, {}).get("name", f"Classe {x}"))
    df["Cor"] = df["Classe"].apply(lambda x: MAPBIOMAS_CLASSES.get(x, {}).get("color", "#CCCCCC")) # Cinza se a cor não for encontrada
    
    return df

# Botão de execução
if run_btn and selected_roi_name:
    # 1. Obtém a Feature GeoJSON selecionada
    selected_feature = get_feature_by_name(all_geojson_data, selected_roi_name)
    
    if selected_feature is None:
        st.error(f"Erro: Não foi possível encontrar a Feature GeoJSON com 'Name': {selected_roi_name}.")
        st.stop()
        
    try:
        # 2. Converte para objetos EE
        roi_fc, roi_geom = analisar_roi(selected_feature)
        
        # 3. Adiciona a camada da ROI (apenas o contorno)
        # CORREÇÃO 3: Usando um estilo claro para o contorno da ROI
        roi_style = {'color': 'red', 'fillColor': '00000000'} # Transparente no interior
        m.addLayer(roi_fc.style(**roi_style), {}, f"Contorno ROI: {selected_roi_name}")
        m.centerObject(roi_geom, zoom=9)

        # 4. Recorte e visualização da classificação MapBiomas dentro da ROI
        lulc_clip = lulc.clip(roi_geom)
        m.addLayer(lulc_clip, vis_params, f"MapBiomas Clip: {selected_roi_name} – {ano}")

        # 5. Área por classe
        df_area = calcular_area_por_classe(roi_geom)

        if df_area.empty:
            st.warning(f"Nenhuma área calculada para a ROI '{selected_roi_name}' (verifique se a geometria está dentro do Brasil e o ano possui dados).")
        else:
            col1, col2 = st.columns(2)
            
            # Mapeamento de Cores para Plotly
            color_map = df_area.set_index("Nome da Classe")["Cor"].to_dict()

            with col1:
                st.markdown("### 📊 Área por classe (barras)")
                # CORREÇÃO 2b: Usa a coluna 'Nome da Classe' e o mapa de cores
                fig_bar = px.bar(
                    df_area, 
                    x="Nome da Classe", 
                    y="Área (ha)", 
                    color="Nome da Classe",
                    color_discrete_map=color_map, # Aplica o mapeamento de cores
                    category_orders={"Nome da Classe": df_area["Nome da Classe"].tolist()}
                )
                fig_bar.update_layout(xaxis_title="Classe", yaxis_title="Área (ha)")
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with col2:
                st.markdown("### 🥧 Área por classe (pizza)")
                # CORREÇÃO 2c: Usa a coluna 'Nome da Classe' e o mapa de cores
                fig_pie = px.pie(
                    df_area, 
                    values="Área (ha)", 
                    names="Nome da Classe",
                    color="Nome da Classe",
                    color_discrete_map=color_map # Aplica o mapeamento de cores
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            # Exibe a tabela, incluindo Nomes e Cores para referência
            st.dataframe(df_area[["Classe", "Nome da Classe", "Área (ha)"]], use_container_width=True)

    except ValueError as e:
        st.error(f"Erro ao processar a ROI: {e}")
    except Exception as e:
        st.error(f"Falha inesperada na análise: {e}")

# CORREÇÃO 1 (Continuação): Exibe o mapa uma única vez no final, 
# após todas as camadas (base, contorno da ROI, recorte) serem adicionadas.
m.to_streamlit(height=550, width=1200)

if not run_btn:
    st.info("Selecione um ano e uma ROI e clique em 'Executar Análise'.")
elif run_btn and 'selected_roi_name' in locals() and not selected_roi_name:
    st.warning("Selecione uma ROI no menu lateral.")
