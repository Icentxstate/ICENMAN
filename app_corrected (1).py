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

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------------- Load and unzip data ----------------
csv_zip_path = "columns_kept.zip"
shp_zip_path = "filtered_11_counties.zip"

csv_folder = "unzipped_csvs"
shp_folder = "unzipped_shapefile"

if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip_path, "r") as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip_path, "r") as zip_ref:
        zip_ref.extractall(shp_folder)

# ---------------- Load CSVs ----------------
all_data = []
for root, _, files in os.walk(csv_folder):
    for file in files:
        if file.endswith(".csv"):
            df = pd.read_csv(os.path.join(root, file), low_memory=False)
            df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
            df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
            all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV files found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)
required_cols = ["ActivityStartDate", "CharacteristicName", "ResultMeasureValue", "MonitoringLocationIdentifier"]
missing_cols = [col for col in required_cols if col not in combined_df.columns]
if missing_cols:
    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
    st.stop()

combined_df = combined_df.dropna(subset=required_cols)
combined_df["ResultMeasureValue"] = pd.to_numeric(combined_df["ResultMeasureValue"], errors='coerce')

# ---------------- Load Shapefile ----------------
shapefile_path = None
for file in os.listdir(shp_folder):
    if file.endswith(".shp"):
        shapefile_path = os.path.join(shp_folder, file)
        break

if shapefile_path is None:
    st.error("❌ No shapefile found in unzipped folder.")
    st.stop()

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# ---------------- Select Parameter ----------------
st.sidebar.header("🧪 Select Parameter to Show on Map")
available_params = combined_df["CharacteristicName"].dropna().unique()
selected_map_param = st.sidebar.selectbox("Parameter", sorted(available_params))

# ---------------- Summarize Station Info ----------------
station_info = {}
for station_id, group in combined_df.groupby("MonitoringLocationIdentifier"):
    lat = group["ActivityLocation/LatitudeMeasure"].iloc[0]
    lon = group["ActivityLocation/LongitudeMeasure"].iloc[0]

    latest_val = group[group["CharacteristicName"] == selected_map_param].sort_values("ActivityStartDate")["ResultMeasureValue"].dropna()
    latest_val = latest_val.iloc[-1] if not latest_val.empty else None

    param_summary = []
    for param, pgroup in group.groupby("CharacteristicName"):
        dates = pgroup["ActivityStartDate"].sort_values()
        if dates.empty:
            continue
        gap_count = len(dates.diff().dt.days.dropna()[lambda x: x > 30])
        param_summary.append({
            "Parameter": param,
            "FirstDate": dates.min().strftime("%Y-%m"),
            "LastDate": dates.max().strftime("%Y-%m"),
            "TimeGaps": f"{gap_count}"
        })

    station_info[station_id] = {
        "lat": lat,
        "lon": lon,
        "latest_value": latest_val,
        "params": param_summary
    }

# ---------------- Draw Map ----------------
st.subheader("🗺️ Monitoring Stations Map")
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron")

folium.GeoJson(gdf, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 2,
    "fillOpacity": 0.4
}).add_to(m)

for sid, info in station_info.items():
    size = info["latest_value"] if info["latest_value"] is not None else 2
    popup_html = f"<b>Station ID:</b> {sid}<br><b>{selected_map_param} (latest):</b> {size:.2f if size else 'N/A'}"
    folium.CircleMarker(
        location=[info["lat"], info["lon"]],
        radius=min(max(size, 2), 20),
        color="blue",
        fill=True,
        fill_opacity=0.7,
        popup=folium.Popup(popup_html, max_width=300)
    ).add_to(m)

st_data = st_folium(m, width=1300, height=600)

# ---------------- Clicked Station Details ----------------
clicked_lat = None
clicked_lon = None

if st_data and isinstance(st_data.get("last_object_clicked"), dict):
    clicked_lat = st_data["last_object_clicked"].get("lat")
    clicked_lon = st_data["last_object_clicked"].get("lng")

    # Find closest station
    selected_station = None
    for sid, info in station_info.items():
        if abs(info["lat"] - clicked_lat) < 1e-4 and abs(info["lon"] - clicked_lon) < 1e-4:
            selected_station = sid
            break

    if selected_station:
        st.subheader(f"📍 Selected Station: `{selected_station}`")

        df_station = combined_df[combined_df["MonitoringLocationIdentifier"] == selected_station]
        param_options = df_station["CharacteristicName"].unique()
        selected_params = st.multiselect("📊 Select parameters for time series + correlation", options=sorted(param_options), default=[selected_map_param])

        if selected_params:
            plot_df = df_station[df_station["CharacteristicName"].isin(selected_params)]
            pivot_df = plot_df.pivot(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue").sort_index()

            st.line_chart(pivot_df)

            st.markdown("### 📈 Descriptive Statistics")
            st.dataframe(pivot_df.describe().T)

            st.markdown("### 🔥 Correlation Heatmap")
            corr = pivot_df.corr()
            fig, ax = plt.subplots(figsize=(8, 6))
            sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)
            st.pyplot(fig)
