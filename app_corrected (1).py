import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import glob
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import matplotlib.colors as mcolors
from streamlit_folium import st_folium

st.set_page_config(layout="wide", page_title="Water Quality Map")
st.title("🌊 Texas Coastal Water Quality Monitoring")
st.markdown("---")

# --- Paths ---
csv_zip = "columns_kept.zip"
shp_zip = "filtered_11_counties.zip"
csv_folder = "csv_extracted"
shp_folder = "shp_extracted"

# --- Unzip CSV files ---
if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

# --- Load CSVs ---
csv_files = []
for root, _, files in os.walk(csv_folder):
    for file in files:
        if file.endswith(".csv"):
            csv_files.append(os.path.join(root, file))

all_data = []
for file in csv_files:
    try:
        df = pd.read_csv(file, low_memory=False)
        df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
        if not df.empty:
            all_data.append(df)
    except Exception as e:
        st.warning(f"⚠️ Error loading {file}: {e}")

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

df = pd.concat(all_data, ignore_index=True)

# --- Clean & Validate ---
required_cols = ["ActivityStartDate", "CharacteristicName", "ResultMeasureValue"]
missing = [col for col in required_cols if col not in df.columns]
if missing:
    st.error(f"❌ Missing required columns: {', '.join(missing)}")
    st.stop()

df = df.dropna(subset=required_cols)
df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')

# --- Load shapefile ---
if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip, "r") as zip_ref:
        zip_ref.extractall(shp_folder)

shp_files = glob.glob(os.path.join(shp_folder, "**", "*.shp"), recursive=True)
if not shp_files:
    st.error("❌ No shapefile found.")
    st.stop()

gdf = gpd.read_file(shp_files[0]).to_crs(epsg=4326)
gdf_safe = gdf[[col for col in gdf.columns if gdf[col].dtype.kind in 'ifO']].copy()
gdf_safe["geometry"] = gdf["geometry"]

# --- Main Parameter Selection ---
available_params = sorted(df["CharacteristicName"].dropna().unique())
selected_param = st.selectbox("📌 Select Parameter for Map Circle Sizing:", available_params)

# --- Get latest value per station ---
df["StationKey"] = df["ActivityLocation/LatitudeMeasure"].astype(str) + "," + df["ActivityLocation/LongitudeMeasure"].astype(str)
filtered_df = df[df["CharacteristicName"] == selected_param]
latest_values = (
    filtered_df.sort_values("ActivityStartDate")
    .groupby("StationKey")
    .tail(1)
    .set_index("StationKey")
)

# --- Map ---
map_center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[map_center.y, map_center.x], zoom_start=7, tiles="CartoDB positron")

# Add counties
folium.GeoJson(
    gdf_safe,
    name="Counties",
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.1,
    },
).add_to(m)

# Add points
for key, row in latest_values.iterrows():
    lat, lon = row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]
    val = row["ResultMeasureValue"]
    popup_html = f"""
    <b>Location:</b> {key}<br>
    <b>{selected_param}:</b> {val:.2f}<br>
    <b>Date:</b> {row['ActivityStartDate'].strftime('%Y-%m-%d')}
    """
    folium.CircleMarker(
        location=[lat, lon],
        radius=3 + min(val, 10),
        fill=True,
        color="blue",
        fill_opacity=0.6,
        popup=folium.Popup(popup_html, max_width=300),
    ).add_to(m)

# Display Map
st.markdown("## 🗌 Select Station")
st_data = st_folium(m, height=600, width=1200)

# Station Clicked
if st_data and st_data.get("last_object_clicked"):
    lat = round(st_data["last_object_clicked"]["lat"], 5)
    lon = round(st_data["last_object_clicked"]["lng"], 5)
    st.markdown(f"📍 Selected Coordinates: **{lat}, {lon}**")

    if st.button("Run Analysis"):
        station_df = df[(df["ActivityLocation/LatitudeMeasure"].round(5) == lat) &
                        (df["ActivityLocation/LongitudeMeasure"].round(5) == lon)]

        selected_params = st.multiselect("Select Parameters to Plot:", sorted(station_df["CharacteristicName"].unique()), default=[selected_param])
        plot_df = station_df[station_df["CharacteristicName"].isin(selected_params)]

        if plot_df.empty:
            st.warning("No data for selected parameters at this station.")
        else:
            # Time Series
            fig, ax = plt.subplots(figsize=(12, 5))
            for param in selected_params:
                sub = plot_df[plot_df["CharacteristicName"] == param]
                ax.plot(sub["ActivityStartDate"], sub["ResultMeasureValue"], label=param)
            ax.set_xlabel("Date")
            ax.set_ylabel("Result Measure")
            ax.set_title("Time Series of Selected Parameters")
            ax.legend()
            ax.grid(True)
            ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b %Y'))
            plt.xticks(rotation=45)
            st.pyplot(fig)

            # Summary Table
            stats_table = plot_df.groupby("CharacteristicName")["ResultMeasureValue"].describe().round(2)
            st.markdown("### 📊 Summary Statistics")
            st.dataframe(stats_table)

            # Correlation Heatmap
            pivot_df = plot_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            corr = pivot_df.corr()
            st.markdown("### 🔥 Correlation Heatmap")
            fig2, ax2 = plt.subplots(figsize=(8, 6))
            sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
            st.pyplot(fig2)
