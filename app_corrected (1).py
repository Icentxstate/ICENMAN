import streamlit as st
import pandas as pd
import geopandas as gpd
import requests
from io import BytesIO
import zipfile
import os
import matplotlib.pyplot as plt
import seaborn as sns
import folium
from streamlit_folium import folium_static

# تنظیمات اولیه
st.set_page_config(layout="wide")
st.title("📍 اپلیکیشن تحلیلی مکانی و زمانی")

# آدرس مخزن گیت‌هاب
REPO_URL = "https://github.com/Icentxstate/ICENMAN/raw/main"

# تابع بارگذاری فایل زیپ از گیت‌هاب
def load_zip_from_github(zip_filename, extract_to="data"):
    url = f"{REPO_URL}/{zip_filename}"
    response = requests.get(url)
    with zipfile.ZipFile(BytesIO(response.content)) as z:
        z.extractall(extract_to)
    return extract_to

# بارگذاری داده‌ها
with st.spinner("در حال بارگذاری داده‌ها..."):
    csv_dir = load_zip_from_github("columns_kept.zip", "csv_data")
    shp_dir = load_zip_from_github("filtered_11_counties.zip", "shp_data")

    # بارگذاری CSVها
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    df_list = [pd.read_csv(os.path.join(csv_dir, f)) for f in csv_files]
    df = pd.concat(df_list, ignore_index=True)

    # بارگذاری shapefile
    shp_files = [f for f in os.listdir(shp_dir) if f.endswith(".shp")]
    gdf = gpd.read_file(os.path.join(shp_dir, shp_files[0]))

# نمایش نقشه
st.subheader("🗺️ نقشه نقاط")
m = folium.Map(location=[gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()], zoom_start=8)
for _, row in gdf.iterrows():
    folium.Marker(
        location=[row.geometry.centroid.y, row.geometry.centroid.x],
        popup="کلیک برای مشاهده پارامترها",
        tooltip="نقطه",
    ).add_to(m)
folium_static(m)

# انتخاب پارامتر و رسم گراف
st.subheader("📊 انتخاب پارامترها برای رسم گراف")
params = [col for col in df.columns if col not in ['timestamp', 'lat', 'lon']]
selected_params = st.multiselect("پارامترها:", params)

if selected_params:
    st.line_chart(df[selected_params])

# هیت‌مپ همبستگی
if st.button("📈 نمایش هیت‌مپ همبستگی"):
    st.subheader("🔍 همبستگی بین پارامترها")
    corr = df[selected_params].corr()
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)
    st.pyplot(fig)
