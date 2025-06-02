import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import glob
import numpy as np
import matplotlib.colors as mcolors
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

# --- Basic Clean ---
required_cols = ["ActivityStartDate", "CharacteristicName", "ResultMeasureValue"]
missing = [col for col in required_cols if col not in df.columns]
if missing:
    st.error(f"❌ Missing required columns: {', '.join(missing)}")
    st.stop()

df = df.dropna(subset=required_cols)
df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')

# --- Organization Mapping ---
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

# --- Parameter Selector ---
available_params = sorted(df["CharacteristicName"].dropna().unique())
selected_param = st.selectbox("📌 Select a Water Quality Parameter", available_params)

# --- Filter by selected parameter ---
filtered_df = df[df["CharacteristicName"] == selected_param]

# --- Last Value Per Station ---
latest_values = (
    filtered_df.sort_values("ActivityStartDate")
    .groupby("StationKey")
    .tail(1)
    .set_index("StationKey")
)

# --- Load shapefile ---
shp_files = glob.glob(os.path.join(shp_folder, "**", "*.shp"), recursive=True)
if not shp_files:
    st.error("❌ No shapefile found.")
    st.stop()

gdf = gpd.read_file(shp_files[0]).to_crs(epsg=4326)
gdf_safe = gdf[[col for col in gdf.columns if gdf[col].dtype.kind in 'ifO']].copy()
gdf_safe["geometry"] = gdf["geometry"]

# --- Organization colors ---
orgs = df["OrganizationFormalName"].dropna().unique()
color_palette = list(mcolors.TABLEAU_COLORS.values()) + list(mcolors.CSS4_COLORS.values())
org_colors = {org: color_palette[i % len(color_palette)] for i, org in enumerate(orgs)}

# --- Map ---
st.subheader(f"🗺️ Map of Latest {selected_param} Measurements")
map_center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[map_center.y, map_center.x], zoom_start=7, tiles="CartoDB positron")

# Add counties
folium.GeoJson(
    gdf_safe,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.3,
    },
).add_to(m)

# Add points
for key, row in latest_values.iterrows():
    lat, lon = row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]
    val = row["ResultMeasureValue"]
    org = row["OrganizationFormalName"]
    color = org_colors.get(org, "gray")
    popup_html = f"""
    <b>Location:</b> {key}<br>
    <b>Org:</b> {org}<br>
    <b>{selected_param}:</b> {val:.2f}<br>
    <b>Date:</b> {row['ActivityStartDate'].strftime('%Y-%m-%d')}
    """
    folium.CircleMarker(
        location=[lat, lon],
        radius=5 + min(max(val, 0), 100) ** 0.5,  # scale radius
        color=color,
        fill=True,
        fill_opacity=0.8,
        popup=folium.Popup(popup_html, max_width=300),
    ).add_to(m)

# Add Legend
legend_html = """
<div style='position: fixed; bottom: 50px; left: 50px; z-index:9999; background:white; padding:10px; border:1px solid #ccc'>
<b>Organization Legend</b><br>
"""
for org, color in org_colors.items():
    legend_html += f"<span style='display:inline-block;width:12px;height:12px;background:{color};margin-right:5px'></span>{org}<br>"
legend_html += "</div>"
m.get_root().html.add_child(folium.Element(legend_html))

# Show map
st_data = st_folium(m, width=1300, height=600)

# --- Toolbar below map ---
clicked_lat = None
clicked_lon = None
if st_data and "last_object_clicked" in st_data:
    clicked_lat = st_data["last_object_clicked"].get("lat")
    clicked_lon = st_data["last_object_clicked"].get("lng")

if clicked_lat and clicked_lon:
    st.markdown("---")
    st.markdown("### 🧪 Selected Station")
    coords_str = f"{clicked_lat:.5f}, {clicked_lon:.5f}"
    st.write(f"📍 Coordinates: `{coords_str}`")
    
    if st.button("📈 نمایش گراف و آمار"):
        clicked_key = f"{clicked_lat},{clicked_lon}"
        ts_df = filtered_df[filtered_df["StationKey"] == clicked_key].sort_values("ActivityStartDate")
        if not ts_df.empty:
            st.subheader(f"📈 Time Series for {selected_param} at {coords_str}")

            # ⏳ Show time range
            date_min = ts_df["ActivityStartDate"].min().strftime("%Y-%m-%d")
            date_max = ts_df["ActivityStartDate"].max().strftime("%Y-%m-%d")
            st.markdown(f"🗓️ Data available from **{date_min}** to **{date_max}**")

            # 📉 Line chart
            st.line_chart(ts_df.set_index("ActivityStartDate")["ResultMeasureValue"])

            # 📊 Summary stats
            st.markdown("📊 **Statistical Summary**")
            summary = ts_df["ResultMeasureValue"].describe().to_frame().T
            st.dataframe(summary.style.format("{:.2f}"))
        else:
            st.info("No time series available for this location.")
