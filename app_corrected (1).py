import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import glob
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# --- Paths ---
csv_zip = "columns_kept.zip"
shp_zip = "filtered_11_counties.zip"
csv_folder = "csv_extracted"
shp_folder = "shp_extracted"

# --- Unzip files ---
if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

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

# --- Clean ---
required_cols = ["ActivityStartDate", "CharacteristicName", "ResultMeasureValue"]
missing = [col for col in required_cols if col not in df.columns]
if missing:
    st.error(f"❌ Missing required columns: {', '.join(missing)}")
    st.stop()

df = df.dropna(subset=required_cols)
df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')

# --- Org Mapping ---
org_lookup = {
    "TCEQMAIN": "Texas Commission on Environmental Quality",
    "NALMS": "North American Lake Management Society",
    "NARS_WQX": "EPA National Aquatic Resources Survey (NARS)",
    "TXSTRMTM_WQX": "Texas Stream Team",
    "11NPSWRD_WQX": "National Park Service Water Resources Division",
    "OST_SHPD": "USEPA Office of Science and Technology"
}
df["OrganizationFormalName"] = df["OrganizationIdentifier"].map(org_lookup).fillna("Unknown")
df["StationKey"] = df["ActivityLocation/LatitudeMeasure"].astype(str) + "," + df["ActivityLocation/LongitudeMeasure"].astype(str)

# --- Param Selection ---
available_params = sorted(df["CharacteristicName"].dropna().unique())
selected_params = st.multiselect("📌 Select Water Quality Parameter(s)", available_params, default=[available_params[0]])
if not selected_params:
    st.stop()

# --- Filtered Data ---
filtered_df = df[df["CharacteristicName"].isin(selected_params)]

# --- Last Value Per Station ---
latest_values = (
    filtered_df.sort_values("ActivityStartDate")
    .groupby(["StationKey", "CharacteristicName"])
    .tail(1)
    .sort_values("ActivityStartDate")
    .drop_duplicates("StationKey", keep="last")
    .set_index("StationKey")
)

# --- Shapefile ---
shp_files = glob.glob(os.path.join(shp_folder, "**", "*.shp"), recursive=True)
gdf = gpd.read_file(shp_files[0]).to_crs(epsg=4326)
gdf["geometry"] = gdf["geometry"]

# --- Map ---
st.subheader(f"🗺️ Map of Latest {', '.join(selected_params)} Measurements")
map_center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[map_center.y, map_center.x], zoom_start=7, tiles="CartoDB positron")

folium.GeoJson(
    gdf,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.3,
    },
).add_to(m)

for key, row in latest_values.iterrows():
    lat, lon = map(float, key.split(","))
    val = row["ResultMeasureValue"]
    color = "#007849"
    popup_html = f"""
    <b>Location:</b> {key}<br>
    <b>{row['CharacteristicName']}:</b> {val:.2f}<br>
    <b>Date:</b> {row['ActivityStartDate'].strftime('%b %Y')}
    """
    folium.CircleMarker(
        location=[lat, lon],
        radius=5 + min(max(val, 0), 100)**0.5,
        color=color,
        fill=True,
        fill_opacity=0.85,
        popup=folium.Popup(popup_html, max_width=300),
    ).add_to(m)

st_data = st_folium(m, width=1300, height=600)

# --- Toolbar & Graph ---
clicked_lat = None
clicked_lon = None

if st_data and isinstance(st_data.get("last_object_clicked"), dict):
    clicked_lat = st_data["last_object_clicked"].get("lat")
    clicked_lon = st_data["last_object_clicked"].get("lng")

if clicked_lat and clicked_lon:
    st.markdown("### 📍 Selected Station")
    coords_str = f"{clicked_lat:.5f},{clicked_lon:.5f}"
    st.write(f"Coordinates: `{coords_str}`")

    if st.button("📊 نمایش گراف و ماتریس همبستگی"):
        key = coords_str
        df_station = df[(df["StationKey"] == key) & (df["CharacteristicName"].isin(selected_params))]
        if df_station.empty:
            st.info("No data available for this location.")
        else:
            st.subheader(f"📈 Time Series at {coords_str}")
            df_pivot = df_station.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            df_pivot = df_pivot.sort_index()

            # نمایش بازه زمانی
            st.markdown(f"⏳ Range: **{df_pivot.index.min().strftime('%b %Y')}** → **{df_pivot.index.max().strftime('%b %Y')}**")

            # سری زمانی با فرمت ماه-سال
            fig, ax = plt.subplots(figsize=(10, 4))
            df_pivot.plot(ax=ax)
            ax.set_ylabel("Measurement Value")
            ax.set_xlabel("Date")
            ax.set_title("Time Series of Selected Parameters")
            ax.legend(loc='best')
            ax.grid(True)
            ax.set_xticks(pd.date_range(df_pivot.index.min(), df_pivot.index.max(), freq="3MS"))
            ax.set_xticklabels([d.strftime("%b %Y") for d in pd.date_range(df_pivot.index.min(), df_pivot.index.max(), freq="3MS")], rotation=45)
            st.pyplot(fig)

            # جدول آماری
            st.markdown("📋 Statistical Summary")
            st.dataframe(df_pivot.describe().T.style.format("{:.2f}"))

            # ماتریس همبستگی
            st.markdown("📊 Correlation Heatmap")
            corr = df_pivot.corr()
            fig2, ax2 = plt.subplots(figsize=(5, 4))
            sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax2)
            ax2.set_title("Correlation Between Parameters")
            st.pyplot(fig2)
