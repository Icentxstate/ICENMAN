import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import matplotlib.colors as mcolors
from streamlit_folium import st_folium
import gdown

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------- File Paths ----------
csv_zip_url = "https://drive.google.com/uc?id=1Iuzyu8H1vHvlPuV7LkXO3ZhTy3mvGT52"
shp_zip_url = "https://drive.google.com/uc?id=181SO_yvEey7d-HijGeRzDeuLuoS0jJJt"
csv_zip_path = "biological_csvs.zip"
shp_zip_path = "shape.zip"
csv_folder = "csv_data"
shp_folder = "shapefile_data"

# ---------- Download + Unzip ----------
if not os.path.exists(csv_folder):
    gdown.download(csv_zip_url, csv_zip_path, quiet=True)
    with zipfile.ZipFile(csv_zip_path, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    gdown.download(shp_zip_url, shp_zip_path, quiet=True)
    with zipfile.ZipFile(shp_zip_path, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# ---------- Load CSV Files ----------
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
    except:
        pass

if not all_data:
    st.error("❌ No valid CSV data was loaded.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)
combined_df = combined_df.dropna(subset=["ActivityStartDate", "CharacteristicName", "ResultMeasureValue", "MonitoringLocationIdentifier"])
combined_df["ResultMeasureValue"] = pd.to_numeric(combined_df["ResultMeasureValue"], errors='coerce')

# ---------- Map OrganizationIdentifier to Formal Names ----------
organization_lookup = {
    "TCEQMAIN": "Texas Commission on Environmental Quality",
    "NALMS": "North American Lake Management Society",
    "NARS_WQX": "EPA National Aquatic Resources Survey (NARS)",
    "TXSTRMTM_WQX": "Texas Stream Team",
    "11NPSWRD_WQX": "National Park Service Water Resources Division",
    "OST_SHPD": "USEPA, Office of Water, Office of Science and Technology, Standards and Health Protection Division"
}

combined_df["OrganizationFormalName"] = combined_df["OrganizationIdentifier"].map(organization_lookup).fillna("Unknown")

# ---------- Load and Prepare Shapefile ----------
shapefile_path = os.path.join(shp_folder, "filtered_11_counties.shp")
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)
if "COUNTY" not in gdf.columns:
    gdf["COUNTY"] = "Unknown"
gdf = gdf[["geometry", "COUNTY"]]

# ---------- Color by Organization ----------
orgs = combined_df["OrganizationFormalName"].dropna().unique()
color_palette = list(mcolors.TABLEAU_COLORS.values()) + list(mcolors.CSS4_COLORS.values())
org_colors = {org: color_palette[i % len(color_palette)] for i, org in enumerate(orgs)}

# ---------- Summarize by Station ----------
station_info = {}
for station_id, group in combined_df.groupby("MonitoringLocationIdentifier"):
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

    station_info[station_id] = {
        "lat": lat,
        "lon": lon,
        "organization": org_display,
        "params": param_summary,
        "color": org_color,
        "gap_total": gap_total
    }

# ---------- Build Map ----------
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron")

folium.GeoJson(
    gdf,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.4,
    },
    tooltip="COUNTY"
).add_to(m)

for station_id, info in station_info.items():
    table_html = "<table style='font-size: 12px'><tr><th>Parameter</th><th>First Date</th><th>Last Date</th><th>Gaps</th></tr>"
    for param in info["params"]:
        table_html += f"<tr><td>{param['Parameter']}</td><td>{param['FirstDate']}</td><td>{param['LastDate']}</td><td>{param['TimeGaps']}</td></tr>"
    table_html += "</table>"

    popup_html = f"""
    <div style='font-size:13px; max-height:300px; overflow:auto;'>
        <b>Station ID:</b> {station_id}<br>
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

# ---------- Click-Based Chart with Highlight ----------
clicked_id = None
clicked_lat = None
clicked_lng = None

if st_data and isinstance(st_data.get("last_object_clicked"), dict):
    clicked_point = st_data["last_object_clicked"]
    clicked_lat = clicked_point.get("lat")
    clicked_lng = clicked_point.get("lng")

    if isinstance(clicked_lat, (int, float)) and isinstance(clicked_lng, (int, float)):
        for sid, info in station_info.items():
            if abs(info["lat"] - clicked_lat) < 1e-4 and abs(info["lon"] - clicked_lng) < 1e-4:
                clicked_id = sid
                break

if clicked_id:
    df_station = combined_df[combined_df["MonitoringLocationIdentifier"] == clicked_id]
    st.subheader(f"📈 Time Series for Station `{clicked_id}`")
    selected_param = st.selectbox("Select parameter", df_station["CharacteristicName"].unique())
    chart_df = df_station[df_station["CharacteristicName"] == selected_param].sort_values("ActivityStartDate")
    st.line_chart(chart_df.set_index("ActivityStartDate")["ResultMeasureValue"])

    # Highlight on map
    folium.CircleMarker(
        location=[clicked_lat, clicked_lng],
        radius=10,
        color="red",
        fill=True,
        fill_opacity=1,
        popup=folium.Popup(f"<b>Highlighted Station:</b><br>{clicked_id}", max_width=300),
    ).add_to(m)

    # Show updated map
    st.subheader("📍 Highlighted Station")
    st_folium(m, width=1300, height=600)
