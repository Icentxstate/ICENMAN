# app.py
import os
import zipfile
import pandas as pd
import geopandas as gpd
import folium
import matplotlib.pyplot as plt
import seaborn as sns
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import streamlit as st

# 1. تنظیمات اولیه Streamlit
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Water Quality Dashboard")

# 2. مسیر فایل‌های فشرده
csv_zip = "columns_kept.zip"
shp_zip = "filtered_11_counties.zip"
csv_folder = "csv_extracted"
shp_folder = "shp_extracted"

# 3. استخراج فایل‌ها
if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# 4. بارگذاری داده‌ها
csv_dir = os.path.join(csv_folder, os.listdir(csv_folder)[0])
csv_files = [os.path.join(csv_dir, f) for f in os.listdir(csv_dir) if f.endswith(".csv")]
dfs = []
for file in csv_files:
    df = pd.read_csv(file, low_memory=False)
    df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
    df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
    dfs.append(df)
df_all = pd.concat(dfs, ignore_index=True)

# 5. ساخت خلاصه‌ای از مقادیر آخرین پارامترها
latest = df_all.sort_values("ActivityStartDate").groupby(["MonitoringLocationIdentifier", "CharacteristicName"]).last().reset_index()
pivot = latest.pivot(index="MonitoringLocationIdentifier", columns="CharacteristicName", values="ResultMeasureValue")

# مختصات هر ایستگاه
locations = df_all.groupby("MonitoringLocationIdentifier").first()[["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"]]
pivot = pivot.merge(locations, left_index=True, right_index=True)
pivot.reset_index(inplace=True)

# 6. ساخت نقشه
m = folium.Map(location=[28.5, -96.5], zoom_start=7, tiles="cartodbpositron")
marker_cluster = MarkerCluster().add_to(m)

for _, row in pivot.iterrows():
    summary = "<br>".join([f"{col}: {round(row[col], 2)}" for col in pivot.columns if col not in ["MonitoringLocationIdentifier", "ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"] and pd.notnull(row[col])])
    folium.Marker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        tooltip=row["MonitoringLocationIdentifier"],
        popup=folium.Popup(f"<b>{row['MonitoringLocationIdentifier']}</b><br>{summary}", max_width=300)
    ).add_to(marker_cluster)

# نقشه در Streamlit
st.subheader("🗺️ Monitoring Stations Map")
map_data = st_folium(m, height=500, width=1000)

# 7. انتخاب ایستگاه و پارامتر
selected_point = map_data.get("last_clicked")
if selected_point:
    lat, lon = selected_point["lat"], selected_point["lng"]
    st.success(f"✅ Selected Location: {lat:.4f}, {lon:.4f}")

    # فیلتر داده‌ها بر اساس مختصات
    selected_station = df_all[
        (df_all["ActivityLocation/LatitudeMeasure"].round(4) == round(lat, 4)) &
        (df_all["ActivityLocation/LongitudeMeasure"].round(4) == round(lon, 4))
    ]

    if not selected_station.empty:
        available_parameters = sorted(selected_station["CharacteristicName"].dropna().unique())
        selected_parameters = st.multiselect("📊 Select Parameters to Plot", available_parameters)

        # 8. رسم سری‌های زمانی
        if selected_parameters:
            st.subheader("📈 Time Series Plot")
            fig, ax = plt.subplots(figsize=(10, 5))
            for param in selected_parameters:
                series = selected_station[selected_station["CharacteristicName"] == param]
                ax.plot(series["ActivityStartDate"], series["ResultMeasureValue"], label=param)
            ax.legend()
            ax.set_xlabel("Date")
            ax.set_ylabel("Value")
            ax.set_title("Parameter Time Series")
            st.pyplot(fig)

        # 9. رسم Correlation Heatmap
        if st.button("🔍 Show Correlation Heatmap"):
            pivot_corr = selected_station.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            corr = pivot_corr[selected_parameters].corr(method="pearson")
            st.subheader("📌 Correlation Heatmap")
            fig, ax = plt.subplots()
            sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)
            st.pyplot(fig)
else:
    st.info("👆 Click on a map marker to begin analysis.")
