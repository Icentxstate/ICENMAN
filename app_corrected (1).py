import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import FloatImage
from streamlit_folium import st_folium
import os
import zipfile
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(layout="wide")

# ---------------------- مسیر فایل‌ها ----------------------
csv_zip_path = "columns_kept.zip"
shapefile_zip_path = "filtered_11_counties.zip"
csv_extract_path = "csv_data"
shapefile_extract_path = "shapefile_data"

# ---------------------- استخراج فایل ZIP ----------------------
def extract_zip(zip_path, extract_to):
    if not os.path.exists(extract_to):
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)

extract_zip(csv_zip_path, csv_extract_path)
extract_zip(shapefile_zip_path, shapefile_extract_path)

# ---------------------- خواندن CSVها ----------------------
def find_csv_folder(base_folder):
    for root, _, files in os.walk(base_folder):
        if any(f.endswith(".csv") for f in files):
            return root
    return None

csv_folder = find_csv_folder(csv_extract_path)
csv_files = [f for f in os.listdir(csv_folder) if f.endswith(".csv")] if csv_folder else []

all_data = []
for file in csv_files:
    df = pd.read_csv(os.path.join(csv_folder, file), low_memory=False)
    if "ActivityLocation/LatitudeMeasure" in df.columns and "ActivityLocation/LongitudeMeasure" in df.columns:
        df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
        if "ActivityStartDate" in df.columns:
            df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors="coerce")
        if "ResultMeasureValue" in df.columns:
            df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors="coerce")
        all_data.append(df)

combined_df = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

# ---------------------- بارگذاری شیپ فایل ----------------------
shapefile_path = None
for root, _, files in os.walk(shapefile_extract_path):
    for f in files:
        if f.endswith(".shp"):
            shapefile_path = os.path.join(root, f)
            break

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326) if shapefile_path else gpd.GeoDataFrame()
gdf_clean = gdf.copy()
for col in gdf_clean.columns:
    gdf_clean[col] = gdf_clean[col].astype(str)

# ---------------------- رابط کاربری ----------------------
st.title("🗺 Texas Water Quality Explorer")

# پارامتر بالای نقشه
param_map = st.selectbox("Select Parameter for Map Display", sorted(combined_df["CharacteristicName"].dropna().unique()))

# فیلتر داده‌ها برای نقشه
map_df = combined_df[combined_df["CharacteristicName"] == param_map].dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "ResultMeasureValue"])

# ---------------------- نقشه ----------------------
m = folium.Map(location=[29.5, -97.5], zoom_start=7, control_scale=True)
folium.GeoJson(gdf_clean.__geo_interface__, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 2,
    "fillOpacity": 0.2
}).add_to(m)

for _, row in map_df.iterrows():
    val = row["ResultMeasureValue"]
    popup = f"{param_map}: {val:.2f}<br>Date: {row['ActivityStartDate'].date() if pd.notnull(row['ActivityStartDate']) else 'N/A'}"
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=min(max(val / 10, 4), 10),
        color="blue",
        fill=True,
        fill_opacity=0.7,
        popup=popup
    ).add_to(m)

st_data = st_folium(m, width=1200, height=600)

# ---------------------- انتخاب ایستگاه ----------------------
clicked_coords = None
if st_data.get("last_object_clicked"):
    clicked_coords = (
        st_data["last_object_clicked"]["lat"],
        st_data["last_object_clicked"]["lng"]
    )

if clicked_coords:
    st.markdown("### 🔍 Selected Station")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.write(f"Coordinates: {clicked_coords[0]:.5f}, {clicked_coords[1]:.5f}")
    with col2:
        run = st.button("Run", use_container_width=True)

    if run:
        selected_df = combined_df[
            (combined_df["ActivityLocation/LatitudeMeasure"].between(clicked_coords[0] - 0.0005, clicked_coords[0] + 0.0005)) &
            (combined_df["ActivityLocation/LongitudeMeasure"].between(clicked_coords[1] - 0.0005, clicked_coords[1] + 0.0005))
        ]

        # پارامترهای انتخابی برای گراف
        selected_params = st.multiselect("Select Parameters for Time Series", sorted(selected_df["CharacteristicName"].dropna().unique()), default=[param_map])

        fig, ax = plt.subplots(figsize=(10, 4))
        for p in selected_params:
            d = selected_df[selected_df["CharacteristicName"] == p]
            d = d.sort_values("ActivityStartDate")
            ax.plot(d["ActivityStartDate"], d["ResultMeasureValue"], marker='o', label=p)
        ax.set_title("Time Series")
        ax.set_ylabel("Value")
        ax.set_xlabel("Date")
        ax.legend()
        ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b-%Y'))
        plt.xticks(rotation=45)
        st.pyplot(fig)

        # جدول آماری
        st.markdown("### 📊 Statistical Summary")
        stat_df = selected_df[selected_df["CharacteristicName"].isin(selected_params)]
        stat_summary = stat_df.groupby("CharacteristicName")["ResultMeasureValue"].describe()
        st.dataframe(stat_summary)

        # همبستگی
        pivot = stat_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
        corr = pivot.corr()
        fig2, ax2 = plt.subplots(figsize=(6, 5))
        sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
        ax2.set_title("Correlation Heatmap")
        st.pyplot(fig2)
