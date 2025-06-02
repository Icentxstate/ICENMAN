import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import glob
import matplotlib.colors as mcolors
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------- Extract ZIP Files ----------
csv_zip = "columns_kept.zip"
shp_zip = "filtered_11_counties.zip"
csv_folder = "csv_extracted"
shp_folder = "shp_extracted"

if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# ---------- Load CSVs ----------
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

combined_df = pd.concat(all_data, ignore_index=True)

# ---------- Check Columns ----------
required_cols = ["ActivityStartDate", "CharacteristicName", "ResultMeasureValue"]
missing = [col for col in required_cols if col not in combined_df.columns]
if missing:
    st.error(f"❌ Missing required columns: {', '.join(missing)}")
    st.stop()

combined_df = combined_df.dropna(subset=required_cols)
combined_df["ResultMeasureValue"] = pd.to_numeric(combined_df["ResultMeasureValue"], errors='coerce')

# ---------- Map OrganizationIdentifier to names ----------
organization_lookup = {
    "TCEQMAIN": "Texas Commission on Environmental Quality",
    "NALMS": "North American Lake Management Society",
    "NARS_WQX": "EPA National Aquatic Resources Survey (NARS)",
    "TXSTRMTM_WQX": "Texas Stream Team",
    "11NPSWRD_WQX": "National Park Service Water Resources Division",
    "OST_SHPD": "USEPA Office of Science and Technology"
}
combined_df["OrganizationFormalName"] = combined_df["OrganizationIdentifier"].map(organization_lookup).fillna("Unknown")

# ---------- Define StationKey by lat/lon ----------
combined_df["StationKey"] = combined_df["ActivityLocation/LatitudeMeasure"].astype(str) + "," + combined_df["ActivityLocation/LongitudeMeasure"].astype(str)

# ---------- Load Shapefile Automatically ----------
shapefile_list = glob.glob(os.path.join(shp_folder, "**", "*.shp"), recursive=True)
if not shapefile_list:
    st.error("❌ No shapefile (.shp) found in ZIP.")
    st.stop()

shapefile_path = shapefile_list[0]
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# ---------- Clean gdf for JSON compatibility ----------
gdf_safe = gdf[[col for col in gdf.columns if gdf[col].dtype.kind in 'ifO']].copy()
gdf_safe["geometry"] = gdf["geometry"]

# ---------- Color by Organization ----------
orgs = combined_df["OrganizationFormalName"].dropna().unique()
color_palette = list(mcolors.TABLEAU_COLORS.values()) + list(mcolors.CSS4_COLORS.values())
org_colors = {org: color_palette[i % len(color_palette)] for i, org in enumerate(orgs)}

# ---------- Summarize Stations ----------
station_info = {}
for station_key, group in combined_df.groupby("StationKey"):
    lat = group["ActivityLocation/LatitudeMeasure"].iloc[0]
    lon = group["ActivityLocation/LongitudeMeasure"].iloc[0]
    orgs = group["OrganizationFormalName"].dropna().unique()
    org_display = orgs[0] if len(orgs) > 0 else "Unknown"
    org_color = org_colors.get(org_display, "gray")

    param_summary = []
    gap_total = 0
    for param, pgroup in group.groupby("CharacteristicName"):
        dates = pgroup["ActivityStartDate"].sort_values()
        if dates.empty:
            continue
        start = dates.min()
        end = dates.max()
        gaps = dates.diff().dt.days.dropna()
        gap_count = len(gaps[gaps > 30])
        gap_total += gap_count
        param_summary.append({
            "Parameter": param,
            "FirstDate": start.strftime("%Y-%m-%d"),
            "LastDate": end.strftime("%Y-%m-%d"),
            "TimeGaps": f"{gap_count}"
        })

    station_info[station_key] = {
        "lat": lat,
        "lon": lon,
        "organization": org_display,
        "params": param_summary,
        "color": org_color,
        "gap_total": gap_total
    }

# ---------- Map ----------
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron")

folium.GeoJson(
    gdf_safe,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.4,
    },
    tooltip=gdf_safe.columns[1] if len(gdf_safe.columns) > 1 else None
).add_to(m)

for key, info in station_info.items():
    table_html = "<table style='font-size: 12px'><tr><th>Parameter</th><th>First</th><th>Last</th><th>Gaps</th></tr>"
    for param in info["params"]:
        table_html += f"<tr><td>{param['Parameter']}</td><td>{param['FirstDate']}</td><td>{param['LastDate']}</td><td>{param['TimeGaps']}</td></tr>"
    table_html += "</table>"

    popup_html = f"""
    <div style='font-size:13px; max-height:300px; overflow:auto;'>
        <b>Location:</b> {key}<br>
        <b>Organization:</b> {info["organization"]}<br>
        <b>Total Gaps &gt;30d:</b> {info["gap_total"]}<br><br>
        {table_html}
    </div>
    """
    folium.CircleMarker(
        location=[info["lat"], info["lon"]],
        radius=7,
        color=info["color"],
        fill=True,
        fill_opacity=0.9,
        popup=folium.Popup(popup_html, max_width=500)
    ).add_to(m)

st_data = st_folium(m, width=1300, height=600)

# ---------- Click Plot ----------
clicked_key = None
if st_data and isinstance(st_data.get("last_object_clicked"), dict):
    clicked_lat = st_data["last_object_clicked"].get("lat")
    clicked_lng = st_data["last_object_clicked"].get("lng")
    clicked_key = f"{clicked_lat},{clicked_lng}"

if clicked_key and clicked_key in station_info:
    st.subheader(f"📈 Time Series for Station {clicked_key}")
    df_station = combined_df[combined_df["StationKey"] == clicked_key]
    selected_param = st.selectbox("Select parameter", df_station["CharacteristicName"].unique())
    chart_df = df_station[df_station["CharacteristicName"] == selected_param].sort_values("ActivityStartDate")
    st.line_chart(chart_df.set_index("ActivityStartDate")["ResultMeasureValue"])
