import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import matplotlib
import matplotlib.pyplot as plt

st.set_page_config(page_title="Tractor Traffic Heatmap", layout="wide")
st.title("Tractor Movement Heatmap (April 2025)")
st.write(
    "Fine-grained heatmap (0.5m–10m). Colors show density: Green (low) → Yellow → Red (high). "
    "Color scaling adapts to data for strong visible contrast. "
    "Adjust all sliders for detail, bar height, and color mapping."
)

# === Load Data ===
@st.cache_data
def load_data():
    df = pd.read_csv("gps_data_april2025.csv")
    df = df[df["Lat"].notnull() & df["Lon"].notnull()]
    return df

df = load_data()

# --- Sliders
grid_size = st.slider(
    "Grid cell size (meters)", min_value=0.50, max_value=10.00, value=2.00, step=0.10
)
max_bar_height = st.slider(
    "Max bar height (meters)", min_value=0.20, max_value=20.00, value=10.00, step=0.10
)
color_sharpness = st.slider(
    "Color sharpness / density boost",
    min_value=0.05,
    max_value=2.00,
    value=0.20,
    step=0.01,
)

# --- Binning into grid
deg_per_meter = 1 / 111_000
lat_bin_width = grid_size * deg_per_meter
lon_bin_width = grid_size * deg_per_meter / np.cos(np.deg2rad(df["Lat"].mean()))
lat_bins = np.arange(df["Lat"].min(), df["Lat"].max() + lat_bin_width, lat_bin_width)
lon_bins = np.arange(df["Lon"].min(), df["Lon"].max() + lon_bin_width, lon_bin_width)
df['lat_bin'] = pd.cut(df['Lat'], bins=lat_bins, labels=False, include_lowest=True)
df['lon_bin'] = pd.cut(df['Lon'], bins=lon_bins, labels=False, include_lowest=True)
binned = df.groupby(['lat_bin', 'lon_bin']).size().reset_index(name='count')
binned = binned.dropna()

# --- Build grid DataFrame for pydeck
heatmap_data = []
for _, row in binned.iterrows():
    i, j, count = int(row['lat_bin']), int(row['lon_bin']), int(row['count'])
    lat_c = (lat_bins[i] + lat_bins[i+1]) / 2
    lon_c = (lon_bins[j] + lon_bins[j+1]) / 2
    heatmap_data.append({
        "lat": lat_c,
        "lon": lon_c,
        "count": count
    })
heatmap_df = pd.DataFrame(heatmap_data)

if not heatmap_df.empty:
    min_density = int(heatmap_df['count'].min())
    max_density = int(heatmap_df['count'].max())
else:
    min_density = 1
    max_density = 1

# --- Color normalization for green→yellow→red
from matplotlib.colors import LinearSegmentedColormap
gyred = LinearSegmentedColormap.from_list("gyred", [
    (0.00, "#00FF00"),  # Green
    (0.50, "#FFFF00"),  # Yellow
    (1.00, "#FF0000"),  # Red
])

# Apply color sharpness: density normalization/exponentiation
if not heatmap_df.empty and max_density > 0:
    heatmap_df['rel_density'] = (
        (heatmap_df['count'] - min_density) / (max_density - min_density + 1e-8)
    ) ** color_sharpness
    heatmap_df['rel_density'] = heatmap_df['rel_density'].clip(0, 1)
    # Map normalized to rgba (0..255, alpha 180)
    heatmap_df['color'] = heatmap_df['rel_density'].apply(
        lambda x: [int(255*y) for y in gyred(x)[:3]] + [180]
    )
else:
    heatmap_df['rel_density'] = 0
    heatmap_df['color'] = [[0, 255, 0, 180]]

# --- Pydeck Layer
layer = pdk.Layer(
    "ColumnLayer",
    data=heatmap_df,
    get_position='[lon, lat]',
    get_elevation="count",
    elevation_scale=max_bar_height / (max_density if max_density > 0 else 1),
    elevation_range=[0, max_bar_height],
    radius=grid_size / 2,  # "radius" is half the grid cell, so bars don't overlap
    get_fill_color="color",
    pickable=True,
    auto_highlight=True,
    extruded=True,
)

view_state = pdk.ViewState(
    latitude=df["Lat"].mean(),
    longitude=df["Lon"].mean(),
    zoom=17,
    bearing=0,
    pitch=45,
)

tooltip = {
    "html": (
        "Lat/Lon: [{lat:.5f}, {lon:.5f}]<br>"
        "Points: <b>{count}</b>"
    ),
    "style": {"backgroundColor": "black", "color": "white"},
}

r = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    map_style="mapbox://styles/mapbox/satellite-v9",
    tooltip=tooltip,
)

st.pydeck_chart(r, use_container_width=True)

# --- Colorbar legend using st.pyplot
fig, ax = plt.subplots(figsize=(5, 0.7))
norm = matplotlib.colors.Normalize(vmin=min_density, vmax=max_density)
cb = matplotlib.colorbar.ColorbarBase(
    ax, cmap=gyred, orientation='horizontal', norm=norm
)
cb.set_label(f"Min/Max: Green cell = {min_density} points, Red = {max_density} points.")
plt.tight_layout()
st.pyplot(fig)

st.caption(
    "Use sliders to tune detail, color boost, and bar height. "
    "Green = lowest density, red = highest. Hover for counts. "
    "Ignore 'tight layout' warnings—legend is accurate."
)
