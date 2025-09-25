# import required libraries
import psycopg2
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.ops import unary_union
from shapely.geometry import Point
from matplotlib.lines import Line2D
import osmnx as ox
import urllib.request
import tempfile

# connect to PostgreSQL database
conn = psycopg2.connect(
    dbname="cosea_db",
    user="cosea_user",
    password="CoSeaIndex",
    host="pgsql.dataconn.net",
    port="5432"
)

# load RI_Female disparity values and school coordinates
query = """
SELECT 
    ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326) AS geom,
    g."RI_Female"
FROM census.gadoe2024 g
JOIN "2024"."tbl_approvedschools" s
ON g."UNIQUESCHOOLID" = s."UNIQUESCHOOLID"
WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
"""
gdf = gpd.GeoDataFrame.from_postgis(query, conn, geom_col='geom')
conn.close()

# map disparity values to color bins
def classify_disparity(value):
    if -0.864929 <= value <= -0.296520:
        return '#7f2704'
    elif -0.296519 <= value <= -0.211112:
        return '#d94801'
    elif -0.211111 <= value <= -0.051748:
        return '#fdae6b'
    elif -0.051747 <= value <= 0.032609:
        return '#ffffff'
    elif 0.034510 <= value <= 0.257576:
        return '#9ecae1'
    elif 0.257577 <= value <= 0.497095:
        return '#3182bd'
    elif 0.497096 <= value <= 0.652174:
        return '#08519c'
    return None

# assign color and drop any missing values
gdf['Color'] = gdf['RI_Female'].apply(classify_disparity)
gdf = gdf.dropna(subset=['Color'])
gdf_3857 = gdf.to_crs(epsg=3857)

# load state boundary for Georgia
ga_boundary = ox.geocode_to_gdf("Georgia, USA").to_crs(epsg=3857)

# load and filter counties
county_url = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"
county_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
urllib.request.urlretrieve(county_url, county_path)
counties = gpd.read_file("zip://" + county_path).to_crs(epsg=3857)
ga_counties = counties[counties["STATEFP"] == "13"]

# download and filter interstate roads
roads_url = "https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip"
roads_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
urllib.request.urlretrieve(roads_url, roads_path)
roads = gpd.read_file("zip://" + roads_path).to_crs(epsg=3857)
interstates = gpd.clip(roads[roads["RTTYP"] == "I"], ga_boundary)

# initialize figure
fig, ax = plt.subplots(figsize=(12, 8))

# plot state and county outlines
ga_boundary.plot(ax=ax, facecolor='none', edgecolor='gray', linewidth=1)
ga_counties.boundary.plot(ax=ax, edgecolor='gray', linewidth=0.5, alpha=0.5)

# plot interstates
interstates.plot(ax=ax, color='gray', linewidth=1.0, alpha=0.9, zorder=1)

# plot disparity school points 
non_white = gdf_3857[gdf_3857['Color'] != '#ffffff']
white = gdf_3857[gdf_3857['Color'] == '#ffffff']
non_white.plot(ax=ax, color=non_white['Color'], markersize=20, alpha=0.5)
white.plot(ax=ax, color=white['Color'], markersize=20, alpha=0.5,
           edgecolor='black', linewidth=0.3)

# remove axes and grid
ax.set_xticks([]); ax.set_yticks([])
ax.set_xlabel(""); ax.set_ylabel(""); ax.grid(False)
for spine in ax.spines.values():
    spine.set_visible(False)

# pad map extent with buffer
xmin, ymin, xmax, ymax = ga_boundary.total_bounds
xpad = (xmax - xmin) * 0.05
ypad = (ymax - ymin) * 0.05
ax.set_xlim(xmin - xpad, xmax + xpad)
ax.set_ylim(ymin - ypad, ymax + ypad)

# create legend for point color bins
color_bins = {
    '#7f2704': '-0.864929 to -0.296520',
    '#d94801': '-0.296519 to -0.211112',
    '#fdae6b': '-0.211111 to -0.051748',
    '#ffffff': '-0.051747 to 0.032609',
    '#9ecae1': '0.034510 to 0.257576',
    '#3182bd': '0.257577 to 0.497095',
    '#08519c': '0.497096 to 0.652174'
}
legend_elements = []
for color, label in color_bins.items():
    count = (gdf['Color'] == color).sum()
    legend_elements.append(Line2D([0], [0], marker='o', color='w',
                                  label=f"{label} ({count} Schools)",
                                  markerfacecolor=color,
                                  markeredgecolor='black' if color == '#ffffff' else color,
                                  alpha=0.5,
                                  markersize=7))

leg1 = ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, 0.03),
                 ncol=2, title="Female Student Enrollment", fontsize=7, frameon=True,
                 columnspacing=0.6, handletextpad=0.4, borderpad=0.6, borderaxespad=0.2, markerscale=0.8)

# create legend for interstates and county borders
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

# define key cities with coordinates
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

# set label offset positions
offsets = {
    "Atlanta": (-120000, 5000),
    "Savannah": (6000, 40000),
    "Augusta": (30000, -8000),
    "Macon": (-170000, -60000)
}

# add city annotations with arrows
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

# layout and bottom spacing for legend
plt.tight_layout()
plt.subplots_adjust(bottom=0.12)

# save figure
fig.savefig("output/map3_county.png", dpi=300, bbox_inches='tight', bbox_extra_artists=[leg1, leg2])
#plt.show()
