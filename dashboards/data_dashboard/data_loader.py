from data_dashboard.settings import *
import os
import tempfile
import requests
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine
import pandas as pd
import json


def ratio_fmt(val):
    if pd.isnull(val) or val is None:
        return '0.0 students per teacher'
    try:
        return f"{val:.1f} students per teacher"
    except Exception:
        return '0.0 students per teacher'


def build_unified_hover(row, template, disparity_col=None, ri_cols=None):
    # Common fields
    school_name = row.get("SCHOOL_NAME", "")
    district = row.get("SYSTEM_NAME", "") or row.get("district", "")
    city = row.get("School City", "") or row.get("city", "")
    locale = row.get("Locale", "") or row.get("locale", "")
    grade_range = row.get("GRADE_RANGE", "")
    cs_enrollment = row.get("CS_Enrollment", 0)
    approved_teachers = row.get("approved_teachers", 0)
    extra_teachers = row.get("extra_teachers", 0)
    ratio_display = row.get("ratio_display", ratio_fmt(
        cs_enrollment / approved_teachers if approved_teachers else 0))

    # If not in row, fetch from data
    if "approved_teachers" not in row:
        school_id = str(row["UNIQUESCHOOLID"])
        approved_teachers = SCHOOLDATA["approved_teachers_count"].get(
            school_id, 0)
        extra_teachers = SCHOOLDATA["extra_teachers_count"].get(school_id, 0)
        ratio_display = ratio_fmt(
            cs_enrollment / approved_teachers if approved_teachers else 0)

    # Race and RI
    total_race_vals = ""
    cs_race_vals = ""
    ri_vals = ""

    if disparity_col and ri_cols:
        # It's disparity view, data is in row
        total_race_map = {
            "RI_Asian": ("Race: Asian", "Total Asian"),
            "RI_Black": ("Race: Black", "Total Black"),
            "RI_Hispanic": ("Ethnicity: Hispanic", "Total Hispanic"),
            "RI_White": ("Race: White", "Total White"),
        }

        if disparity_col == "RI_Female":
            total_race_vals = f"Total Student Count: {row.get('Total Student Count', '')}<br>Total Female: {row.get('Female', '')}<br>Total Male: {row.get('Male', '')}"
            cs_race_vals = f"CS Female: {int(row.get('CS_Female', 0))}<br>CS Male: {int(row.get('CS_Male', 0))}"
            ri_vals = f"<b>RI Female: {row.get('RI_Female', 0):.4f}</b>"
        else:
            total_race_vals_list = []
            for ri_key, (total_col, total_label) in total_race_map.items():
                val = row.get(total_col, None)
                if pd.notnull(val):
                    total_race_vals_list.append(f"{total_label}: {int(val)}")
            total_race_vals = "<br>".join(total_race_vals_list)

            cs_race_cols = ["CS_Asian", "CS_Black", "CS_Hispanic", "CS_White"]
            cs_race_labels = {
                "CS_Asian": "CS Asian",
                "CS_Black": "CS Black",
                "CS_Hispanic": "CS Hispanic",
                "CS_White": "CS White"
            }
            cs_race_vals_list = []
            for cs_col in cs_race_cols:
                val = row.get(cs_col, None)
                if pd.notnull(val):
                    cs_race_vals_list.append(
                        f"{cs_race_labels[cs_col]}: {int(val)}")
            cs_race_vals = "<br>".join(cs_race_vals_list)

            ri_vals_list = []
            for col in ri_cols:
                if col in row:
                    val = row[col]
                    if pd.notnull(val):
                        bold = "Female" in col or col == disparity_col
                        txt = f"RI {col.replace('RI_', '')}: {val:.4f}"
                        if bold:
                            ri_vals_list.append(f"<b>{txt}</b>")
                        else:
                            ri_vals_list.append(txt)
            ri_vals = "<br>".join(ri_vals_list)
    else:
        # Modality view, use row data directly
        total_race_vals_list = []
        race_cols = ["Race: Asian", "Race: Black",
                     "Ethnicity: Hispanic", "Race: White"]
        race_labels = ["Total Asian", "Total Black",
                       "Total Hispanic", "Total White"]
        for col, label in zip(race_cols, race_labels):
            val = row.get(col, None)
            if pd.notnull(val):
                total_race_vals_list.append(f"{label}: {int(val)}")
        # Add total, female, male
        total_students = row.get("Total Student Count", None)
        if pd.notnull(total_students):
            total_race_vals_list.insert(
                0, f"Total Students: {int(total_students)}")
        female = row.get("Female", None)
        if pd.notnull(female):
            total_race_vals_list.append(f"Female: {int(female)}")
        male = row.get("Male", None)
        if pd.notnull(male):
            total_race_vals_list.append(f"Male: {int(male)}")
        total_race_vals = "<br>".join(total_race_vals_list)

        # Fetch disparity data for CS race and RI
        school_id = str(row["UNIQUESCHOOLID"])
        disparity_row = SCHOOLDATA["disparity"][SCHOOLDATA["disparity"]
                                                ["UNIQUESCHOOLID"] == school_id]
        if not disparity_row.empty:
            drow = disparity_row.iloc[0]
            cs_race_cols = ["CS_Asian", "CS_Black", "CS_Hispanic", "CS_White"]
            cs_race_labels = {
                "CS_Asian": "CS Asian",
                "CS_Black": "CS Black",
                "CS_Hispanic": "CS Hispanic",
                "CS_White": "CS White"
            }
            cs_race_vals_list = []
            for cs_col in cs_race_cols:
                val = drow.get(cs_col, None)
                if pd.notnull(val):
                    cs_race_vals_list.append(
                        f"{cs_race_labels[cs_col]}: {int(val)}")
            cs_race_vals = "<br>".join(cs_race_vals_list)

            ri_vals_list = []
            for col in ["RI_Asian", "RI_Black", "RI_Hispanic", "RI_White", "RI_Female"]:
                val = drow.get(col, None)
                if pd.notnull(val):
                    txt = f"RI {col.replace('RI_', '')}: {val:.4f}"
                    ri_vals_list.append(txt)
            ri_vals = "<br>".join(ri_vals_list)
        else:
            cs_race_vals = ""
            ri_vals = ""

    cs_enrollment_val = row.get("CS_Enrollment", 0)
    if pd.notnull(cs_enrollment_val):
        cs_enrollment_str = int(cs_enrollment_val)
    else:
        cs_enrollment_str = ''

    approved_teachers_val = approved_teachers
    if pd.notnull(approved_teachers_val):
        approved_teachers_str = int(approved_teachers_val)
    else:
        approved_teachers_str = 0

    extra_teachers_val = extra_teachers
    if pd.notnull(extra_teachers_val):
        extra_teachers_str = int(extra_teachers_val)
    else:
        extra_teachers_str = 0

    return template.format(
        SCHOOL_NAME=school_name,
        district=district,
        city=city,
        locale=locale,
        GRADE_RANGE=grade_range,
        CS_Enrollment=cs_enrollment_str,
        approved_teachers=approved_teachers_str,
        extra_teachers=extra_teachers_str,
        ratio_display=ratio_display,
        total_race_vals=total_race_vals,
        cs_race_vals=cs_race_vals,
        ri_vals=ri_vals
    )


def classify_modality(logic_class):
    if logic_class.startswith("11"):
        return "Both"
    elif logic_class.startswith("10"):
        return "In Person"
    elif logic_class.startswith("01"):
        return "Virtual"
    else:
        return "No"


def classify_modality_with_teachers(logic_class):
    """Classify modality with teacher status - circles for no extra teachers, triangles for extra teachers"""
    if pd.isna(logic_class) or not isinstance(logic_class, str) or len(logic_class) < 3:
        return "No"

    prefix = logic_class[:2]  # modality
    # teacher status (1=extra teachers, 0=no extra teachers)
    suffix = logic_class[-1]

    if prefix == "11" and suffix == "1":
        return "Both + Extra Teachers"
    elif prefix == "11" and suffix == "0":
        return "Both"
    elif prefix == "10" and suffix == "1":
        return "In Person + Extra Teachers"
    elif prefix == "10" and suffix == "0":
        return "In Person"
    elif prefix == "01" and suffix == "1":
        return "Virtual + Extra Teachers"
    elif prefix == "01" and suffix == "0":
        return "Virtual"
    elif prefix == "00" and suffix == "1":
        return "No CS + Extra Teachers"
    elif prefix == "00" and suffix == "0":
        return "No"
    else:
        return "No"


def get_ri_bin_edges(vals, eps=1e-6):
    below_vals = vals[vals < -0.05]
    above_vals = vals[vals > 0.05]
    if len(below_vals) > 1:
        min_below = below_vals.min()
        max_below = below_vals.max()
        mid_below = (min_below + max_below) / 2
        below_edges = [min_below, mid_below]
    elif len(below_vals) == 1:
        min_below = max_below = below_vals.iloc[0]
        below_edges = [min_below, min_below + eps]
    else:
        below_edges = [-0.05, -0.05 + eps]
    if len(above_vals) > 1:
        min_above = above_vals.min()
        max_above = above_vals.max()
        mid_above = (min_above + max_above) / 2
        above_edges = [0.05, mid_above, max_above]
        above_edges = [above_edges[1], above_edges[2]]
    elif len(above_vals) == 1:
        min_above = max_above = above_vals.iloc[0]
        above_edges = [min_above, min_above + eps]
    else:
        above_edges = [0.05, 0.05 + eps]
    bin_edges = [below_edges[0], below_edges[1], -
                 0.05, 0.05, above_edges[0], above_edges[1]]
    for i in range(1, len(bin_edges)):
        if bin_edges[i] <= bin_edges[i-1]:
            bin_edges[i] = bin_edges[i-1] + eps
    return bin_edges


def get_gender_color(val, color_bins):
    for b in color_bins:
        if b[0] <= val <= b[1]:
            return b[2]
    return None


engine = create_engine(DATABASE_URL)


def load_all_school_data():
    gadoe = pd.read_sql('SELECT * FROM "census"."gadoe2024_389"', engine)

    course_logic = pd.read_sql(
        'SELECT * FROM "census"."course_logic_2024_389"', engine)

    approved_all = pd.read_sql(
        'SELECT * FROM "allhsgrades24"."tbl_approvedschools"', engine)

    approved_logic = course_logic[(course_logic["approved_flag"] == True) & (
        course_logic["certified_flag"] == True)]
    modality_counts = approved_logic.groupby(
        ["UNIQUESCHOOLID", "is_virtual"]).size().unstack(fill_value=0).reset_index()
    modality_counts = modality_counts.rename(columns={
        True: "virtual_course_count",
        False: "inperson_course_count"
    })
    if "virtual_course_count" not in modality_counts:
        modality_counts["virtual_course_count"] = 0
    if "inperson_course_count" not in modality_counts:
        modality_counts["inperson_course_count"] = 0

    approved_logic2 = course_logic[(course_logic["approved_flag_2"] == True) & (
        course_logic["certified_flag_2"] == True)]
    modality_counts2 = approved_logic2.groupby(
        ["UNIQUESCHOOLID", "is_virtual"]).size().unstack(fill_value=0).reset_index()
    modality_counts2 = modality_counts2.rename(columns={
        True: "virtual_course_count_2",
        False: "inperson_course_count_2"
    })
    if "virtual_course_count_2" not in modality_counts2:
        modality_counts2["virtual_course_count_2"] = 0
    if "inperson_course_count_2" not in modality_counts2:
        modality_counts2["inperson_course_count_2"] = 0

    approved_counts = approved_logic.groupby(
        "UNIQUESCHOOLID").size().reset_index(name="approved_course_count")
    approved_counts2 = approved_logic2.groupby(
        "UNIQUESCHOOLID").size().reset_index(name="approved_course_count_2")

    school_modality_info = approved_all[[
        "UNIQUESCHOOLID", "SCHOOL_NAME", "GRADE_RANGE", "lat", "lon"
    ]].merge(modality_counts, on="UNIQUESCHOOLID", how="left")
    school_modality_info = school_modality_info.merge(
        modality_counts2, on="UNIQUESCHOOLID", how="left")
    school_modality_info = school_modality_info.merge(
        approved_counts, on="UNIQUESCHOOLID", how="left")
    school_modality_info = school_modality_info.merge(
        approved_counts2, on="UNIQUESCHOOLID", how="left")
    for col in ["virtual_course_count", "inperson_course_count", "virtual_course_count_2", "inperson_course_count_2", "approved_course_count", "approved_course_count_2"]:
        if col in school_modality_info:
            school_modality_info[col] = school_modality_info[col].fillna(
                0).astype(int)

    ri_cols = ["RI_Asian", "RI_Black", "RI_Hispanic", "RI_White", "RI_Female"]
    cs_race_cols = ["CS_Asian", "CS_Black", "CS_Hispanic", "CS_White"]
    extra_cols = ["CS_Enrollment", "CS_Female",
                  "CS_Male", "Certified_Teachers"] + cs_race_cols
    all_cols = ri_cols + extra_cols
    disparity_query = f'SELECT "UNIQUESCHOOLID", {', '.join([f'"{col}"' for col in all_cols])
                                                  } FROM census.gadoe2024_389'
    disparity = pd.read_sql(disparity_query, engine)

    gender_query = (
        'SELECT s."UNIQUESCHOOLID", s.lat, s.lon, g."RI_Female" '
        'FROM "allhsgrades24"."tbl_approvedschools" s '
        'JOIN census.gadoe2024_389 g ON s."UNIQUESCHOOLID" = g."UNIQUESCHOOLID" '
        'WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL'
    )
    gender = pd.read_sql(gender_query, engine)

    # Load courses data
    approved_courses = course_logic[course_logic['approved_flag_2'] == 1]
    courses_grouped = approved_courses.groupby(
        ['UNIQUESCHOOLID', 'COURSE_TITLE', 'is_virtual']).size().reset_index(name='count')
    courses_dict = {}
    for _, row in courses_grouped.iterrows():
        school_id = str(row['UNIQUESCHOOLID'])
        course = row['COURSE_TITLE'].lower()
        is_virtual = row['is_virtual']
        count = row['count']
        if school_id not in courses_dict:
            courses_dict[school_id] = {}
        if course not in courses_dict[school_id]:
            courses_dict[school_id][course] = {'virtual': 0, 'inperson': 0}
        if is_virtual:
            courses_dict[school_id][course]['virtual'] += count
        else:
            courses_dict[school_id][course]['inperson'] += count

    school_names = {str(k): v for k, v in zip(
        approved_all['UNIQUESCHOOLID'], approved_all['SCHOOL_NAME'])}

    # Compute extra teachers
    extra_teachers = {}
    approved_teachers_count = {}
    extra_teachers_count = {}
    for school_id in course_logic["UNIQUESCHOOLID"].unique():
        school_courses = course_logic[course_logic["UNIQUESCHOOLID"] == school_id]
        approved_certs = set(
            school_courses[school_courses["approved_flag_2"] == True]["CERTIFICATE_ID"].dropna())
        all_certs = set(school_courses["CERTIFICATE_ID"].dropna())
        extra_teachers[str(school_id)] = len(all_certs) > len(approved_certs)
        approved_teachers_count[str(school_id)] = len(approved_certs)
        extra_teachers_count[str(school_id)] = len(
            all_certs) - len(approved_certs)

    return {
        "gadoe": gadoe,
        "course_logic": course_logic,
        "approved_all": approved_all,
        "school_modality_info": school_modality_info,
        "disparity": disparity,
        "gender": gender,
        "courses": courses_dict,
        "school_names": school_names,
        "extra_teachers": extra_teachers,
        "approved_teachers_count": approved_teachers_count,
        "extra_teachers_count": extra_teachers_count
    }


def load_geodata():
    ga_boundary = ox.geocode_to_gdf(GA_OSM_QUERY).to_crs(epsg=4326)
    county_url = COUNTY_SHAPEFILE_URL
    county_zip = os.path.join(tempfile.gettempdir(), "tl_2022_us_county.zip")
    if not os.path.exists(county_zip):
        r = requests.get(county_url, verify=False)
        with open(county_zip, "wb") as f:
            f.write(r.content)
    counties = gpd.read_file(f"zip://{county_zip}")
    ga_counties = counties[counties["STATEFP"] == "13"].to_crs(epsg=4326)
    county_lines = []
    for _, row in ga_counties.iterrows():
        geom = row.geometry
        if isinstance(geom, Polygon):
            x, y = geom.exterior.xy
            county_lines.append((list(x), list(y)))
        elif isinstance(geom, MultiPolygon):
            for poly in geom.geoms:
                x, y = poly.exterior.xy
                county_lines.append((list(x), list(y)))
    road_url = ROAD_SHAPEFILE_URL
    road_zip = os.path.join(tempfile.gettempdir(),
                            "tl_2022_us_primaryroads.zip")
    if not os.path.exists(road_zip):
        r = requests.get(road_url, verify=False)
        with open(road_zip, "wb") as f:
            f.write(r.content)
    roads = gpd.read_file(f"zip://{road_zip}")
    interstates = roads[roads["RTTYP"] == "I"].to_crs(epsg=4326)
    interstates = gpd.clip(interstates, ga_boundary)
    highway_lines = []
    for _, row in interstates.iterrows():
        geom = row.geometry
        x, y = geom.xy
        highway_lines.append((list(x), list(y)))
    ga_outline = []
    for _, row in ga_boundary.iterrows():
        geom = row.geometry
        if isinstance(geom, Polygon):
            x, y = geom.exterior.xy
            ga_outline.append((list(x), list(y)))
        elif isinstance(geom, MultiPolygon):
            for poly in geom.geoms:
                x, y = poly.exterior.xy
                ga_outline.append((list(x), list(y)))
    return {
        "ga_boundary": ga_boundary,
        "county_lines": county_lines,
        "highway_lines": highway_lines,
        "ga_outline": ga_outline
    }


def load_cbg_underlay(selected_field, bins=5):
    """
    Load block group geometries and ACS data for the selected field.
    Returns GeoDataFrame with binned values for grayscale mapping.
    """
    # Load block group geometries
    block_query = (
        'SELECT "GEOID", ST_Transform(cbgpolygeom, 4326) AS geom FROM "allhsgrades24"."tbl_cbg_finalassignment" '
    )
    block_groups = gpd.read_postgis(block_query, engine, geom_col='geom')
    block_groups['GEOID'] = block_groups['GEOID'].astype(str).str.zfill(12)

    # Simplify geometries to reduce complexity for faster rendering
    block_groups['geom'] = block_groups['geom'].simplify(
        tolerance=0.0001, preserve_topology=True)

    # Load ACS data for selected field
    if selected_field == "black_population_ratio":
        acs_query = 'SELECT geoid, "black_alone_non_hispanic", "total_population" FROM census.acs2023_combined'
        acs_df = pd.read_sql(acs_query, engine)
        acs_df['geoid'] = acs_df['geoid'].astype(str).str.zfill(12)
        acs_df[selected_field] = acs_df['black_alone_non_hispanic'] / \
            acs_df['total_population']
    elif selected_field == "median_household_income":
        acs_query = 'SELECT geoid, median_household_income FROM census.acs2023_combined'
        acs_df = pd.read_sql(acs_query, engine)
        acs_df['geoid'] = acs_df['geoid'].astype(str).str.zfill(12)
        acs_df[selected_field] = pd.to_numeric(
            acs_df[selected_field], errors='coerce')
    elif selected_field == "edu_hs_or_more":
        acs_query = 'SELECT geoid, edu_hs_or_more FROM census.acs2023_combined'
        acs_df = pd.read_sql(acs_query, engine)
        acs_df['geoid'] = acs_df['geoid'].astype(str).str.zfill(12)
        acs_df[selected_field] = pd.to_numeric(
            acs_df[selected_field], errors='coerce')
    elif selected_field == "households_with_subscription":
        acs_query = 'SELECT geoid, households_with_subscription FROM census.acs2023_combined'
        acs_df = pd.read_sql(acs_query, engine)
        acs_df['geoid'] = acs_df['geoid'].astype(str).str.zfill(12)
        acs_df[selected_field] = pd.to_numeric(
            acs_df[selected_field], errors='coerce')
    else:
        acs_query = f'SELECT geoid, "{selected_field}" FROM census.acs2023_combined'
        acs_df = pd.read_sql(acs_query, engine)
        acs_df['geoid'] = acs_df['geoid'].astype(str).str.zfill(12)

    # Merge ACS data into block groups
    block_groups = block_groups.merge(
        acs_df, left_on='GEOID', right_on='geoid', how='left')

    # Bin the selected field for grayscale mapping
    if selected_field == "median_household_income":
        income_bins = [2499, 53240, 84175, 122700, 180134, 250001]
        block_groups['underlay_bin'] = pd.cut(
            block_groups[selected_field], bins=income_bins, labels=False, include_lowest=True)
    elif selected_field == "edu_hs_or_more":
        edu_bins = [0, 508, 832, 1199, 1711, 3965]
        block_groups['underlay_bin'] = pd.cut(
            block_groups[selected_field], bins=edu_bins, labels=False, include_lowest=True)
    elif selected_field == "households_with_subscription":
        internet_bins = [0, 288, 472, 679, 965, 2070]
        block_groups['underlay_bin'] = pd.cut(
            block_groups[selected_field], bins=internet_bins, labels=False, include_lowest=True)
    else:
        if block_groups[selected_field].notnull().sum() > 0:
            block_groups['underlay_bin'] = pd.qcut(
                block_groups[selected_field], bins, labels=False, duplicates='drop')
        else:
            block_groups['underlay_bin'] = None

    # Grayscale colors (light to dark)
    gray_colors = ["#f0f0f0", "#bdbdbd", "#969696", "#636363", "#252525"]
    block_groups['underlay_color'] = block_groups['underlay_bin'].map(
        lambda x: gray_colors[int(x)] if pd.notnull(x) else None)

    return block_groups


print("Loading school data...")
SCHOOLDATA = load_all_school_data()
print("Loading geo data...")
GEODATA = load_geodata()
print("Loading CBG underlay data...")
CBGDATA = {}
underlay_fields = ["black_population_ratio", "median_household_income",
                   "edu_hs_or_more", "households_with_subscription"]
for field in underlay_fields:
    cbg_gdf = load_cbg_underlay(field)
    cbg_gdf = cbg_gdf.set_index('GEOID')
    CBGDATA[field] = {
        'geojson': json.loads(cbg_gdf.to_json()),
        'locations': cbg_gdf.index.tolist(),
        'z_values': cbg_gdf['underlay_bin'].fillna(-1).tolist()
    }

print("Data loading complete.")
