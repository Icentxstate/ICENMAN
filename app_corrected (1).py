import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import os
import zipfile
from folium.plugins import FloatImage
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import seaborn as sns

# --- تنظیمات صفحه ---
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Hydrologic Monitoring Dashboard")

# --- مسیر فایل‌ها ---
csv_zip = "columns_kept.zip"
shp_zip = "filtered_11_counties.zip"
csv_folder = "extracted_csvs"
shp_folder = "shapefile"

# --- استخراج فایل‌های ZIP ---
def extract_nested_csvs(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    for root, dirs, files in os.walk(extract_to):
        for dir in dirs:
            sub_path = os.path.join(root, dir)
            csvs = [f for f in os.listdir(sub_path) if f.endswith(".csv")]
            if csvs:
                return sub_path
    return extract_to

def extract_shapefile(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

csv_path = extract_nested_csvs(csv_zip, csv_folder)
extract_shapefile(shp_zip, shp_folder)

# --- بارگذاری داده‌ها ---
csv_files = [f for f in os.listdir(csv_path) if f.endswith(".csv")]
all_data = []
for file in csv_files:
    df = pd.read_csv(os.path.join(csv_path, file), low_memory=False)
    if {"ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "ActivityStartDate", "CharacteristicName", "ResultMeasureValue"}.issubset(df.columns):
        df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "ActivityStartDate", "CharacteristicName", "ResultMeasureValue"])
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors="coerce")
        df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors="coerce")
        all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# --- بارگذاری shapefile ---
shapefile_path = None
for file in os.listdir(shp_folder):
    if file.endswith(".shp"):
        shapefile_path = os.path.join(shp_folder, file)
        break
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# --- انتخاب پارامتر نقشه ---
param_map = st.selectbox("🧪 Select Parameter for Map Display", combined_df["CharacteristicName"].unique())

# --- خلاصه آخرین مقادیر ایستگاه ---
latest_data = combined_df.sort_values("ActivityStartDate").dropna()
latest_by_station = latest_data.groupby(["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "CharacteristicName"]).tail(1)
map_df = latest_by_station[latest_by_station["CharacteristicName"] == param_map]

# --- نقشه ---
st.subheader("🗺️ Interactive Map")
m = folium.Map(location=[map_df["ActivityLocation/LatitudeMeasure"].mean(), map_df["ActivityLocation/LongitudeMeasure"].mean()], zoom_start=7)

# نقشه کانتی‌ها
folium.GeoJson(
    gdf.__geo_interface__,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.2,
    }
).add_to(m)

# نقاط ایستگاه‌ها
for _, row in map_df.iterrows():
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=min(max(row["ResultMeasureValue"] / 10, 3), 12),
        color="blue",
        fill=True,
        fill_opacity=0.8,
        popup=f"{param_map}: {row['ResultMeasureValue']:.2f}<br>Date: {row['ActivityStartDate'].date()}"
    ).add_to(m)

st_data = st_folium(m, width=1200, height=600)

# --- انتخاب نقطه ---
clicked_coords = st_data.get("last_object_clicked", None)
if clicked_coords:
    lat, lon = round(clicked_coords["lat"], 6), round(clicked_coords["lng"], 6)
    st.markdown(f"📍 Selected Station: `{lat}, {lon}`")
    if st.button("Run Analysis"):
        station_df = combined_df[
            (combined_df["ActivityLocation/LatitudeMeasure"].round(6) == lat) &
            (combined_df["ActivityLocation/LongitudeMeasure"].round(6) == lon)
        ]
        if station_df.empty:
            st.warning("No data found for this location.")
        else:
            multi_params = st.multiselect("➕ Add Parameters to Plot", station_df["CharacteristicName"].unique())
            if multi_params:
                fig, ax = plt.subplots(figsize=(10, 4))
                for param in multi_params:
                    subset = station_df[station_df["CharacteristicName"] == param]
                    ax.plot(subset["ActivityStartDate"], subset["ResultMeasureValue"], label=param)
                ax.legend()
                ax.set_xlabel("Date")
                ax.set_ylabel("Value")
                ax.set_title("Time Series")
                ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b-%Y'))
                fig.autofmt_xdate()
                st.pyplot(fig)

                # Correlation heatmap
                pivot_df = station_df[station_df["CharacteristicName"].isin(multi_params)]
                pivot_wide = pivot_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
                corr = pivot_wide.corr()
                st.subheader("🔗 Parameter Correlation Heatmap")
                fig2, ax2 = plt.subplots()
                sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
                st.pyplot(fig2)
