import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import matplotlib.pyplot as plt
import seaborn as sns
from folium.plugins import FloatImage
from streamlit_folium import st_folium
from io import BytesIO
from datetime import datetime

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# --------- Paths ---------
csv_zip_path = "columns_kept.zip"
shp_zip_path = "filtered_11_counties.zip"
csv_folder = "csv_data"
shp_folder = "shapefile_data"

# --------- Extract ZIPs if needed ---------
if not os.path.exists(csv_folder):
    os.makedirs(csv_folder, exist_ok=True)
    with zipfile.ZipFile(csv_zip_path, 'r') as zip_ref:
        inner_dir = zip_ref.namelist()[0].split('/')[0]
        zip_ref.extractall(csv_folder)
    csv_folder = os.path.join(csv_folder, inner_dir)

if not os.path.exists(shp_folder):
    os.makedirs(shp_folder, exist_ok=True)
    with zipfile.ZipFile(shp_zip_path, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# --------- Load CSV Data ---------
csv_files = [f for f in os.listdir(csv_folder) if f.endswith(".csv")]
all_data = []

for file in csv_files:
    df = pd.read_csv(os.path.join(csv_folder, file), low_memory=False)
    required_cols = ["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "ActivityStartDate", "CharacteristicName", "ResultMeasureValue"]
    if all(col in df.columns for col in required_cols):
        df = df.dropna(subset=required_cols)
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
        df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')
        all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# --------- Load Shapefile ---------
shapefile_path = [os.path.join(shp_folder, f) for f in os.listdir(shp_folder) if f.endswith(".shp")][0]
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# Clean for Folium
gdf_clean = gdf.copy()
gdf_clean = gdf_clean[["geometry"] + (["County"] if "County" in gdf.columns else [])]

# --------- Parameter Selector (Top Bar) ---------
st.sidebar.subheader("Map Circle Sizing Parameter")
param_to_map = st.sidebar.selectbox("Select parameter to size map circles:", combined_df["CharacteristicName"].unique())

# --------- Latest Value Per Site ---------
latest_df = combined_df[combined_df["CharacteristicName"] == param_to_map].sort_values("ActivityStartDate")
latest_vals = latest_df.groupby(["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])["ResultMeasureValue"].last().reset_index()

# --------- Map Display ---------
st.subheader("🗺️ Monitoring Sites Map")
center = [latest_df["ActivityLocation/LatitudeMeasure"].mean(), latest_df["ActivityLocation/LongitudeMeasure"].mean()]
m = folium.Map(location=center, zoom_start=7, tiles="CartoDB positron")

# Add County Boundaries
folium.GeoJson(
    gdf_clean,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.4
    },
    tooltip="County" if "County" in gdf_clean.columns else None
).add_to(m)

# Add monitoring points
for _, row in latest_vals.iterrows():
    val = row["ResultMeasureValue"]
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=5 + min(val / 5, 20),
        fill=True,
        fill_opacity=0.8,
        popup=f"{param_to_map}: {val:.2f}"
    ).add_to(m)

st_data = st_folium(m, width=1300, height=600)

# --------- Point Selection + Multi-param Analysis ---------
if st_data and "last_object_clicked" in st_data:
    clicked_lat = st_data["last_object_clicked"].get("lat")
    clicked_lon = st_data["last_object_clicked"].get("lng")
    st.subheader("📌 Selected Station")
    st.write(f"**Coordinates:** {clicked_lat:.4f}, {clicked_lon:.4f}")

    if st.button("Run Analysis"):
        selected_df = combined_df[(combined_df["ActivityLocation/LatitudeMeasure"].round(4) == round(clicked_lat, 4)) &
                                  (combined_df["ActivityLocation/LongitudeMeasure"].round(4) == round(clicked_lon, 4))]

        st.subheader("📈 Time Series Plot")
        multi_params = st.multiselect("Select Parameters:", selected_df["CharacteristicName"].unique(), default=[param_to_map])
        chart_data = selected_df[selected_df["CharacteristicName"].isin(multi_params)]
        pivot_df = chart_data.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
        pivot_df = pivot_df.sort_index()

        st.line_chart(pivot_df)

        st.subheader("📊 Correlation Heatmap")
        corr = pivot_df.corr()
        fig, ax = plt.subplots(figsize=(6, 5))
        sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)
        st.pyplot(fig)

        st.subheader("📋 Statistical Summary")
        st.dataframe(pivot_df.describe().T)
