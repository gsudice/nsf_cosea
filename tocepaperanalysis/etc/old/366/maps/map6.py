# import required libraries
import psycopg2
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap
from shapely.geometry import Point
import osmnx as ox
import urllib.request
import tempfile

# connect to PostgreSQL database
conn = psycopg2.connect(
    dbname="cosea_db", user="cosea_user", password="CoSeaIndex", host="pgsql.dataconn.net", port="5432"
)

# load White CS enrollment disparity and school coordinates
query = """
SELECT 
    ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326) AS geom,
    g."RI_White"
FROM census.gadoe2024 g
JOIN "2024"."tbl_approvedschools" s
ON g."UNIQUESCHOOLID" = s."UNIQUESCHOOLID"
WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
"""
school_gdf = gpd.GeoDataFrame.from_postgis(query, conn, geom_col='geom')

# load White population ratios from ACS
pop_sql = """
SELECT geoid, white_alone_non_hispanic, total_population
FROM census.acs2023_combined;
"""
pop_df = pd.read_sql(pop_sql, conn)
pop_df['geoid'] = pop_df['geoid'].astype(str).str.zfill(12)
pop_df['white_ratio'] = pop_df['white_alone_non_hispanic'] / pop_df['total_population']

# load block group geometries
block_query = """
SELECT "GEOID", ST_Transform(cbgpolygeom, 4326) AS geom
FROM "2024"."tbl_cbg_finalassignment"
"""
block_groups = gpd.read_postgis(block_query, conn, geom_col='geom')
conn.close()

# merge population ratio with block geometries
block_groups['GEOID'] = block_groups['GEOID'].astype(str).str.zfill(12)
block_groups = block_groups.merge(pop_df[['geoid', 'white_ratio']], left_on='GEOID', right_on='geoid', how='left')
block_groups['white_ratio_class'] = pd.qcut(block_groups['white_ratio'], 5, labels=False, duplicates='drop')

# define disparity bins and associated colors
disparity_bins = [-0.627130, -0.168843, -0.082320, -0.050197, 0.049292, 0.090172, 0.162600, 0.981273]
disparity_colors = ['#7f2704', '#d94801', '#fdae6b', '#ffffff', '#9ecae1', '#3182bd', '#08519c']

# classify each school by disparity bin
def classify_disparity(val):
    if pd.isnull(val): return None
    for i in range(7):
        if disparity_bins[i] <= val <= disparity_bins[i+1]:
            return disparity_colors[i]
    return None

school_gdf['disparity_color'] = pd.to_numeric(school_gdf['RI_White'], errors='coerce').apply(classify_disparity)
school_gdf = school_gdf.dropna(subset=['disparity_color'])

# convert to web mercator projection
block_groups_3857 = block_groups.to_crs(epsg=3857)
school_gdf_3857 = school_gdf.to_crs(epsg=3857)
georgia_boundary = ox.geocode_to_gdf("Georgia, USA").to_crs(epsg=3857)

# load and filter counties
county_url = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"
county_tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
urllib.request.urlretrieve(county_url, county_tmp)
counties = gpd.read_file("zip://" + county_tmp).to_crs(epsg=3857)
ga_counties = counties[counties["STATEFP"] == "13"]

# load and filter interstates
roads_url = "https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip"
roads_tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
urllib.request.urlretrieve(roads_url, roads_tmp)
roads = gpd.read_file("zip://" + roads_tmp).to_crs(epsg=3857)
interstates = gpd.clip(roads[roads["RTTYP"] == "I"], georgia_boundary)

# initialize figure
fig, ax = plt.subplots(figsize=(12, 8))
gray_colors = ["#f0f0f0", "#bdbdbd", "#969696", "#636363", "#252525"]
gray_cmap = ListedColormap(gray_colors)

# plot block group underlay
block_groups_3857.plot(column='white_ratio_class', cmap=gray_cmap, ax=ax, edgecolor='none', alpha=0.6)

# plot base layers
georgia_boundary.plot(ax=ax, facecolor='none', edgecolor='gray', linewidth=1)
ga_counties.boundary.plot(ax=ax, edgecolor='gray', linewidth=0.5, alpha=0.5)
interstates.plot(ax=ax, color='gray', linewidth=1.0, alpha=0.9)

# plot school dots
white_pts = school_gdf_3857[school_gdf_3857['disparity_color'] == '#ffffff']
non_white_pts = school_gdf_3857[school_gdf_3857['disparity_color'] != '#ffffff']
non_white_pts.plot(ax=ax, color=non_white_pts['disparity_color'], markersize=20, alpha=0.8,
                   edgecolor=non_white_pts['disparity_color'], linewidth=0.3)
white_pts.plot(ax=ax, color='#ffffff', markersize=20, alpha=0.8,
               edgecolor='black', linewidth=0.6)

# remove axes and set limits
ax.set_axis_off()
xmin, ymin, xmax, ymax = block_groups_3857.total_bounds
xpad, ypad = (xmax - xmin) * 0.05, (ymax - ymin) * 0.05
ax.set_xlim(xmin - xpad, xmax + xpad)
ax.set_ylim(ymin - ypad, ymax + ypad)

# legend 1: block group underlay
bg_labels = ["Lowest 20%", "20–40%", "40–60%", "60–80%", "Highest 20%"]
legend_handles_bg = [
    Line2D([0], [0], marker='s', linestyle='None', color='w',
           markerfacecolor=gray_colors[i], markersize=8, label=bg_labels[i])
    for i in range(5)
]
leg1 = ax.legend(handles=legend_handles_bg, title="White Population (Underlay)",
                 loc='upper center', bbox_to_anchor=(0.35, 0.03), frameon=True,
                 fontsize=8, title_fontsize=9)
ax.add_artist(leg1)

# legend 2: disparity bins
legend_labels_sp = [
    f"{disparity_bins[i]:.6f} – {disparity_bins[i+1]:.6f} "
    f"({(school_gdf_3857['disparity_color'] == disparity_colors[i]).sum()} schools)"
    for i in range(len(disparity_colors))
]
legend_handles_sp = [
    Line2D([0], [0], marker='o', linestyle='None',
           markerfacecolor=disparity_colors[i], alpha=0.8,
           markeredgecolor='black' if disparity_colors[i] == '#ffffff' else disparity_colors[i],
           label=legend_labels_sp[i], markersize=6)
    for i in range(len(disparity_colors))
]
leg2 = ax.legend(handles=legend_handles_sp, title="White CS Enrollment Disparity",
                 loc='upper center', bbox_to_anchor=(0.75, 0.03), frameon=True,
                 fontsize=8, title_fontsize=9)
ax.add_artist(leg2)

# legend 3: interstates and counties
legend_elements_extra = [
    Line2D([0], [0], color='gray', lw=0.5, label='County Boundaries', alpha=0.5),
    Line2D([0], [0], color='gray', lw=1.0, label='Interstate Highways', alpha=0.9)
]
leg3 = ax.legend(handles=legend_elements_extra,
                 loc='upper right', bbox_to_anchor=(0.9, 0.92),
                 frameon=True, fontsize=9)
ax.add_artist(leg3)

# add city labels with arrows
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
for idx, row in city_gdf.iterrows():
    x, y = row.geometry.x, row.geometry.y
    dx, dy = offsets[row.city]
    ax.annotate(
        row.city,
        xy=(x, y), xytext=(x + dx, y + dy),
        textcoords='data', fontsize=9,
        ha='right' if dx < 0 else 'left',
        va='center',
        arrowprops=dict(arrowstyle="-", linewidth=0.7, color="black", shrinkA=0, shrinkB=3)
    )

# save figure
plt.tight_layout()
plt.subplots_adjust(bottom=0.15)
fig.savefig("output/map6_county.png", dpi=300, bbox_inches='tight', bbox_extra_artists=[leg1, leg2, leg3])
#plt.show()
