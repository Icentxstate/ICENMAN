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

# ---------- Page Config ----------
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------- Unzip Data ----------
@st.cache_data
def unzip_data(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

# Assume zip files are already uploaded into the directory
csv_zip_path = "columns_kept.zip"
shp_zip_path = "filtered_11_counties.zip"
csv_folder = "columns_kept"
shp_folder = "filtered_11_counties"

unzip_data(csv_zip_path, csv_folder)
unzip_data(shp_zip_path, shp_folder)

# ---------- Load CSV Data ----------
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
        all_data.append(df)
    except Exception as e:
        st.warning(f"❌ Error loading {file}: {e}")

if not all_data:
    st.error("❌ No valid CSV data loaded.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# Optional: Fill missing organization names
org_map = {
    "TCEQMAIN": "Texas Commission on Environmental Quality",
    "NALMS": "North American Lake Management Society",
    "NARS_WQX": "EPA National Aquatic Resources Survey (NARS)",
    "TXSTRMTM_WQX": "Texas Stream Team",
    "11NPSWRD_WQX": "National Park Service Water Resources Division",
    "OST_SHPD": "USEPA, Office of Science and Technology"
}
combined_df["OrganizationFormalName"] = combined_df["OrganizationFormalName"].fillna(
    combined_df["OrganizationIdentifier"].map(org_map))

# Add Station Key for clarity
combined_df["StationKey"] = combined_df["ActivityLocation/LatitudeMeasure"].round(5).astype(str) + "," + combined_df["ActivityLocation/LongitudeMeasure"].round(5).astype(str)

# ---------- Load Shapefile ----------
shapefile_path = None
for file in os.listdir(shp_folder):
    if file.endswith(".shp"):
        shapefile_path = os.path.join(shp_folder, file)
        break
if not shapefile_path:
    st.error("❌ No shapefile found.")
    st.stop()

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# ---------- Select Main Parameter ----------
st.sidebar.header("🧪 Parameter for Map Visualization")
main_param = st.sidebar.selectbox("Select parameter for circle sizing:", sorted(combined_df["CharacteristicName"].dropna().unique()))

# ---------- Latest Value per Station ----------
latest_df = combined_df[combined_df["CharacteristicName"] == main_param]
latest_df = latest_df.sort_values("ActivityStartDate").dropna(subset=["ResultMeasureValue"])
latest_df = latest_df.groupby("StationKey").tail(1)

# ---------- Map ----------
st.subheader("🗺️ Monitoring Stations Map")
map_center = [latest_df["ActivityLocation/LatitudeMeasure"].mean(), latest_df["ActivityLocation/LongitudeMeasure"].mean()]
m = folium.Map(location=map_center, zoom_start=7, tiles="CartoDB positron")

# Shapefile Layer
folium.GeoJson(
    gdf,
    style_function=lambda x: {"fillColor": "#0b5394", "color": "#0b5394", "weight": 2, "fillOpacity": 0.3},
).add_to(m)

# Monitoring Stations
for _, row in latest_df.iterrows():
    val = row["ResultMeasureValue"]
    popup = f"<b>{main_param}</b>: {val:.2f}<br>{row['StationKey']}"
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=min(max(val, 2), 20),  # Size based on value
        color="blue",
        fill=True,
        fill_opacity=0.7,
        popup=folium.Popup(popup, max_width=250),
    ).add_to(m)

st_data = st_folium(m, height=600, width=1300)

# ---------- Chart Section ----------
clicked_lat = None
clicked_lon = None
if st_data and isinstance(st_data.get("last_object_clicked"), dict):
    clicked_lat = round(st_data["last_object_clicked"].get("lat", 0), 5)
    clicked_lon = round(st_data["last_object_clicked"].get("lng", 0), 5)

if clicked_lat and clicked_lon:
    st.markdown("### 📍 Selected Station")
    coords_str = f"{clicked_lat},{clicked_lon}"
    st.write(f"Coordinates: `{coords_str}`")

    station_df = combined_df[combined_df["StationKey"] == coords_str]
    available_station_params = sorted(station_df["CharacteristicName"].dropna().unique())

    selected_params = st.multiselect("Select parameter(s) to plot", available_station_params, default=[main_param] if main_param in available_station_params else [])

    if st.button("📊 نمایش گراف و ماتریس همبستگی") and selected_params:
        df_station = station_df[station_df["CharacteristicName"].isin(selected_params)]

        if df_station.empty:
            st.info("No data available for this location and parameters.")
        else:
            st.subheader(f"📈 Time Series at {coords_str}")
            df_pivot = df_station.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            df_pivot = df_pivot.sort_index()

            st.markdown(f"⏳ Range: **{df_pivot.index.min().strftime('%b %Y')}** → **{df_pivot.index.max().strftime('%b %Y')}**")

            # Time series
            fig, ax = plt.subplots(figsize=(10, 4))
            df_pivot.plot(ax=ax)
            ax.set_ylabel("Measurement Value")
            ax.set_xlabel("Date")
            ax.set_title("Time Series of Selected Parameters")
            ax.grid(True)
            ax.set_xticks(pd.date_range(df_pivot.index.min(), df_pivot.index.max(), freq="3MS"))
            ax.set_xticklabels([d.strftime("%b %Y") for d in pd.date_range(df_pivot.index.min(), df_pivot.index.max(), freq="3MS")], rotation=45)
            st.pyplot(fig)

            # Summary
            st.markdown("📋 Statistical Summary")
            st.dataframe(df_pivot.describe().T.style.format("{:.2f}"))

            # Correlation Heatmap
            st.markdown("📊 Correlation Heatmap")
            corr = df_pivot.corr()
            fig2, ax2 = plt.subplots(figsize=(5, 4))
            sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax2)
            ax2.set_title("Correlation Between Parameters")
            st.pyplot(fig2)
