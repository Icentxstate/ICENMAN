import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from folium.plugins import FloatImage
from streamlit_folium import st_folium

# ---------- Paths ----------
csv_zip_path = "columns_kept.zip"
shp_zip_path = "filtered_11_counties.zip"
csv_folder = "csv_data"
shp_folder = "shapefile_data"

# ---------- Extract ZIPs ----------
if not os.path.exists(csv_folder):
    with zipfile.ZipFile(csv_zip_path, 'r') as zip_ref:
        zip_ref.extractall(csv_folder)

if not os.path.exists(shp_folder):
    with zipfile.ZipFile(shp_zip_path, 'r') as zip_ref:
        zip_ref.extractall(shp_folder)

# ---------- Load CSVs ----------
subfolders = [os.path.join(csv_folder, d) for d in os.listdir(csv_folder) if os.path.isdir(os.path.join(csv_folder, d))]
csv_files = []
for folder in subfolders:
    csv_files.extend([os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".csv")])

all_data = []
for file in csv_files:
    df = pd.read_csv(file, low_memory=False)
    if {'ActivityLocation/LatitudeMeasure', 'ActivityLocation/LongitudeMeasure', 'ActivityStartDate', 'CharacteristicName', 'ResultMeasureValue'}.issubset(df.columns):
        df = df.dropna(subset=['ActivityLocation/LatitudeMeasure', 'ActivityLocation/LongitudeMeasure'])
        df['ActivityStartDate'] = pd.to_datetime(df['ActivityStartDate'], errors='coerce')
        df['ResultMeasureValue'] = pd.to_numeric(df['ResultMeasureValue'], errors='coerce')
        df = df.dropna(subset=['ActivityStartDate', 'ResultMeasureValue'])
        df['StationKey'] = df['ActivityLocation/LatitudeMeasure'].astype(str) + "," + df['ActivityLocation/LongitudeMeasure'].astype(str)
        all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data was loaded.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# ---------- Load Shapefile ----------
shapefile_path = None
for root, dirs, files in os.walk(shp_folder):
    for file in files:
        if file.endswith('.shp'):
            shapefile_path = os.path.join(root, file)
            break
if shapefile_path is None:
    st.error("❌ No shapefile found.")
    st.stop()

gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# ---------- Sidebar Parameter Selection ----------
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Monitoring Dashboard")
selected_param = st.sidebar.selectbox("📌 Select Parameter for Map View", combined_df['CharacteristicName'].dropna().unique())

# ---------- Prepare Latest Values ----------
latest_df = combined_df[combined_df['CharacteristicName'] == selected_param].sort_values("ActivityStartDate")
latest_values = latest_df.groupby("StationKey").last().reset_index()

# ---------- Build Map ----------
st.subheader("🗺️ Interactive Monitoring Map")
center = gdf.geometry.centroid.iloc[0]
m = folium.Map(location=[center.y, center.x], zoom_start=7, tiles="CartoDB positron")

# Add shapefile
folium.GeoJson(gdf).add_to(m)

# Add station circles
for _, row in latest_values.iterrows():
    val = row['ResultMeasureValue']
    popup_text = f"Param: {selected_param}<br>Date: {row['ActivityStartDate'].date()}<br>Value: {val:.2f}"
    folium.CircleMarker(
        location=[row['ActivityLocation/LatitudeMeasure'], row['ActivityLocation/LongitudeMeasure']],
        radius=5 + min(val/10, 10),
        color="blue",
        fill=True,
        fill_opacity=0.7,
        popup=popup_text
    ).add_to(m)

st_data = st_folium(m, width=1300, height=600)

# ---------- Click + Graph Section ----------
if st_data and isinstance(st_data.get("last_object_clicked"), dict):
    clicked_lat = st_data["last_object_clicked"].get("lat")
    clicked_lon = st_data["last_object_clicked"].get("lng")
    if clicked_lat and clicked_lon:
        clicked_key = f"{clicked_lat},{clicked_lon}"
        st.markdown(f"**Selected Station:** `{clicked_key}`")
        if st.button("📈 نمایش گراف و آمار"):
            st.subheader(f"📊 Time Series for Station")
            multiselect_params = st.multiselect("Select Parameters to Compare", combined_df['CharacteristicName'].unique(), default=[selected_param])
            filtered_df = combined_df[combined_df['StationKey'] == clicked_key]
            ts_df = filtered_df[filtered_df['CharacteristicName'].isin(multiselect_params)]

            if not ts_df.empty:
                fig, ax = plt.subplots(figsize=(10, 4))
                for param in multiselect_params:
                    subset = ts_df[ts_df['CharacteristicName'] == param].sort_values("ActivityStartDate")
                    ax.plot(subset['ActivityStartDate'], subset['ResultMeasureValue'], label=param)

                ax.set_title("Time Series Plot")
                ax.set_ylabel("Value")
                ax.set_xlabel("Date")
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b-%Y'))
                plt.xticks(rotation=45)
                plt.legend()
                st.pyplot(fig)

                # 📊 Summary Table
                st.markdown("### 📈 Summary Statistics")
                stats = ts_df.groupby("CharacteristicName")["ResultMeasureValue"].describe()
                st.dataframe(stats.style.format("{:.2f}"))

                # 🔥 Correlation Heatmap
                pivot_df = ts_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
                corr = pivot_df.corr()
                fig_corr, ax_corr = plt.subplots()
                sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax_corr)
                ax_corr.set_title("Correlation Heatmap")
                st.pyplot(fig_corr)
            else:
                st.info("No data available for this station.")
