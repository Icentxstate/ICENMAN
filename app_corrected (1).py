import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import zipfile
import os
import matplotlib.pyplot as plt
import seaborn as sns
from folium.plugins import MarkerCluster

# ---------------------- تنظیمات صفحه ----------------------
st.set_page_config(layout="wide")
st.title("Texas Coastal Hydrologic Monitoring Project")

# ---------------------- مسیرها ----------------------
data_zip_path = "columns_kept.zip"
shape_zip_path = "filtered_11_counties.zip"
data_extract_path = "columns_kept"
shape_extract_path = "filtered_11_counties"

# ---------------------- استخراج داده‌ها ----------------------
if not os.path.exists(data_extract_path):
    with zipfile.ZipFile(data_zip_path, 'r') as zip_ref:
        zip_ref.extractall(data_extract_path)

if not os.path.exists(shape_extract_path):
    with zipfile.ZipFile(shape_zip_path, 'r') as zip_ref:
        zip_ref.extractall(shape_extract_path)

# ---------------------- بارگذاری داده‌ها ----------------------
csv_folder = os.path.join(data_extract_path, os.listdir(data_extract_path)[0])
csv_files = [f for f in os.listdir(csv_folder) if f.endswith(".csv")]
all_data = []
for file in csv_files:
    df = pd.read_csv(os.path.join(csv_folder, file), low_memory=False)
    if "ActivityLocation/LatitudeMeasure" in df.columns and "ActivityLocation/LongitudeMeasure" in df.columns:
        df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
        df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')
        all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# ---------------------- آماده‌سازی داده مکانی ----------------------
gdf = gpd.read_file(os.path.join(shape_extract_path, "filtered_11_counties.shp"))
gdf = gdf.to_crs(epsg=4326)

# ---------------------- نقشه ----------------------
st.subheader("Monitoring Map")
parameter_for_map = st.selectbox("Select parameter to map by size:", combined_df["CharacteristicName"].dropna().unique())
latest_values = (
    combined_df[combined_df["CharacteristicName"] == parameter_for_map]
    .sort_values("ActivityStartDate")
    .groupby(["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
    .tail(1)
)

m = folium.Map(location=[28.9, -96.8], zoom_start=7)
folium.GeoJson(gdf, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 2,
    "fillOpacity": 0.1,
}).add_to(m)

marker_cluster = MarkerCluster().add_to(m)
for _, row in latest_values.iterrows():
    value = row["ResultMeasureValue"]
    lat, lon = row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]
    folium.CircleMarker(
        location=[lat, lon],
        radius=5 + min(value, 20)/4,
        popup=f"{parameter_for_map}: {value:.2f}",
        color="blue",
        fill=True,
        fill_opacity=0.6,
    ).add_to(marker_cluster)

st_data = st_folium(m, width=1200, height=600)

# ---------------------- انتخاب ایستگاه ----------------------
if st_data and st_data.get("last_object_clicked"):
    clicked = st_data["last_object_clicked"]
    st.write(f"**Selected Station Coordinates:** {clicked['lat']:.4f}, {clicked['lng']:.4f}")

    selected_df = combined_df[
        (combined_df["ActivityLocation/LatitudeMeasure"].round(4) == round(clicked['lat'], 4)) &
        (combined_df["ActivityLocation/LongitudeMeasure"].round(4) == round(clicked['lng'], 4))
    ]

    selected_params = st.multiselect("Add parameters to time series plot:", selected_df["CharacteristicName"].dropna().unique())
    run_plot = st.button("Run Analysis")

    if run_plot and selected_params:
        fig, ax = plt.subplots(figsize=(10, 5))
        for param in selected_params:
            temp = selected_df[selected_df["CharacteristicName"] == param]
            temp = temp.sort_values("ActivityStartDate")
            ax.plot(temp["ActivityStartDate"], temp["ResultMeasureValue"], label=param)

        ax.set_title("Time Series of Selected Parameters")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value")
        ax.legend()
        ax.grid(True)
        ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b-%Y'))
        st.pyplot(fig)

        # جدول تحلیل آماری
        stats_df = (
            selected_df[selected_df["CharacteristicName"].isin(selected_params)]
            .groupby("CharacteristicName")["ResultMeasureValue"]
            .agg(["count", "mean", "std", "min", "max"])
        )
        st.subheader("Statistical Summary")
        st.dataframe(stats_df)

        # همبستگی پارامترها
        pivot_df = (
            selected_df[selected_df["CharacteristicName"].isin(selected_params)]
            .pivot_table(values="ResultMeasureValue", index="ActivityStartDate", columns="CharacteristicName")
        )
        corr = pivot_df.corr()
        fig2, ax2 = plt.subplots()
        sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
        st.subheader("Correlation Heatmap")
        st.pyplot(fig2)
