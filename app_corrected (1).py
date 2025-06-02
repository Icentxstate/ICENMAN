import streamlit as st
import pandas as pd
import geopandas as gpd
import zipfile
import os
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO

# ------------------ Paths ------------------
CSV_ZIP_PATH = "columns_kept.zip"
SHP_ZIP_PATH = "filtered_11_counties.zip"

# ------------------ Extract CSV ------------------
csv_extract_path = "columns_kept_unzipped"
os.makedirs(csv_extract_path, exist_ok=True)
with zipfile.ZipFile(CSV_ZIP_PATH, 'r') as zip_ref:
    zip_ref.extractall(csv_extract_path)

# Detect inner folder and find CSV files
inner_folders = [os.path.join(csv_extract_path, d) for d in os.listdir(csv_extract_path) if os.path.isdir(os.path.join(csv_extract_path, d))]
csv_folder = inner_folders[0] if inner_folders else csv_extract_path
csv_files = [f for f in os.listdir(csv_folder) if f.endswith(".csv")]

# ------------------ Load Data ------------------
all_data = []
for file in csv_files:
    df = pd.read_csv(os.path.join(csv_folder, file), low_memory=False)
    if {"ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "ActivityStartDate", "CharacteristicName", "ResultMeasureValue"}.issubset(df.columns):
        df = df.dropna(subset=["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure", "ActivityStartDate"])
        df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors='coerce')
        df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors='coerce')
        all_data.append(df)

if not all_data:
    st.error("❌ No valid CSV data found.")
    st.stop()

combined_df = pd.concat(all_data, ignore_index=True)

# ------------------ Extract SHP ------------------
shp_extract_path = "shapefile_extracted"
os.makedirs(shp_extract_path, exist_ok=True)
with zipfile.ZipFile(SHP_ZIP_PATH, 'r') as zip_ref:
    zip_ref.extractall(shp_extract_path)

shapefile_path = [os.path.join(shp_extract_path, f) for f in os.listdir(shp_extract_path) if f.endswith(".shp")][0]
gdf = gpd.read_file(shapefile_path).to_crs(epsg=4326)

# ------------------ Streamlit UI ------------------
st.set_page_config(layout="wide")
st.title("Texas Coastal Water Quality Dashboard")

param_main = st.selectbox("Select Parameter to Display on Map", sorted(combined_df["CharacteristicName"].dropna().unique()))

# Latest value per station and parameter
df_latest = (combined_df[combined_df["CharacteristicName"] == param_main]
             .sort_values("ActivityStartDate")
             .groupby(["ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"], as_index=False)
             .tail(1))

# ------------------ Create Map ------------------
m = folium.Map(location=[29.5, -97.5], zoom_start=7, control_scale=True)

folium.GeoJson(gdf, style_function=lambda x: {
    "fillColor": "#0b5394",
    "color": "#0b5394",
    "weight": 2,
    "fillOpacity": 0.1,
}).add_to(m)

for _, row in df_latest.iterrows():
    popup_text = f"<b>Parameter:</b> {row['CharacteristicName']}<br><b>Value:</b> {row['ResultMeasureValue']:.2f}<br><b>Date:</b> {row['ActivityStartDate'].date()}"
    folium.CircleMarker(
        location=[row["ActivityLocation/LatitudeMeasure"], row["ActivityLocation/LongitudeMeasure"]],
        radius=min(max(row["ResultMeasureValue"] / 10, 3), 15),
        color='blue',
        fill=True,
        fill_opacity=0.6,
        popup=popup_text
    ).add_to(m)

st_data = st_folium(m, width=1200, height=600)

# ------------------ Plotting Section ------------------
if st_data and st_data.get("last_object_clicked"):
    clicked = st_data["last_object_clicked"]
    lat, lon = clicked["lat"], clicked["lng"]
    st.subheader("Selected Station")
    st.write(f"Coordinates: ({lat:.4f}, {lon:.4f})")

    params_selected = st.multiselect("Add Parameters to Plot", sorted(combined_df["CharacteristicName"].dropna().unique()), default=[param_main])

    filtered_plot_df = combined_df[(combined_df["ActivityLocation/LatitudeMeasure"].round(4) == round(lat, 4)) &
                                   (combined_df["ActivityLocation/LongitudeMeasure"].round(4) == round(lon, 4)) &
                                   (combined_df["CharacteristicName"].isin(params_selected))]

    if not filtered_plot_df.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        for p in params_selected:
            df_p = filtered_plot_df[filtered_plot_df["CharacteristicName"] == p]
            ax.plot(df_p["ActivityStartDate"], df_p["ResultMeasureValue"], label=p)
        ax.set_title("Time Series of Selected Parameters")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value")
        ax.legend()
        ax.grid(True)
        fig.autofmt_xdate()
        st.pyplot(fig)

        st.markdown("### Statistical Summary")
        stats = filtered_plot_df.groupby("CharacteristicName")["ResultMeasureValue"].describe()
        st.dataframe(stats)

        st.markdown("### Correlation Heatmap")
        pivot = filtered_plot_df.pivot(index="ActivityStartDate", columns="CharacteristicName", values="ResultMeasureValue")
        corr = pivot.corr()
        fig_corr, ax_corr = plt.subplots()
        sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax_corr)
        st.pyplot(fig_corr)
    else:
        st.warning("No data available for selected point and parameters.")
