
import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import zipfile
import os
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# -------------------- Config --------------------
st.set_page_config(layout="wide")
st.title("🌊 Texas Coastal Water Quality Monitoring Dashboard")

# -------------------- Extract Files --------------------
csv_zip_path = "columns_kept.zip"
shp_zip_path = "filtered_11_counties.zip"
csv_extracted_path = "csv_extracted"
shp_extracted_path = "shp_extracted"

for path, zip_path in zip([csv_extracted_path, shp_extracted_path], [csv_zip_path, shp_zip_path]):
    if not os.path.exists(path):
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(path)

# -------------------- Load CSV Files --------------------
csv_root = next(os.walk(csv_extracted_path))[1][0]
csv_files = [os.path.join(csv_extracted_path, csv_root, f) for f in os.listdir(os.path.join(csv_extracted_path, csv_root)) if f.endswith(".csv")]

dataframes = []
for file in csv_files:
    df = pd.read_csv(file, low_memory=False)
    if "ActivityStartDate" in df.columns:
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors="coerce")
    dataframes.append(df)
df_all = pd.concat(dataframes, ignore_index=True)

# Filter for necessary columns
required_cols = ["ActivityStartDate", "CharacteristicName", "ResultMeasureValue", "ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"]
df_all = df_all[[col for col in required_cols if col in df_all.columns]].dropna()

# -------------------- Load Shapefile --------------------
shp_files = [f for f in os.listdir(shp_extracted_path) if f.endswith(".shp")]
shapefile_path = os.path.join(shp_extracted_path, shp_files[0])
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# -------------------- Sidebar Selection --------------------
param_choices = sorted(df_all["CharacteristicName"].unique())
main_param = st.sidebar.selectbox("🧪 Select Main Parameter (Map Display)", param_choices)

# Latest value per location for selected param
latest_df = df_all[df_all["CharacteristicName"] == main_param].sort_values("ActivityStartDate")
latest_df = latest_df.groupby(["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"]).last().reset_index()

# -------------------- Create Folium Map --------------------
m = folium.Map(location=[28.5, -96], zoom_start=7, tiles="cartodbpositron")

# Add shapefile layer
folium.GeoJson(gdf, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 2,
    "fillOpacity": 0.1,
}).add_to(m)

# Add station markers
mc = MarkerCluster().add_to(m)
for _, row in latest_df.iterrows():
    summary = f"{main_param}: {round(row['ResultMeasureValue'], 2)}"
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=5 + min(20, max(0, row["ResultMeasureValue"] / 5)),
        color="blue",
        fill=True,
        fill_opacity=0.6,
        popup=summary,
    ).add_to(mc)

# Display map
st_data = st_folium(m, width=1200, height=600)

# -------------------- Coordinate selection --------------------
if st_data and st_data.get("last_clicked"):
    lat = round(st_data["last_clicked"]["lat"], 5)
    lon = round(st_data["last_clicked"]["lng"], 5)
    st.markdown(f"### 📍 Selected Station Coordinates: ({lat}, {lon})")
    run = st.button("Run Analysis")

    if run:
        st.subheader("📈 Time Series & Correlation Analysis")

        selected_df = df_all[(df_all["ActivityLocation/LatitudeMeasure"].round(5) == lat) & 
                             (df_all["ActivityLocation/LongitudeMeasure"].round(5) == lon)]

        multiselect_params = st.multiselect("📌 Select Parameters to Plot", sorted(selected_df["CharacteristicName"].unique()), default=[main_param])
        selected_df = selected_df[selected_df["CharacteristicName"].isin(multiselect_params)]

        if not selected_df.empty:
            pivot_df = selected_df.pivot_table(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
            st.line_chart(pivot_df)

            st.markdown("#### 📊 Summary Statistics")
            st.dataframe(pivot_df.describe())

            st.markdown("#### 🔥 Correlation Heatmap")
            fig, ax = plt.subplots(figsize=(10, 5))
            sns.heatmap(pivot_df.corr(), annot=True, cmap="coolwarm", ax=ax)
            st.pyplot(fig)
        else:
            st.warning("No data available for selected station and parameters.")
