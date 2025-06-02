import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import os
import matplotlib.pyplot as plt
import seaborn as sns
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from datetime import datetime

# --- Page Config ---
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Water Quality Monitoring Dashboard")

# --- File Paths ---
csv_folder = "/mnt/data/kept_extracted/filtered_columns_kept"
shapefile_folder = "/mnt/data/shapefile_extracted"

# --- Load Shapefile ---
shapefile_path = None
for file in os.listdir(shapefile_folder):
    if file.endswith(".shp"):
        shapefile_path = os.path.join(shapefile_folder, file)
        break

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# --- Load CSV files ---
csv_files = [f for f in os.listdir(csv_folder) if f.endswith(".csv")]
all_data = []
for file in csv_files:
    df = pd.read_csv(os.path.join(csv_folder, file), low_memory=False)
    df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "CharacteristicName", "ActivityStartDate"])
    df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
    all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# --- Sidebar: Parameter Selection ---
st.sidebar.header("Parameter for Map Visualization")
parameter_for_map = st.sidebar.selectbox("Select a parameter to display on map:", combined_df["CharacteristicName"].unique())

# --- Latest Value per Site for Selected Parameter ---
latest = combined_df[combined_df["CharacteristicName"] == parameter_for_map].sort_values("ActivityStartDate")
latest = latest.groupby(["MonitoringLocationIdentifier"]).last().reset_index()

# --- Create Map ---
m = folium.Map(location=[28.5, -96.5], zoom_start=7, control_scale=True)

# Add shapefile boundary
folium.GeoJson(
    gdf,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.1,
    }
).add_to(m)

# --- Add Station Markers ---
marker_cluster = MarkerCluster().add_to(m)
for idx, row in latest.iterrows():
    lat = row["ActivityLocation/LatitudeMeasure"]
    lon = row["ActivityLocation/LongitudeMeasure"]
    value = row["ResultMeasureValue"]
    loc_id = row["MonitoringLocationIdentifier"]
    folium.CircleMarker(
        location=[lat, lon],
        radius=5 + (float(value) if pd.notnull(value) else 0)/5,
        popup=f"<b>Station:</b> {loc_id}<br><b>Latest {parameter_for_map}:</b> {value}",
        color="blue",
        fill=True,
        fill_opacity=0.6
    ).add_to(marker_cluster)

# --- Interactive Map ---
st_data = st_folium(m, width=1200, height=600)

# --- Extract Clicked Coordinates ---
if st_data and st_data.get("last_clicked"):
    coords = st_data["last_clicked"]
    lat_clicked = coords.get("lat")
    lon_clicked = coords.get("lng")

    st.subheader("📈 Selected Station Time Series")

    # Match nearest station by coordinates
    combined_df["coord_dist"] = ((combined_df["ActivityLocation/LatitudeMeasure"] - lat_clicked)**2 + (combined_df["ActivityLocation/LongitudeMeasure"] - lon_clicked)**2)
    nearest_station = combined_df.loc[combined_df["coord_dist"].idxmin()]
    selected_id = nearest_station["MonitoringLocationIdentifier"]

    # --- Multiselect Parameters ---
    st.markdown(f"**Selected Station:** `{selected_id}`")
    param_options = combined_df[combined_df["MonitoringLocationIdentifier"] == selected_id]["CharacteristicName"].unique()
    selected_params = st.multiselect("Select parameters to plot:", options=param_options.tolist(), default=[parameter_for_map])

    fig, ax = plt.subplots(figsize=(10, 4))
    for param in selected_params:
        subset = combined_df[(combined_df["MonitoringLocationIdentifier"] == selected_id) & (combined_df["CharacteristicName"] == param)]
        subset = subset.sort_values("ActivityStartDate")
        ax.plot(subset["ActivityStartDate"], subset["ResultMeasureValue"], label=param)

    ax.set_title("Time Series Plot")
    ax.set_xlabel("Date")
    ax.set_ylabel("Value")
    ax.legend()
    fig.autofmt_xdate()
    st.pyplot(fig)

    # --- Correlation Heatmap ---
    corr_df = combined_df[(combined_df["MonitoringLocationIdentifier"] == selected_id) & (combined_df["CharacteristicName"].isin(selected_params))]
    pivot = corr_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
    corr_matrix = pivot.corr()

    st.subheader("🔍 Correlation Heatmap")
    fig2, ax2 = plt.subplots()
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", ax=ax2)
    st.pyplot(fig2)
