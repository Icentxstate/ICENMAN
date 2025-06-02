import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from streamlit_folium import st_folium
from folium.plugins import FloatImage

# --- Setup ---
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# --- Paths ---
csv_zip = "/mnt/data/columns_kept.zip"
shp_zip = "/mnt/data/filtered_11_counties.zip"
csv_folder = "csv_extracted"
shp_folder = "shp_extracted"

# --- Unzip data ---
if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# --- Load CSVs ---
csv_subfolders = [os.path.join(csv_folder, d) for d in os.listdir(csv_folder) if os.path.isdir(os.path.join(csv_folder, d))]
csv_files = []
for folder in csv_subfolders:
    csv_files += [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".csv")]

dataframes = []
for file in csv_files:
    try:
        df = pd.read_csv(file, low_memory=False)
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
        df = df.dropna(subset=["ActivityStartDate", "CharacteristicName", "ResultMeasureValue"])
        df = df[["MonitoringLocationIdentifier", "ActivityStartDate", "CharacteristicName", "ResultMeasureValue",
                 "ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"]]
        dataframes.append(df)
    except Exception as e:
        st.warning(f"❌ Failed to load {file}: {e}")

if not dataframes:
    st.error("❌ No valid CSV data found.")
    st.stop()

df_all = pd.concat(dataframes, ignore_index=True)

# --- Pivot for latest value per station/param ---
latest = df_all.sort_values("ActivityStartDate").groupby(
    ["MonitoringLocationIdentifier", "CharacteristicName"]
).last().reset_index()

# --- Load shapefile ---
shp_files = [f for f in os.listdir(shp_folder) if f.endswith(".shp")]
if not shp_files:
    st.error("❌ No shapefile found.")
    st.stop()
shapefile_path = os.path.join(shp_folder, shp_files[0])
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# --- Sidebar selection ---
selected_param = st.sidebar.selectbox("Select parameter to visualize on map", df_all["CharacteristicName"].unique())

# --- Map ---
m = folium.Map(location=[28.5, -96.5], zoom_start=7, control_scale=True)

# Add shapefile layer
folium.GeoJson(gdf.__geo_interface__, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 1,
    "fillOpacity": 0.1,
}).add_to(m)

# Draw circles for selected param
param_df = latest[latest["CharacteristicName"] == selected_param]
for _, row in param_df.iterrows():
    val = row["ResultMeasureValue"]
    if pd.notnull(val):
        folium.CircleMarker(
            location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
            radius=max(3, min(float(val) / 10, 12)),
            color="blue",
            fill=True,
            fill_opacity=0.6,
            popup=f"{row['MonitoringLocationIdentifier']}<br>{val}"
        ).add_to(m)

st_data = st_folium(m, width=1200, height=600)

# --- User click handler ---
if st_data.get("last_object_clicked"):
    lat = st_data["last_object_clicked"]["lat"]
    lon = st_data["last_object_clicked"]["lng"]
    st.session_state["clicked_coords"] = (lat, lon)

if "clicked_coords" in st.session_state:
    lat, lon = st.session_state["clicked_coords"]
    st.subheader("📍 Selected Station")
    st.write(f"**Latitude**: {lat:.5f}, **Longitude**: {lon:.5f}")

    if st.button("Run"):
        # Filter by location
        tol = 1e-4
        nearby = df_all[
            (abs(df_all["ActivityLocation/LatitudeMeasure"] - lat) < tol) &
            (abs(df_all["ActivityLocation/LongitudeMeasure"] - lon) < tol)
        ]

        if nearby.empty:
            st.warning("No data found for the selected station.")
        else:
            st.markdown("### 📊 Time Series and Analysis")

            # Multiselect
            selected_params = st.multiselect("Select parameters to plot", nearby["CharacteristicName"].unique(),
                                             default=[selected_param])

            plot_df = nearby[nearby["CharacteristicName"].isin(selected_params)]
            if not plot_df.empty:
                # --- Time Series Plot ---
                fig, ax = plt.subplots(figsize=(10, 4))
                for param in selected_params:
                    sub = plot_df[plot_df["CharacteristicName"] == param]
                    ax.plot(sub["ActivityStartDate"], sub["ResultMeasureValue"], label=param)
                ax.set_title("Time Series of Selected Parameters")
                ax.set_ylabel("Value")
                ax.set_xlabel("Date")
                ax.legend()
                ax.grid(True)
                ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b-%Y"))
                st.pyplot(fig)

                # --- Stats Table ---
                stats = plot_df.groupby("CharacteristicName")["ResultMeasureValue"].describe().round(2)
                st.dataframe(stats)

                # --- Correlation Heatmap ---
                pivot = plot_df.pivot_table(
                    index="ActivityStartDate",
                    columns="CharacteristicName",
                    values="ResultMeasureValue"
                ).dropna()
                if len(pivot.columns) > 1:
                    corr = pivot.corr()
                    fig2, ax2 = plt.subplots(figsize=(6, 4))
                    sns.heatmap(corr, annot=True, cmap="coolwarm", fmt=".2f", ax=ax2)
                    st.pyplot(fig2)
