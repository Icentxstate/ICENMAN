import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import os
import zipfile
import matplotlib.pyplot as plt
import seaborn as sns
import json

# --- Page Config ---
st.set_page_config(layout="wide")
st.title("📍 Interactive Water Quality Explorer")

# --- Extract ZIPs if needed ---
csv_zip = "kept.zip"
shp_zip = "filtered_11_counties.zip"
csv_folder = "csv_extracted/filtered_columns_kept"
shp_folder = "shapefile_extracted"

if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip, 'r') as zip_ref:
        zip_ref.extractall("csv_extracted")

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# --- Load Shapefile ---
shapefile_path = [f for f in os.listdir(shp_folder) if f.endswith(".shp")][0]
gdf_boundary = gpd.read_file(os.path.join(shp_folder, shapefile_path))

# Check shapefile validity
if gdf_boundary.empty:
    st.error("❌ Shapefile is empty or not loaded correctly.")
    st.stop()

# --- Load CSVs ---
csv_path = os.path.join("csv_extracted", "filtered_columns_kept")
csv_files = [os.path.join(csv_path, f) for f in os.listdir(csv_path) if f.endswith(".csv")]
df_all = pd.concat([pd.read_csv(f) for f in csv_files], ignore_index=True)
df_all = df_all.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
df_all["ActivityStartDate"] = pd.to_datetime(df_all["ActivityStartDate"], errors='coerce')
df_all["ResultMeasureValue"] = pd.to_numeric(df_all["ResultMeasureValue"], errors='coerce')

# --- Get Latest Values per Location/Parameter ---
latest = df_all.sort_values("ActivityStartDate").groupby(["MonitoringLocationIdentifier", "CharacteristicName"]).last().reset_index()

# --- Build Station Summary ---
station_info = {}
for station in latest["MonitoringLocationIdentifier"].unique():
    sub = latest[latest["MonitoringLocationIdentifier"] == station]
    summary = "".join([f"<li>{p}: {round(v,2)} {u}</li>" for p, v, u in zip(sub["CharacteristicName"], sub["ResultMeasureValue"], sub["ResultMeasure/MeasureUnitCode"])])
    coords = sub.iloc[0][["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"]].values
    station_info[station] = {"html": f"<ul>{summary}</ul>", "lat": coords[0], "lon": coords[1]}

# --- Map ---
m = folium.Map(location=[28.5, -96], zoom_start=7)

# Fix: convert to GeoJSON safely
geojson_data = json.loads(gdf_boundary.to_json())
folium.GeoJson(geojson_data, name="Boundary").add_to(m)

marker_cluster = MarkerCluster().add_to(m)
for station, info in station_info.items():
    folium.Marker(
        location=[info["lat"], info["lon"]],
        popup=folium.Popup(info["html"], max_width=300),
        tooltip=station
    ).add_to(marker_cluster)

st.markdown("### 🗺️ Monitoring Stations")
map_data = st_folium(m, height=500, returned_objects=["last_object_clicked"], key="map")

# --- Toolbar ---
clicked_station = map_data.get("last_object_clicked")
if clicked_station:
    lat, lon = clicked_station["lat"], clicked_station["lng"]
    selected = df_all[(df_all["ActivityLocation/LatitudeMeasure"] == lat) & (df_all["ActivityLocation/LongitudeMeasure"] == lon)]
    station_id = selected["MonitoringLocationIdentifier"].iloc[0]

    st.markdown(f"### 📌 Selected Station: `{station_id}`")

    parameters = selected["CharacteristicName"].unique().tolist()
    selected_params = st.multiselect("Choose Parameters", parameters, default=parameters[:1])

    if selected_params:
        fig, ax = plt.subplots(figsize=(12, 5))
        for param in selected_params:
            subset = selected[selected["CharacteristicName"] == param].sort_values("ActivityStartDate")
            ax.plot(subset["ActivityStartDate"], subset["ResultMeasureValue"], label=param)
        ax.set_title(f"Time Series at {station_id}")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value")
        ax.legend()
        st.pyplot(fig)

        # --- Correlation Heatmap ---
        pivot = selected[selected["CharacteristicName"].isin(selected_params)].pivot_table(
            index="ActivityStartDate",
            columns="CharacteristicName",
            values="ResultMeasureValue"
        )
        corr = pivot.corr()
        st.markdown("#### 🔍 Correlation Heatmap")
        fig_corr, ax_corr = plt.subplots(figsize=(8, 6))
        sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax_corr)
        st.pyplot(fig_corr)
else:
    st.info("Click on a point on the map to begin analysis.")
