import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import io

st.set_page_config(page_title="Tractor Traffic Heatmap", layout="wide")
st.title("Tractor Movement Heatmap (April 2025)")
st.write(
    "3D grid heatmap. Adjust cell size, color scaling, and bar height. "
    "Green=lowest activity, Red=highest. Hover for density. "
)

# === Load Data ===
@st.cache_data
def load_data():
    df = pd.read_csv("gps_data_april2025.csv")
    df = df[df["Lat"].notnull() & df["Lon"].notnull()]
    return df

df = load_data()

# --- Sliders with your requested settings ---
grid_size = st.slider(
    "Grid cell size (meters)",
    min_value=0.5, max_value=10.0, value=2.0, step=0.1,
    help="Area each cell represents. Smaller = more detail, slower."
)
max_height = st.slider(
    "Max bar height (meters)",
    min_value=0.2, max_value=20.0, value=10.0, step=0.1,
    help="Maximum column height (visual scale, doesn't affect color)."
)
color_power = st.slider(
    "Color sharpness / density boost",
    min_value=0.05, max_value=1.00, value=0.20, step=0.01,
    help="Boosts contrast. >1 exaggerates high densities, <1 smooths colors."
)

# --- Green-Yellow-Red colormap
from matplotlib.colors import LinearSegmentedColormap
gyred = LinearSegmentedColormap.from_list("gyred", ["#00FF00", "#FFFF00", "#FF0000"])
n_colors = 12
color_range = [
    [int(255*r), int(255*g), int(255*b), 220]
    for (r, g, b, a) in [gyred(i / (n_colors-1)) for i in range(n_colors)]
]

# --- Bin GPS points ---
deg_per_meter = 1 / 111_000
lat_bin_width = grid_size * deg_per_meter
lon_bin_width = grid_size * deg_per_meter / np.cos(np.deg2rad(df["Lat"].mean()))

lat_bins = np.arange(df["Lat"].min(), df["Lat"].max() + lat_bin_width, lat_bin_width)
lon_bins = np.arange(df["Lon"].min(), df["Lon"].max() + lon_bin_width, lon_bin_width)

df['lat_bin'] = pd.cut(df['Lat'], bins=lat_bins, labels=False, include_lowest=True)
df['lon_bin'] = pd.cut(df['Lon'], bins=lon_bins, labels=False, include_lowest=True)
binned = df.groupby(['lat_bin', 'lon_bin']).size().reset_index(name='count')
binned = binned.dropna()

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
    min_density = int(heatmap_df["count"].min())
    max_density = int(heatmap_df["count"].max())
    spread = max(max_density - min_density, 1)
    def norm_boosted(count):
        n = (count - min_density) / spread
        return np.clip(n ** color_power, 0, 1)
    heatmap_df["norm_count"] = heatmap_df["count"].apply(norm_boosted)
    def color_from_norm(norm):
        r, g, b, a = gyred(norm)
        return [int(255*r), int(255*g), int(255*b), 220]
    heatmap_df["color"] = heatmap_df["norm_count"].apply(color_from_norm)
    # Height scaling
    height_scale = max_height / max_density if max_density > 0 else 1.0
    heatmap_df["height"] = heatmap_df["count"] * height_scale
else:
    min_density = 0
    max_density = 1
    heatmap_df["color"] = [gyred(0)]
    heatmap_df["height"] = 1

# --- Pydeck 3D ColumnLayer ---
layer = pdk.Layer(
    "ColumnLayer",
    data=heatmap_df,
    get_position='[lon, lat]',
    pickable=True,
    get_elevation="height",
    elevation_scale=1.0,
    radius=grid_size / 2,
    get_fill_color="color",
    auto_highlight=True,
    extruded=True,
    elevation_range=[0, max_height],
)

view_state = pdk.ViewState(
    latitude=df["Lat"].mean(),
    longitude=df["Lon"].mean(),
    zoom=17,
    bearing=0,
    pitch=45,
)

tooltip = {
    "html": f"Density (points in {grid_size:.2f}×{grid_size:.2f}m): <b>{{count}}</b>",
    "style": {"backgroundColor": "black", "color": "white"}
}

r = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    map_style="mapbox://styles/mapbox/satellite-v9",
    tooltip=tooltip,
)

st.pydeck_chart(r, use_container_width=True)

# --- Colorbar Legend (tight layout minimized, warning is safe to ignore) ---
fig, ax = plt.subplots(figsize=(4.8, 0.45), tight_layout=True)
norm = matplotlib.colors.Normalize(vmin=0, vmax=1)
cb = matplotlib.colorbar.ColorbarBase(
    ax, cmap=gyred, orientation='horizontal', norm=norm
)
cb.set_label(f"Relative Density (Green: {min_density} points, Red: {max_density} points)", fontsize=9)
cb.ax.tick_params(labelsize=8)
buf = io.BytesIO()
plt.savefig(buf, format="png", bbox_inches='tight', dpi=100)
st.image(buf, caption="Green-Yellow-Red Density Scale (see numbers above!)", use_container_width=True)

st.caption(
    f"Min/Max: Green cell = {min_density} points, Red = {max_density} points. "
    f"Use sliders to tune detail, color boost, and bar height. Hover bars for counts.<br>"
    "<small>Ignore 'tight layout' warnings—legend is accurate.</small>", unsafe_allow_html=True
)
