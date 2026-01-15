from data_dashboard.settings import *
import os
import tempfile
import requests
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon, Point, LineString, MultiPoint, MultiLineString, GeometryCollection
from shapely.ops import unary_union
from sqlalchemy import create_engine
import pandas as pd
import json
import re


def suppress_value(val):
    if pd.isnull(val) or val is None:
        return 0
    try:
        num_val = int(val)
        if num_val == 0:
            return 0
        elif num_val < 5:
            return "suppressed"
        else:
            return num_val
    except Exception:
        return 0


def has_suppression(values):
    return any(v == "suppressed" for v in values)


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
    total_students = row.get("Total Student Count", 0)
    approved_teachers = row.get("approved_teachers", 0)
    extra_teachers = row.get("extra_teachers", 0)
    # Compute ratio using approved teachers plus extra certified teachers
    total_teachers_for_ratio = 0
    try:
        total_teachers_for_ratio = int(approved_teachers) + int(extra_teachers)
    except Exception:
        total_teachers_for_ratio = approved_teachers or 0
    ratio_display = row.get("ratio_display", ratio_fmt(
        total_students / total_teachers_for_ratio if total_teachers_for_ratio else 0))

    # If not in row, fetch from data
    if "approved_teachers" not in row:
        school_id = str(row["UNIQUESCHOOLID"])
        approved_teachers = SCHOOLDATA["approved_teachers_count"].get(
            school_id, 0)
        extra_teachers = SCHOOLDATA["extra_teachers_count"].get(school_id, 0)
        # Use approved + extra teachers for ratio
        total_teachers_for_ratio = 0
        try:
            total_teachers_for_ratio = int(
                approved_teachers) + int(extra_teachers)
        except Exception:
            total_teachers_for_ratio = approved_teachers or 0
        ratio_display = ratio_fmt(
            total_students / total_teachers_for_ratio if total_teachers_for_ratio else 0)

    # Race and RI
    total_race_vals = ""
    cs_race_vals = ""
    ri_vals = ""
    cs_total = 0

    if disparity_col and ri_cols:
        # It's disparity view, data is in row
        total_race_map = {
            "RI_Asian": ("Race: Asian", "Total Asian"),
            "RI_Black": ("Race: Black", "Total Black"),
            "RI_Hispanic": ("Ethnicity: Hispanic", "Total Hispanic"),
            "RI_White": ("Race: White", "Total White"),
        }

        # Always show all demographics regardless of selected RI category
        # Collect total demographic values
        total_race_vals_list = []
        total_demographics_displays = []
        for ri_key, (total_col, total_label) in total_race_map.items():
            val = row.get(total_col, None)
            if pd.notnull(val):
                val_display = suppress_value(val)
                total_demographics_displays.append(val_display)
                # Underline if this matches the selected disparity column
                if ri_key == disparity_col:
                    total_race_vals_list.append(f"   - <u>{total_label}: {val_display}</u>")
                else:
                    total_race_vals_list.append(f"   - {total_label}: {val_display}")
        
        # Add female and male
        female = row.get("Female", None)
        if pd.notnull(female):
            female_display = suppress_value(female)
            total_demographics_displays.append(female_display)
            # Underline if Female is selected
            if disparity_col == "RI_Female":
                total_race_vals_list.append(f"   - <u>Total Female: {female_display}</u>")
            else:
                total_race_vals_list.append(f"   - Total Female: {female_display}")
        male = row.get("Male", None)
        if pd.notnull(male):
            male_display = suppress_value(male)
            total_demographics_displays.append(male_display)
            # Note: Male is not a disparity option, so no underlining needed
            total_race_vals_list.append(f"   - Total Male: {male_display}")
        
        # If any demographic is suppressed, suppress Total Students
        total_students = row.get("Total Student Count", None)
        if pd.notnull(total_students):
            if has_suppression(total_demographics_displays):
                total_student_display = "suppressed"
            else:
                total_student_display = suppress_value(total_students)
            total_race_vals_list.append(f"   - Total Students: {total_student_display}")
        total_race_vals = "<br>".join(total_race_vals_list)

        # Collect CS demographic values - always show all
        cs_race_cols = ["CS_Asian", "CS_Black", "CS_Hispanic", "CS_White"]
        cs_race_labels = {
            "CS_Asian": "CS Asian",
            "CS_Black": "CS Black",
            "CS_Hispanic": "CS Hispanic",
            "CS_White": "CS White"
        }
        # Map CS columns to their corresponding RI columns for underlining
        cs_to_ri_map = {
            "CS_Asian": "RI_Asian",
            "CS_Black": "RI_Black",
            "CS_Hispanic": "RI_Hispanic",
            "CS_White": "RI_White"
        }
        cs_race_vals_list = []
        cs_demographics_displays = []
        for cs_col in cs_race_cols:
            val = row.get(cs_col, None)
            if pd.notnull(val):
                val_display = suppress_value(val)
                cs_demographics_displays.append(val_display)
                # Underline if this CS category matches the selected disparity column
                if cs_to_ri_map.get(cs_col) == disparity_col:
                    cs_race_vals_list.append(
                        f"   - <u>{cs_race_labels[cs_col]}: {val_display}</u>")
                else:
                    cs_race_vals_list.append(
                        f"   - {cs_race_labels[cs_col]}: {val_display}")
        
        # Add CS Female and CS Male
        cs_female = row.get('CS_Female', None)
        if pd.notnull(cs_female):
            cs_female_display = suppress_value(cs_female)
            cs_demographics_displays.append(cs_female_display)
            # Underline if Female is selected
            if disparity_col == "RI_Female":
                cs_race_vals_list.append(f"   - <u>CS Female: {cs_female_display}</u>")
            else:
                cs_race_vals_list.append(f"   - CS Female: {cs_female_display}")
        cs_male = row.get('CS_Male', None)
        if pd.notnull(cs_male):
            cs_male_display = suppress_value(cs_male)
            cs_demographics_displays.append(cs_male_display)
            # Note: Male is not a disparity option, so no underlining needed
            cs_race_vals_list.append(f"   - CS Male: {cs_male_display}")
        
        cs_race_vals = "<br>".join(cs_race_vals_list)

        # If any CS demographic is suppressed, suppress CS Total
        if has_suppression(cs_demographics_displays):
            cs_total = "suppressed"
        else:
            cs_total = suppress_value(row.get('CS_Enrollment', 0))

        # Show all RI values, underline the selected one
        ri_vals_list = []
        for col in ri_cols:
            if col in row:
                val = row[col]
                if pd.notnull(val):
                    bold = col == disparity_col
                    txt = f"RI {col.replace('RI_', '')}: {val:.4f}"
                    if bold:
                        ri_vals_list.append(f"   - <u>{txt}</u>")
                    else:
                        ri_vals_list.append(f"   - {txt}")
        ri_vals = "<br>".join(ri_vals_list)
    else:
        # Modality view, use row data directly
        total_race_vals_list = []
        total_demographics_displays = []
        race_cols = ["Race: Asian", "Race: Black",
                     "Ethnicity: Hispanic", "Race: White"]
        race_labels = ["Total Asian", "Total Black",
                       "Total Hispanic", "Total White"]
        for col, label in zip(race_cols, race_labels):
            val = row.get(col, None)
            if pd.notnull(val):
                val_display = suppress_value(val)
                total_demographics_displays.append(val_display)
                total_race_vals_list.append(f"   - {label}: {val_display}")
        
        # Add female and male to demographics list
        female = row.get("Female", None)
        if pd.notnull(female):
            female_display = suppress_value(female)
            total_demographics_displays.append(female_display)
            total_race_vals_list.append(f"   - Total Female: {female_display}")
        male = row.get("Male", None)
        if pd.notnull(male):
            male_display = suppress_value(male)
            total_demographics_displays.append(male_display)
            total_race_vals_list.append(f"   - Total Male: {male_display}")
        
        # If any demographic is suppressed, suppress Total Students
        total_students = row.get("Total Student Count", None)
        if pd.notnull(total_students):
            if has_suppression(total_demographics_displays):
                total_students_display = "suppressed"
            else:
                total_students_display = suppress_value(total_students)
            total_race_vals_list.append(f"   - Total Students: {total_students_display}")
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
            cs_demographics_displays = []
            for cs_col in cs_race_cols:
                val = drow.get(cs_col, None)
                if pd.notnull(val):
                    val_display = suppress_value(val)
                    cs_demographics_displays.append(val_display)
                    cs_race_vals_list.append(
                        f"   - {cs_race_labels[cs_col]}: {val_display}")
            
            # Also check CS Female and CS Male
            cs_female = drow.get('CS_Female', None)
            if pd.notnull(cs_female):
                cs_demographics_displays.append(suppress_value(cs_female))
            cs_male = drow.get('CS_Male', None)
            if pd.notnull(cs_male):
                cs_demographics_displays.append(suppress_value(cs_male))
            
            # If any CS demographic is suppressed, suppress CS Total
            if has_suppression(cs_demographics_displays):
                cs_total = "suppressed"
            else:
                cs_total = suppress_value(drow.get('CS_Enrollment', 0))
            
            cs_race_vals = "<br>".join(cs_race_vals_list)

            ri_vals_list = []
            for col in ["RI_Asian", "RI_Black", "RI_Hispanic", "RI_White", "RI_Female"]:
                val = drow.get(col, None)
                if pd.notnull(val):
                    txt = f"RI {col.replace('RI_', '')}: {val:.4f}"
                    ri_vals_list.append(f"   - {txt}")
            ri_vals = "<br>".join(ri_vals_list)
        else:
            cs_race_vals = ""
            ri_vals = ""

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
        approved_teachers=approved_teachers_str,
        extra_teachers=extra_teachers_str,
        ratio_display=ratio_display,
        total_race_vals=total_race_vals,
        cs_total=cs_total,
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

    # Key Georgia cities for map labels (lat, lon)
    city_labels = {
        "Atlanta": (33.7490, -84.3880),
        "Savannah": (32.0809, -81.0912),
        "Augusta": (33.4735, -82.0105),
        "Macon": (32.8407, -83.6324),
        "Columbus": (32.492222, -84.940277)
    }
    # Use module-level pandas 'pd' imported at top of file
    city_label_df = pd.DataFrame([
        {"city": name, "lat": coords[0], "lon": coords[1]} for name, coords in city_labels.items()
    ])

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
        "extra_teachers_count": extra_teachers_count,
        "city_labels": city_label_df
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
    # All interstates (may extend beyond GA)
    interstates_all = roads[roads["RTTYP"] == "I"].to_crs(epsg=4326)
    # Interstates clipped to GA boundary for drawing
    interstates = gpd.clip(interstates_all, ga_boundary)
    highway_lines = []
    # Temporary collection to group segments by highway name
    highway_segments = {}
    # Build union geometries per highway name for full (unclipped) interstates to detect crossings
    highway_unions = {}
    for _, row in interstates_all.iterrows():
        name = row.get("FULLNAME") or row.get(
            "SIGN1") or row.get("REF") or "Interstate"
        if not name:
            name = "Interstate"
        if name not in highway_unions:
            highway_unions[name] = []
        highway_unions[name].append(row.geometry)
    for name in list(highway_unions.keys()):
        try:
            highway_unions[name] = unary_union(highway_unions[name])
        except Exception:
            # Fallback to simple sum of geometries
            highway_unions[name] = highway_unions[name][0]
    for _, row in interstates.iterrows():
        geom = row.geometry
        # Some geometries may be MultiLineString; handle generically
        try:
            xs, ys = geom.xy
            segments = [(list(xs), list(ys))]
        except Exception:
            # For MultiLineString
            segments = []
            for part in geom.geoms:
                xs, ys = part.xy
                segments.append((list(xs), list(ys)))

        for seg_x, seg_y in segments:
            highway_lines.append((seg_x, seg_y))
            name = row.get("FULLNAME") or row.get(
                "SIGN1") or row.get("REF") or "Interstate"
            if not name:
                name = "Interstate"
            # Group by name
            if name not in highway_segments:
                highway_segments[name] = []
            # store length of segment for choosing longest later
            seg_length = 0
            if len(seg_x) > 1:
                # approximate length by sum of euclidean distances in degrees (fine for grouping)
                seg_length = sum(
                    ((seg_x[i+1]-seg_x[i])**2 + (seg_y[i+1]-seg_y[i])**2)**0.5 for i in range(len(seg_x)-1))
            highway_segments[name].append(
                {"x": seg_x, "y": seg_y, "length": seg_length})

    # Build two labels per interstate, placed at the true start and end of the clipped geometry
    highway_labels = []
    for name, segs in highway_segments.items():
        # Concatenate all segments for this interstate
        all_x = []
        all_y = []
        for seg in segs:
            all_x.extend(seg["x"])
            all_y.extend(seg["y"])
        n = len(all_x)
        if n > 1:
            # Determine highway number digits from name (extract digits, e.g., 'I-75' -> '75')
            digits_match = re.search(r"(\d{1,3})", name)
            num_digits = len(digits_match.group(1)) if digits_match else 0
            if num_digits == 3:
                # For 3-digit interstates, place a single label at the midpoint
                mid_idx = n // 2
                label_lon = all_x[mid_idx]
                label_lat = all_y[mid_idx]
                highway_labels.append(
                    {"name": name, "lat": label_lat, "lon": label_lon})
            else:
                # Default: for 1- or 2-digit interstates, place two labels at start and end
                label_lon1 = all_x[0]
                label_lat1 = all_y[0]
                label_lon2 = all_x[-1]
                label_lat2 = all_y[-1]
                highway_labels.append(
                    {"name": name, "lat": label_lat1, "lon": label_lon1})
                highway_labels.append(
                    {"name": name, "lat": label_lat2, "lon": label_lon2})
    # Add border labels for highways that extend outside the Georgia boundary
    ga_polygon = ga_boundary.unary_union
    ga_boundary_line = ga_polygon.boundary
    # Function to extract points from intersection geometry

    def _extract_points_from_intersection(g):
        pts = []
        if g.is_empty:
            return pts
        if isinstance(g, Point):
            pts.append((g.x, g.y))
        elif isinstance(g, MultiPoint):
            for p in g.geoms:
                pts.append((p.x, p.y))
        elif isinstance(g, (LineString, MultiLineString)):
            cent = g.centroid
            pts.append((cent.x, cent.y))
        elif isinstance(g, GeometryCollection):
            for geom in g.geoms:
                if isinstance(geom, Point):
                    pts.append((geom.x, geom.y))
                elif isinstance(geom, (LineString, MultiLineString)):
                    cent = geom.centroid
                    pts.append((cent.x, cent.y))
        return pts

    for name, union_geom in highway_unions.items():
        try:
            if union_geom.is_empty:
                continue
        except Exception:
            continue
        # If the highway is not entirely within GA, add label(s) at the border crossing(s)
        try:
            if not union_geom.within(ga_polygon):
                inters = union_geom.intersection(ga_boundary_line)
                points = _extract_points_from_intersection(inters)
                for lon, lat in points:
                    # avoid duplicates near existing labels for this highway
                    too_close = False
                    for lbl in highway_labels:
                        if lbl.get("name") == name:
                            if abs(lbl.get("lon") - lon) < 0.0001 and abs(lbl.get("lat") - lat) < 0.0001:
                                too_close = True
                                break
                    if not too_close:
                        highway_labels.append(
                            {"name": name, "lat": lat, "lon": lon})
        except Exception:
            # if any geometry operation fails, skip
            continue
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
        "highway_labels": highway_labels,
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
