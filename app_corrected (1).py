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

# 1. تنظیمات اولیه
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Water Quality Dashboard")

# 2. مسیر فایل‌ها
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
    df["StationID"] = df["ActivityLocation/LatitudeMeasure"].round(5).astype(str) + "_" + df["ActivityLocation/LongitudeMeasure"].round(5).astype(str)
    dfs.append(df)
df_all = pd.concat(dfs, ignore_index=True)

# 5. ساخت خلاصه از داده‌ها
latest = df_all.sort_values("ActivityStartDate").groupby(["StationID", "CharacteristicName"]).last().reset_index()
pivot = latest.pivot(index="StationID", columns="CharacteristicName", values="ResultMeasureValue")
locations = df_all.groupby("StationID").first()[["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"]]
pivot = pivot.merge(locations, left_index=True, right_index=True)
pivot.reset_index(inplace=True)

# 6. نقشه
m = folium.Map(location=[28.5, -96.5], zoom_start=7, tiles="cartodbpositron")
marker_cluster = MarkerCluster().add_to(m)

for _, row in pivot.iterrows():
    summary = "<br>".join([f"{col}: {round(row[col], 2)}" for col in pivot.columns if col not in ["StationID", "ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"] and pd.notnull(row[col])])
    folium.Marker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        tooltip=row["StationID"],
        popup=folium.Popup(f"<b>{row['StationID']}</b><br>{summary}", max_width=300)
    ).add_to(marker_cluster)

st.subheader("🗺️ Monitoring Stations Map")
map_data = st_folium(m, height=500, width=1000)

# 7. انتخاب نقطه
selected_point = map_data.get("last_clicked")
if selected_point:
    lat, lon = selected_point["lat"], selected_point["lng"]
    st.success(f"✅ Selected Location: {lat:.4f}, {lon:.4f}")

    # ساخت StationID
    selected_station_id = f"{round(lat, 5)}_{round(lon, 5)}"
    selected_df = df_all[df_all["StationID"] == selected_station_id]

    if not selected_df.empty:
        available_parameters = sorted(selected_df["CharacteristicName"].dropna().unique())
        selected_parameters = st.multiselect("📊 Select Parameters to Plot", available_parameters)

        # 8. سری زمانی
        if selected_parameters:
            st.subheader("📈 Time Series Plot")
            fig, ax = plt.subplots(figsize=(10, 5))
            for param in selected_parameters:
                series = selected_df[selected_df["CharacteristicName"] == param]
                ax.plot(series["ActivityStartDate"], series["ResultMeasureValue"], label=param)
            ax.legend()
            ax.set_xlabel("Date")
            ax.set_ylabel("Value")
            ax.set_title("Parameter Time Series")
            st.pyplot(fig)

        # 9. همبستگی
        if st.button("🔍 Show Correlation Heatmap"):
            pivot_corr = selected_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            corr = pivot_corr[selected_parameters].corr(method="pearson")
            st.subheader("📌 Correlation Heatmap")
            fig, ax = plt.subplots()
            sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)
            st.pyplot(fig)
else:
    st.info("👆 Click on a map marker to begin analysis.")
