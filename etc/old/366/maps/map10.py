# import libraries
import psycopg2
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box, Point
from shapely.geometry import MultiLineString
import urllib.request
import tempfile
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap

# connect to database
conn = psycopg2.connect(
    dbname="cosea_db",
    user="cosea_user",
    password="CoSeaIndex",
    host="pgsql.dataconn.net",
    port="5432"
)

# define Atlanta bounding box and convert to EPSG:3857
bounds = {"minx": -85.5, "maxx": -82.8, "miny": 32.8, "maxy": 34.5}
clip_box = gpd.GeoDataFrame(
    geometry=[box(bounds["minx"], bounds["miny"], bounds["maxx"], bounds["maxy"])],
    crs="EPSG:4326"
).to_crs(epsg=3857)

# query school disparity data
school_query = """
SELECT ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326) AS geom, g."RI_Black"
FROM census.gadoe2024 g
JOIN "2024"."tbl_approvedschools" s ON g."UNIQUESCHOOLID" = s."UNIQUESCHOOLID"
WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
"""
school_gdf = gpd.GeoDataFrame.from_postgis(school_query, conn, geom_col='geom')
school_gdf['black_disparity'] = pd.to_numeric(school_gdf['RI_Black'], errors='coerce')
school_gdf = school_gdf.cx[bounds["minx"]:bounds["maxx"], bounds["miny"]:bounds["maxy"]]

# classify disparity into color bins
disparity_bins = [-0.864929, -0.168258, -0.088616, -0.050715, 0.049845, 0.088608, 0.139144, 0.684211]
disparity_colors = ['#7f2704', '#d94801', '#fdae6b', '#ffffff', '#9ecae1', '#3182bd', '#08519c']
def classify_disparity(val):
    for i in range(7):
        if disparity_bins[i] <= val <= disparity_bins[i+1]:
            return disparity_colors[i]
    return None
school_gdf['disparity_color'] = school_gdf['black_disparity'].apply(classify_disparity)
school_gdf = school_gdf.dropna(subset=['disparity_color'])

# query education data
edu_query = "SELECT geoid, edu_hs_or_more FROM census.acs2023_combined"
edu_df = pd.read_sql(edu_query, conn)
edu_df['geoid'] = edu_df['geoid'].astype(str).str.zfill(12)
edu_df['edu_hs_or_more'] = pd.to_numeric(edu_df['edu_hs_or_more'], errors='coerce')

# block group geometries
block_query = 'SELECT "GEOID", ST_Transform(cbgpolygeom, 4326) AS geom FROM "2024"."tbl_cbg_finalassignment"'
block_groups = gpd.read_postgis(block_query, conn, geom_col='geom')
conn.close()
block_groups['GEOID'] = block_groups['GEOID'].astype(str).str.zfill(12)
block_groups = block_groups.cx[bounds["minx"]:bounds["maxx"], bounds["miny"]:bounds["maxy"]]
block_groups = block_groups.merge(edu_df, left_on='GEOID', right_on='geoid', how='left')

# education level classification
edu_bins = [0, 508, 832, 1199, 1711, 3965]
block_groups['edu_class'] = pd.cut(block_groups['edu_hs_or_more'], bins=edu_bins, labels=False, include_lowest=True)

def load_shapefile(url):
    path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name
    urllib.request.urlretrieve(url, path)
    return gpd.read_file("zip://" + path).to_crs(epsg=3857)

counties = load_shapefile("https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip")
roads = load_shapefile("https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip")
ga_counties = gpd.clip(counties[counties["STATEFP"] == "13"], clip_box)
interstates = gpd.clip(roads[roads["RTTYP"] == "I"], clip_box)

# reproject to 3857
school_gdf_3857 = school_gdf.to_crs(epsg=3857)
block_groups_3857 = block_groups.to_crs(epsg=3857)

# create plot
fig, ax = plt.subplots(figsize=(10, 7))
gray_cmap = ListedColormap(["#f0f0f0", "#bdbdbd", "#969696", "#636363", "#252525"])
block_groups_3857.plot(column='edu_class', cmap=gray_cmap, ax=ax, edgecolor='none', alpha=0.6)
ga_counties.boundary.plot(ax=ax, edgecolor='gray', linewidth=0.5, alpha=0.5)
interstates.plot(ax=ax, color='gray', linewidth=1.0, alpha=0.9)

# school points
white_pts = school_gdf_3857[school_gdf_3857['disparity_color'] == '#ffffff']
non_white_pts = school_gdf_3857[school_gdf_3857['disparity_color'] != '#ffffff']
non_white_pts.plot(ax=ax, color=non_white_pts['disparity_color'], markersize=20, alpha=0.8,
                   edgecolor=non_white_pts['disparity_color'], linewidth=0.3)
white_pts.plot(ax=ax, color='#ffffff', markersize=20, alpha=0.8,
               edgecolor='black', linewidth=0.6)

# remove axis
ax.set_axis_off()

# legend for underlay
bg_labels = ["0–508", "509–832", "833–1199", "1200–1711", "1712–3965"]
legend_bg = [
    Line2D([0], [0], marker='s', linestyle='None', color='w', markerfacecolor=gray_cmap.colors[i], markersize=8, label=bg_labels[i])
    for i in range(5)
]
leg1 = ax.legend(handles=legend_bg, title="High School or More (Underlay)", loc='upper center',
                 bbox_to_anchor=(0.35, 0.03), frameon=True, fontsize=8, title_fontsize=9)
ax.add_artist(leg1)

# legend for disparity
legend_sp = [
    Line2D([0], [0], marker='o', linestyle='None',
           markerfacecolor=disparity_colors[i], alpha=0.8,
           markeredgecolor='black' if disparity_colors[i] == '#ffffff' else disparity_colors[i],
           label=f"{disparity_bins[i]:.6f} – {disparity_bins[i+1]:.6f} ({(school_gdf_3857['disparity_color'] == disparity_colors[i]).sum()} schools)",
           markersize=6)
    for i in range(7)
]
leg2 = ax.legend(handles=legend_sp, title="Black Disparity (Schools)", loc='upper center',
                 bbox_to_anchor=(0.75, 0.03), frameon=True, fontsize=8, title_fontsize=9)
ax.add_artist(leg2)

# legend for boundaries and roads
legend_extra = [
    Line2D([0], [0], color='gray', lw=0.5, label='County Boundaries', alpha=0.5),
    Line2D([0], [0], color='gray', lw=1.0, label='Interstate Highways', alpha=0.9)
]
leg3 = ax.legend(handles=legend_extra, loc='center left', bbox_to_anchor=(0.93, 0.75), frameon=True, fontsize=8)
ax.add_artist(leg3)

# annotate I-85
interstates['max_y'] = interstates.bounds['maxy']
top_edge_segment = interstates.sort_values(by='max_y', ascending=False).iloc[0]
midpoint = top_edge_segment.geometry.interpolate(0.5, normalized=True)
ax.annotate("I-85",
            xy=(midpoint.x, midpoint.y),
            xytext=(midpoint.x, midpoint.y + 12000),
            textcoords='data',
            fontsize=9,
            color='black',
            ha='center',
            va='bottom',
            arrowprops=dict(arrowstyle='-', linewidth=0.7, color='black'))
interstates.drop(columns='max_y', inplace=True)

# save figure
plt.tight_layout()
plt.subplots_adjust(bottom=0.25)
fig.savefig("output/map10_county.png", dpi=300, bbox_inches='tight', bbox_extra_artists=[leg1, leg2, leg3])
#plt.show()
