import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
from folium.plugins import FloatImage
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------- Paths ----------
csv_zip_path = "columns_kept.zip"
shp_zip_path = "filtered_11_counties.zip"
csv_folder = "csv_data"
shp_folder = "shapefile_data"

# ---------- Unzip CSV and Shapefile ----------
if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip_path, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip_path, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# ---------- Load and Combine CSVs ----------
csv_files = []
for root, dirs, files in os.walk(csv_folder):
    for file in files:
        if file.endswith(".csv"):
            csv_files.append(os.path.join(root, file))

all_data = []
for file in csv_files:
    df = pd.read_csv(file, low_memory=False)
    if {'LatitudeMeasure', 'LongitudeMeasure', 'ActivityStartDate', 'CharacteristicName', 'ResultMeasureValue'}.issubset(df.columns):
        df = df.dropna(subset=['LatitudeMeasure', 'LongitudeMeasure', 'ActivityStartDate', 'CharacteristicName', 'ResultMeasureValue'])
        df['ActivityStartDate'] = pd.to_datetime(df['ActivityStartDate'], errors='coerce')
        df['ResultMeasureValue'] = pd.to_numeric(df['ResultMeasureValue'], errors='coerce')
        all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# ---------- Load and Clean Shapefile ----------
shapefile_path = None
for file in os.listdir(shp_folder):
    if file.endswith(".shp"):
        shapefile_path = os.path.join(shp_folder, file)
        break

if shapefile_path is None:
    st.error("❌ No shapefile found in the provided folder.")
    st.stop()

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)
gdf = gdf[gdf.geometry.notnull()]

# ---------- Sidebar Parameter Selection ----------
st.sidebar.header("🔎 Map Display Parameter")
map_param = st.sidebar.selectbox("Select a parameter to show on the map", combined_df["CharacteristicName"].unique())

# ---------- Build Map ----------
st.subheader("🗺️ Interactive Monitoring Map")
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron")

folium.GeoJson(
    gdf,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.4,
    }
).add_to(m)

# Aggregate latest values by coordinate
latest_df = combined_df[combined_df["CharacteristicName"] == map_param].copy()
latest_df = latest_df.sort_values("ActivityStartDate").dropna(subset=["ResultMeasureValue"])
latest_df = latest_df.groupby(['LatitudeMeasure', 'LongitudeMeasure']).tail(1)

for _, row in latest_df.iterrows():
    val = row['ResultMeasureValue']
    folium.CircleMarker(
        location=[row['LatitudeMeasure'], row['LongitudeMeasure']],
        radius=5 + min(10, val / 10),
        color="blue",
        fill=True,
        fill_opacity=0.7,
        popup=f"{map_param}: {val:.2f}"
    ).add_to(m)

# Display Map
st_data = st_folium(m, width=1300, height=600)

# ---------- Interaction Section ----------
clicked_lat = st_data.get("last_object_clicked", {}).get("lat")
clicked_lon = st_data.get("last_object_clicked", {}).get("lng")

if clicked_lat and clicked_lon:
    st.subheader("📍 Selected Station")
    st.write(f"**Coordinates:** ({clicked_lat:.5f}, {clicked_lon:.5f})")

    st.markdown("---")
    st.subheader("📊 Time Series and Analysis")
    
    nearby_df = combined_df[
        (combined_df['LatitudeMeasure'] - clicked_lat).abs() < 1e-4 &
        (combined_df['LongitudeMeasure'] - clicked_lon).abs() < 1e-4
    ]

    param_options = nearby_df['CharacteristicName'].dropna().unique()
    selected_params = st.multiselect("Select parameters to plot:", param_options, default=[map_param])

    if selected_params:
        plot_df = nearby_df[nearby_df['CharacteristicName'].isin(selected_params)]

        # Line Chart
        st.write("### 📈 Time Series")
        fig, ax = plt.subplots(figsize=(10, 4))
        for param in selected_params:
            subset = plot_df[plot_df['CharacteristicName'] == param].sort_values("ActivityStartDate")
            ax.plot(subset["ActivityStartDate"], subset["ResultMeasureValue"], label=param)
        ax.set_title("Time Series by Parameter")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value")
        ax.legend()
        ax.grid(True)
        fig.autofmt_xdate()
        st.pyplot(fig)

        # Correlation Heatmap
        pivot_df = plot_df.pivot_table(index='ActivityStartDate', columns='CharacteristicName', values='ResultMeasureValue')
        corr = pivot_df[selected_params].corr()
        st.write("### 🔥 Correlation Heatmap")
        fig2, ax2 = plt.subplots(figsize=(6, 5))
        sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
        st.pyplot(fig2)

        # Summary Stats
        st.write("### 📋 Statistical Summary")
        st.dataframe(plot_df.groupby("CharacteristicName")["ResultMeasureValue"].describe())
