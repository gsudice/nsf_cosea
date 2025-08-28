# import libraries
import psycopg2
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from shapely.geometry import Point
import osmnx as ox
import urllib.request
import tempfile

# connect to database
conn = psycopg2.connect(
    dbname="cosea_db",
    user="cosea_user",
    password="CoSeaIndex",
    host="pgsql.dataconn.net",
    port="5432"
)

# load school data and logic classifications
school_query = """SELECT "UNIQUESCHOOLID", lat, lon FROM "2024"."tbl_approvedschools" """
school_df = pd.read_sql(school_query, conn)
logic_query = """SELECT "UNIQUESCHOOLID", "LOGIC_CLASS" FROM census.gadoe2024"""
logic_df = pd.read_sql(logic_query, conn)
conn.close()

# merge and classify
merged = school_df.merge(logic_df, on="UNIQUESCHOOLID", how="inner").dropna(subset=["lat", "lon", "LOGIC_CLASS"])

def combined_category(logic_class):
    prefix = logic_class[:2]
    suffix = logic_class[-1]
    if prefix == "11" and suffix == "1": return 'Purple Triangle'
    elif prefix == "11" and suffix == "0": return 'Purple Circle'
    elif prefix == "10" and suffix == "1": return 'Pink Triangle'
    elif prefix == "10" and suffix == "0": return 'Pink Circle'
    elif prefix == "01" and suffix == "1": return 'Yellow Triangle'
    elif prefix == "01" and suffix == "0": return 'Yellow Circle'
    elif prefix == "00" and suffix == "1": return 'Gray Triangle'
    elif prefix == "00" and suffix == "0": return 'Gray Circle'
    else: return 'Other'

merged["Category"] = merged["LOGIC_CLASS"].apply(combined_category)

# define marker styles and labels
marker_styles = {
    'Purple Triangle': ('^', '#47CEF5'),
    'Purple Circle': ('o', '#47CEF5'),
    'Pink Triangle': ('^', '#F54777'),
    'Pink Circle': ('o', '#F54777'),
    'Yellow Triangle': ('^', '#FFB300'),
    'Yellow Circle': ('o', '#FFB300'),
    'Gray Triangle': ('^', '#636363'),
    'Gray Circle': ('o', '#636363')
}
legend_labels = {
    'Purple Triangle': 'In Person and Virtual with Extra Teachers',
    'Purple Circle': 'In Person and Virtual without Extra Teachers',
    'Pink Triangle': 'In Person with Extra Teachers',
    'Pink Circle': 'In Person without Extra Teachers',
    'Yellow Triangle': 'Virtual with Extra Teachers',
    'Yellow Circle': 'Virtual without Extra Teachers',
    'Gray Triangle': 'No CS with Extra Teachers',
    'Gray Circle': 'No CS without Extra Teachers'
}
category_counts = merged['Category'].value_counts()

# convert to GeoDataFrame
gdf = gpd.GeoDataFrame(merged, geometry=gpd.points_from_xy(merged.lon, merged.lat), crs="EPSG:4326")
gdf_3857 = gdf.to_crs(epsg=3857)

# load boundaries and interstates
georgia = ox.geocode_to_gdf("Georgia, USA").to_crs(epsg=3857)

county_url = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"
county_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
urllib.request.urlretrieve(county_url, county_path)
counties = gpd.read_file(f"zip://{county_path}").to_crs(epsg=3857)
ga_counties = counties[counties["STATEFP"] == "13"]

road_url = "https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip"
road_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
urllib.request.urlretrieve(road_url, road_path)
roads = gpd.read_file(f"zip://{road_path}").to_crs(epsg=3857)
interstates = gpd.clip(roads[roads["RTTYP"] == "I"], georgia)

# begin plotting
fig, ax = plt.subplots(figsize=(12, 8))

# background layers
georgia.plot(ax=ax, facecolor='none', edgecolor='gray', linewidth=1)
ga_counties.boundary.plot(ax=ax, edgecolor='gray', linewidth=0.5, alpha=0.5)
interstates.plot(ax=ax, color='gray', linewidth=1.0, alpha=0.9, zorder=1)

# plot schools by category
for category, (marker, color) in marker_styles.items():
    subset = gdf_3857[gdf_3857["Category"] == category]
    if not subset.empty:
        subset.plot(ax=ax, marker=marker, color=color, markersize=20, alpha=0.5,
                    edgecolor='black', linewidth=0.3)

# clean axes
ax.set_axis_off()
xmin, ymin, xmax, ymax = georgia.total_bounds
xpad = (xmax - xmin) * 0.05
ypad = (ymax - ymin) * 0.05
ax.set_xlim(xmin - xpad, xmax + xpad)
ax.set_ylim(ymin - ypad, ymax + ypad)

# legend for modality
legend_elements = []
for category, (marker, color) in marker_styles.items():
    count = category_counts.get(category, 0)
    label = f"{legend_labels.get(category, category)} ({count})"
    legend_elements.append(Line2D([0], [0], marker=marker, color='w',
                                  label=label, markerfacecolor=color,
                                  markeredgecolor='black', markersize=6, alpha=0.5))
leg1 = ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, 0.03),
                 ncol=1, title="CS Enrollment + Extra Teacher", fontsize=8, title_fontsize=9,
                 frameon=True, columnspacing=0.5, handletextpad=0.5)
ax.add_artist(leg1)

# legend for boundaries and highways
leg2 = ax.legend(handles=[
    Line2D([0], [0], color='gray', lw=0.5, label='County Boundaries', alpha=0.5),
    Line2D([0], [0], color='gray', lw=1.0, label='Interstate Highways', alpha=0.9)
], loc='upper right', bbox_to_anchor=(0.9, 0.92), frameon=True, fontsize=9)
ax.add_artist(leg2)

# annotate cities
city_labels = {
    "Atlanta": (33.7490, -84.3880),
    "Savannah": (32.0809, -81.0912),
    "Augusta": (33.4735, -82.0105),
    "Macon": (32.8407, -83.6324)
}
city_gdf = gpd.GeoDataFrame(
    pd.DataFrame(city_labels.items(), columns=["city", "coords"]),
    geometry=[Point(lon, lat) for lat, lon in city_labels.values()],
    crs="EPSG:4326"
).to_crs(epsg=3857)

offsets = {
    "Atlanta": (-120000, 5000),
    "Savannah": (6000, 40000),
    "Augusta": (30000, -8000),
    "Macon": (-170000, -60000)
}

for _, row in city_gdf.iterrows():
    dx, dy = offsets[row.city]
    ax.annotate(
        row.city,
        xy=(row.geometry.x, row.geometry.y),
        xytext=(row.geometry.x + dx, row.geometry.y + dy),
        textcoords='data', fontsize=9,
        ha='right' if dx < 0 else 'left', va='center',
        arrowprops=dict(arrowstyle="-", linewidth=0.7, color="black", shrinkA=0, shrinkB=3)
    )

# save figure
plt.tight_layout()
plt.subplots_adjust(bottom=0.18)
fig.savefig("output/map14_county.png", dpi=300, bbox_inches='tight', bbox_extra_artists=[leg1, leg2])
#plt.show()