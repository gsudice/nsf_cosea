# import required libraries
import psycopg2
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import osmnx as ox
from shapely.geometry import Point
import urllib.request
import os
import tempfile

# connect to PostgreSQL database
conn = psycopg2.connect(
    dbname="cosea_db",
    user="cosea_user",
    password="CoSeaIndex",
    host="pgsql.dataconn.net",
    port="5432"
)

# load school location data
school_query = """
SELECT "UNIQUESCHOOLID", lat, lon
FROM "2024"."tbl_approvedschools"
"""
school_df = pd.read_sql(school_query, conn)

# load alternate logic classification data
logic_query = """
SELECT "UNIQUESCHOOLID", "LOGIC_CLASS_2"
FROM census.gadoe2024
"""
logic_df = pd.read_sql(logic_query, conn)
conn.close()

# merge datasets and drop rows with missing key info
merged = school_df.merge(logic_df, on="UNIQUESCHOOLID", how="inner")
merged = merged.dropna(subset=["lat", "lon", "LOGIC_CLASS_2"])

# classify each school by CS course modality
def classify(logic_class):
    if logic_class.startswith("11"):
        return "Both"
    elif logic_class.startswith("10"):
        return "In Person"
    elif logic_class.startswith("01"):
        return "Virtual"
    else:
        return "No"

# apply classification function to dataset
merged["Classification"] = merged["LOGIC_CLASS_2"].apply(classify)

# define colors for each modality type
color_map = {
    "Both": "#47CEF5",
    "In Person": "#F54777",
    "Virtual": "#FFB300",
    "No": "#636363"
}
modality_labels = {
    "Both": "In Person and Virtual",
    "In Person": "In Person Only",
    "Virtual": "Virtual Only",
    "No": "No approved CS Class"
}

# map modality to color column
merged["Modality_Color"] = merged["Classification"].map(color_map)

# convert school points into geodataframe with geometry
merged["geometry"] = merged.apply(lambda row: Point(row["lon"], row["lat"]), axis=1)
gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")
gdf_3857 = gdf.to_crs(epsg=3857)

# load Georgia state boundary
ga_boundary = ox.geocode_to_gdf("Georgia, USA").to_crs(epsg=3857)

# load US counties and filter for Georgia
counties = gpd.read_file("https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip")
ga_counties = counties[counties["STATEFP"] == "13"].to_crs(epsg=3857)

# download and read interstate road data
road_url = "https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip"
road_zip = os.path.join(tempfile.gettempdir(), "interstates.zip")
urllib.request.urlretrieve(road_url, road_zip)
roads = gpd.read_file("zip://" + road_zip).to_crs(epsg=3857)
interstates = roads[roads["RTTYP"] == "I"]
interstates = gpd.clip(interstates, ga_boundary)

# initialize plot
fig, ax = plt.subplots(figsize=(12, 8))

# plot state boundary
ga_boundary.plot(ax=ax, facecolor='none', edgecolor='gray', linewidth=1)

# plot county boundaries
ga_counties.boundary.plot(ax=ax, edgecolor='gray', linewidth=0.5, alpha=0.5)

# plot interstates
interstates.plot(ax=ax, color='gray', linewidth=1.0, alpha=0.9, zorder=1)

# plot school dots by modality
gdf_3857.plot(
    ax=ax,
    color=gdf_3857["Modality_Color"],
    markersize=20,
    alpha=0.5,
    edgecolor='black',
    linewidth=0.3,
    zorder=2
)

# remove default axes
ax.set_axis_off()

# create legend for CS modalities
modality_counts = gdf["Classification"].value_counts()
legend_elements = [
    Line2D([0], [0], marker='o', color='w',
           label=f"{modality_labels[k]} ({modality_counts.get(k, 0)})",
           markerfacecolor=color_map[k], markersize=8, alpha=0.5)
    for k in color_map
]
leg1 = ax.legend(
    handles=legend_elements,
    loc='upper center',
    bbox_to_anchor=(0.5, 0.03),
    ncol=2,
    title="Enrollment Modality",
    fontsize=9,
    frameon=True,
    columnspacing=0.8,
    handletextpad=0.4,
    borderpad=0.6,
    borderaxespad=0.2
)

# create legend for boundaries and roads
legend_elements_extra = [
    Line2D([0], [0], color='gray', lw=0.5, label='County Boundaries', alpha=0.5),
    Line2D([0], [0], color='gray', lw=1.0, label='Interstate Highways', alpha=0.9)
]
leg2 = ax.legend(
    handles=legend_elements_extra,
    loc='upper right',
    bbox_to_anchor=(0.9, 0.92),
    frameon=True,
    fontsize=9
)
ax.add_artist(leg1)

# set bounds with padding around Georgia
xmin, ymin, xmax, ymax = ga_boundary.total_bounds
xpad = (xmax - xmin) * 0.05
ypad = (ymax - ymin) * 0.05
ax.set_xlim(xmin - xpad, xmax + xpad)
ax.set_ylim(ymin - ypad, ymax + ypad)

# manually define major Georgia cities
city_labels = {
    "Atlanta": (33.7490, -84.3880),
    "Savannah": (32.0809, -81.0912),
    "Augusta": (33.4735, -82.0105),
    "Macon": (32.8407, -83.6324)
}

# convert city points to geodataframe
city_gdf = gpd.GeoDataFrame(
    pd.DataFrame(city_labels.items(), columns=["city", "coords"]),
    geometry=[Point(lon, lat) for lat, lon in city_labels.values()],
    crs="EPSG:4326"
).to_crs(epsg=3857)

# set manual label offsets for clarity
offsets = {
    "Atlanta": (-120000, 5000),
    "Savannah": (6000, 40000),
    "Augusta": (30000, -8000),
    "Macon": (-170000, -60000)
}

# annotate cities with directional arrows
for idx, row in city_gdf.iterrows():
    x, y = row.geometry.x, row.geometry.y
    dx, dy = offsets[row.city]
    ax.annotate(
        row.city,
        xy=(x, y),
        xytext=(x + dx, y + dy),
        textcoords='data',
        fontsize=9,
        ha='right' if dx < 0 else 'left',
        va='center',
        arrowprops=dict(arrowstyle="-", linewidth=0.7, color="black", shrinkA=0, shrinkB=3)
    )

# adjust layout and spacing
plt.tight_layout()
plt.subplots_adjust(bottom=0.12)

# save figure
fig.savefig("output/map2_county.png", dpi=300, bbox_inches='tight', bbox_extra_artists=[leg1, leg2])
#plt.show()
