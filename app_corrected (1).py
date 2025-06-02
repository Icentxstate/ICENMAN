import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import FloatImage
from streamlit_folium import st_folium
import zipfile
import os
import matplotlib.pyplot as plt
import seaborn as sns

# ------------------- داده‌ها -------------------
@st.cache_data
def load_csv_from_nested_zip(zip_path):
    extract_dir = "/tmp/columns_kept"
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    # پیدا کردن پوشه حاوی CSVها
    all_csvs = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.endswith(".csv"):
                path = os.path.join(root, f)
                df = pd.read_csv(path, low_memory=False)
                if "ActivityStartDate" in df.columns and "CharacteristicName" in df.columns:
                    df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors="coerce")
                    df = df.dropna(subset=["ActivityStartDate", "CharacteristicName", "ResultMeasureValue", "ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
                    df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors="coerce")
                    all_csvs.append(df)

    if not all_csvs:
        st.error("❌ No valid CSV data found.")
        return pd.DataFrame()

    combined_df = pd.concat(all_csvs, ignore_index=True)
    return combined_df

@st.cache_data
def load_shapefile_from_zip(zip_path):
    extract_dir = "/tmp/shapefile"
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    shp_file = None
    for root, _, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".shp"):
                shp_file = os.path.join(root, file)
                break
    if not shp_file:
        return None

    gdf = gpd.read_file(shp_file)
    return gdf[gdf.geometry.notnull()]

# ------------------- UI بالا -------------------
st.set_page_config(layout="wide", page_title="Water Quality Map")
st.title("🌊 Texas Coastal Water Quality Monitoring")
st.markdown("---")

df = load_csv_from_nested_zip("columns_kept.zip")
gdf = load_shapefile_from_zip("filtered_11_counties.zip")

if df.empty or gdf is None:
    st.stop()

# ------------------- انتخاب پارامتر -------------------
parameter = st.selectbox("Select Parameter for Map Circle Sizing:", sorted(df["CharacteristicName"].unique()))
latest_df = df.sort_values("ActivityStartDate").drop_duplicates(
    subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "CharacteristicName"],
    keep="last"
)
latest_df = latest_df[latest_df["CharacteristicName"] == parameter]

# ------------------- نقشه -------------------
m = folium.Map(location=[28.5, -96.5], zoom_start=7)

# counties layer
folium.GeoJson(
    data=gdf.__geo_interface__,
    style_function=lambda x: {
        "fillColor": "#0b5394",
        "color": "#0b5394",
        "weight": 2,
        "fillOpacity": 0.1,
    }
).add_to(m)

# stations layer
for _, row in latest_df.iterrows():
    value = row["ResultMeasureValue"]
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=3 + min(value, 10),
        popup=f"{parameter}: {value:.2f}",
        fill=True,
        color="blue",
        fill_opacity=0.6,
    ).add_to(m)

# ------------------- انتخاب ایستگاه -------------------
st.markdown("## 🗺️ Select Station")
st_data = st_folium(m, height=600, width=1200)

if st_data["last_object_clicked"]:
    lat = round(st_data["last_object_clicked"]["lat"], 5)
    lon = round(st_data["last_object_clicked"]["lng"], 5)
    st.markdown(f"📍 Selected Coordinates: **{lat}, {lon}**")
    if st.button("Run Analysis"):

        station_df = df[(df["ActivityLocation/LatitudeMeasure"].round(5) == lat) &
                        (df["ActivityLocation/LongitudeMeasure"].round(5) == lon)]

        selected_params = st.multiselect("Select Parameters to Plot:", sorted(station_df["CharacteristicName"].unique()), default=[parameter])

        plot_df = station_df[station_df["CharacteristicName"].isin(selected_params)]

        if plot_df.empty:
            st.warning("No data for selected parameters at this station.")
        else:
            # ------------------- سری زمانی -------------------
            fig, ax = plt.subplots(figsize=(12, 5))
            for param in selected_params:
                sub = plot_df[plot_df["CharacteristicName"] == param]
                ax.plot(sub["ActivityStartDate"], sub["ResultMeasureValue"], label=param)
            ax.set_xlabel("Date")
            ax.set_ylabel("Result Measure")
            ax.set_title("Time Series of Selected Parameters")
            ax.legend()
            ax.grid(True)
            ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b %Y'))
            plt.xticks(rotation=45)
            st.pyplot(fig)

            # ------------------- جدول آماری -------------------
            stats_table = plot_df.groupby("CharacteristicName")["ResultMeasureValue"].describe().round(2)
            st.markdown("### 📊 Summary Statistics")
            st.dataframe(stats_table)

            # ------------------- Heatmap -------------------
            pivot_df = plot_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            corr = pivot_df.corr()
            st.markdown("### 🔥 Correlation Heatmap")
            fig2, ax2 = plt.subplots(figsize=(8, 6))
            sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax2)
            st.pyplot(fig2)
