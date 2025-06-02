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

st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# ---------- Paths ----------
csv_zip_path = "columns_kept.zip"
csv_extract_path = "columns_kept_unzipped"
shp_zip_path = "filtered_11_counties.zip"
shp_extract_path = "filtered_11_counties_unzipped"

# ---------- Extract ZIPs ----------
if not os.path.exists(csv_extract_path):
    with zipfile.ZipFile(csv_zip_path, "r") as zip_ref:
        zip_ref.extractall(csv_extract_path)

if not os.path.exists(shp_extract_path):
    with zipfile.ZipFile(shp_zip_path, "r") as zip_ref:
        zip_ref.extractall(shp_extract_path)

# ---------- Locate CSV Folder ----------
inner_csv_folder = None
for root, dirs, files in os.walk(csv_extract_path):
    if any(f.endswith(".csv") for f in files):
        inner_csv_folder = root
        break

# ---------- Load CSV Data ----------
all_data = []
if inner_csv_folder:
    for file in os.listdir(inner_csv_folder):
        if file.endswith(".csv"):
            df = pd.read_csv(os.path.join(inner_csv_folder, file), low_memory=False)
            df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
            df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
            df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')
            all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# ---------- Load Shapefile ----------
shapefile_path = None
for root, dirs, files in os.walk(shp_extract_path):
    for file in files:
        if file.endswith(".shp"):
            shapefile_path = os.path.join(root, file)
            break
if not shapefile_path:
    st.error("❌ No shapefile found.")
    st.stop()

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# ---------- Parameter Selector (Top Bar) ----------
st.sidebar.header("🧪 Select Parameter for Map")
available_params = combined_df["CharacteristicName"].dropna().unique().tolist()
selected_param = st.sidebar.selectbox("Parameter:", available_params)

# ---------- Most Recent Value Per Location ----------
latest_df = combined_df[combined_df["CharacteristicName"] == selected_param].copy()
latest_df.sort_values("ActivityStartDate", ascending=False, inplace=True)
latest_df = latest_df.drop_duplicates(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])

# ---------- Map Rendering ----------
st.subheader("📍 Monitoring Stations Map")
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron")

folium.GeoJson(gdf, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 2,
    "fillOpacity": 0.4
}).add_to(m)

for _, row in latest_df.iterrows():
    val = row["ResultMeasureValue"]
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=5 + min(val / 5, 15) if pd.notnull(val) else 5,
        color="#d62728",
        fill=True,
        fill_opacity=0.8,
        popup=f"{selected_param}: {val:.2f}"
    ).add_to(m)

# Toolbar for coordinate selection
st_data = st_folium(m, width=1300, height=600)
clicked_coords = None
if st_data and "last_object_clicked" in st_data:
    lat = st_data["last_object_clicked"].get("lat")
    lon = st_data["last_object_clicked"].get("lng")
    if lat and lon:
        clicked_coords = (lat, lon)

if clicked_coords:
    st.subheader("📊 Selected Station")
    st.write(f"**Coordinates:** {clicked_coords}")
    if st.button("Run Analysis"):
        station_df = combined_df[
            (combined_df["ActivityLocation/LatitudeMeasure"].round(4) == round(clicked_coords[0], 4)) &
            (combined_df["ActivityLocation/LongitudeMeasure"].round(4) == round(clicked_coords[1], 4))
        ]
        param_choices = station_df["CharacteristicName"].dropna().unique().tolist()
        selected_params = st.multiselect("Select parameters to plot:", param_choices, default=[selected_param])

        if selected_params:
            st.write("### 📈 Time Series Plot")
            fig, ax = plt.subplots(figsize=(10, 4))
            for param in selected_params:
                ts = station_df[station_df["CharacteristicName"] == param]
                ts = ts.sort_values("ActivityStartDate")
                ax.plot(ts["ActivityStartDate"], ts["ResultMeasureValue"], label=param)
            ax.set_xlabel("Date")
            ax.set_ylabel("Value")
            ax.legend()
            fig.autofmt_xdate()
            st.pyplot(fig)

            # ---------- Correlation Heatmap ----------
            st.write("### 🔥 Correlation Heatmap")
            pivot = station_df[station_df["CharacteristicName"].isin(selected_params)].pivot_table(
                index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue"
            )
            corr = pivot.corr()
            fig2, ax2 = plt.subplots()
            sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
            st.pyplot(fig2)

            # ---------- Summary Stats ----------
            st.write("### 📋 Statistical Summary")
            st.dataframe(pivot.describe().T)
else:
    st.info("👆 Click a point on the map to analyze its data.")
