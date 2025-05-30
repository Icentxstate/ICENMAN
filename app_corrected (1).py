import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import os
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from streamlit_folium import st_folium

st.set_page_config(page_title="Texas Water Quality", layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------------------- مسیر فایل‌ها ----------------------
data_folder = "data"
shapefile_path = os.path.join(data_folder, "CZB.shp")

# ---------------------- بارگذاری فایل‌های CSV ----------------------
csv_files = [f for f in os.listdir(data_folder) if f.endswith("_biologicalresult.csv")]
all_data = []

for file in csv_files:
    df = pd.read_csv(os.path.join(data_folder, file), low_memory=False)
    df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
    df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
    all_data.append(df)

if not all_data:
    st.error("❌ No biological result files found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)
combined_df = combined_df.dropna(subset=["ActivityStartDate", "CharacteristicName", "ResultMeasureValue", "MonitoringLocationIdentifier"])
combined_df["ResultMeasureValue"] = pd.to_numeric(combined_df["ResultMeasureValue"], errors='coerce')

# ---------------------- رنگ‌دهی به سازمان‌ها ----------------------
orgs = combined_df["OrganizationFormalName"].dropna().unique()
color_palette = list(mcolors.TABLEAU_COLORS.values()) + list(mcolors.CSS4_COLORS.values())
org_colors = {org: color_palette[i % len(color_palette)] for i, org in enumerate(orgs)}

# ---------------------- خلاصه‌سازی اطلاعات ایستگاه‌ها ----------------------
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

station_info.pop("NALMS-F1384149", None)

# ---------------------- بارگذاری شیپ‌فایل ----------------------
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron", control_scale=True)

# ---------------------- لایه پلیگان + مارکرها ----------------------
folium.GeoJson(
    gdf,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.4,
    },
    popup=folium.Popup("Texas Coastal Hydrologic Monitoring Project", max_width=450)
).add_to(m)

for station_id, info in station_info.items():
    popup_html = f"""
    <div style='font-size:13px; max-height:300px; overflow:auto;'>
        <b>Station ID:</b> {station_id}<br>
        <b>Organization:</b> {info["organization"]}<br>
        <b>Total Gaps &gt;30d:</b> {info["gap_total"]}<br>
    </div>
    """
    folium.CircleMarker(
        location=[info["lat"], info["lon"]],
        radius=7,
        color=info["color"],
        weight=1,
        fill=True,
        fill_color=info["color"],
        fill_opacity=0.9,
        popup=folium.Popup(popup_html, max_width=500)
    ).add_to(m)

# ---------------------- نمایش نقشه ----------------------
st.subheader("🗺️ Interactive Map")
st.markdown("Click on a marker or select a station to view its data.")
map_data = st_folium(m, width=900, height=500)

# ---------------------- انتخاب ایستگاه و نمودار ----------------------
station_ids = sorted(station_info.keys())
selected_station = st.selectbox("📍 Select a Station ID to View Data:", station_ids)

if selected_station:
    st.write(f"**Station ID:** {selected_station}")
    station_df = combined_df[combined_df["MonitoringLocationIdentifier"] == selected_station]
    for param in station_df["CharacteristicName"].unique():
        st.subheader(f"📊 {param}")
        param_df = station_df[station_df["CharacteristicName"] == param]
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(param_df["ActivityStartDate"], param_df["ResultMeasureValue"], marker="o", linestyle="-")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value")
        ax.grid(True)
        st.pyplot(fig)
