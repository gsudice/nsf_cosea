# ---------- APPROVED COURSES ----------
APPROVED_COURSES = [
    "advanced placement, computer science a",
    "advanced placement computer science principles",
    "ib computer science, year one",
    "ib computer science, year two",
    "computer science principles",
    "programming, games, apps and society",
    "web development",
    "embedded computing",
    "game design: animation and simulation",
    "introduction to cybersecurity",
    "advanced cybersecurity",
    "coding for fintech",
    "introduction to python",
    "introduction to software technology",
    "introduction to digital technology",
    "introduction to hardware technology"
]
# Mapping for display names (preserve key casing in data but adjust frontend labels)
COURSE_DISPLAY_MAP = {
    # Keep keys as stored in APPROVED_COURSES (lowercase); map to desired display labels
    "ib computer science, year one": "IB Computer Science, Year One",
    "ib computer science, year two": "IB Computer Science, Year Two",
}
MODALITY_LABELS = {
    "Both": "In Person and Virtual",
    "In Person": "In Person Only",
    "Virtual": "Virtual Only",
    "No": "No approved CS Class"
}
MODALITY_CLASS_MAP = {
    "Both": "both",
    "In Person": "in-person",
    "Virtual": "virtual",
    "No": "no"
}

# Teacher modality labels and mappings
TEACHER_MODALITY_LABELS = {
    "Both + Extra Teachers": "In Person and Virtual + Extra Teachers",
    "Both": "In Person and Virtual",
    "In Person + Extra Teachers": "In Person + Extra Teachers",
    "In Person": "In Person Only",
    "Virtual + Extra Teachers": "Virtual + Extra Teachers",
    "Virtual": "Virtual Only",
    "No CS + Extra Teachers": "No CS + Extra Teachers",
    "No": "No approved CS Class"
}
TEACHER_MODALITY_CLASS_MAP = {
    "Both + Extra Teachers": "both",
    "Both": "both",
    "In Person + Extra Teachers": "in-person",
    "In Person": "in-person",
    "Virtual + Extra Teachers": "virtual",
    "Virtual": "virtual",
    "No CS + Extra Teachers": "no",
    "No": "no"
}

LABELS = {
    "overlay_options": [
        {"label": "Show Modalities", "value": "modalities"},
        {"label": "Show County Lines", "value": "counties"},
        {"label": "Show Highways", "value": "highways"},
    ],
    "map_options": [
        {"label": "Show Legend", "value": "show_legend"},
        {"label": "Highways", "value": "highways"},
        {"label": "County Lines", "value": "counties"},
        {"label": "City Labels", "value": "city_labels"},
    ],
    "sidebar_title": "Map Options",
    "school_dots": "School Dots",
    "school_toggles": [
        {"label": "Course Modality", "value": "modalities"},
        {"label": "Representation Index (RI)", "value": "disparity"},
    ],
    "dots_dropdown_label_modality": "Modality Type",
    "dots_dropdown_label_disparity": "RI Category",
    "dots_dropdown_options_modality": [
        {"label": "Modality", "value": "LOGIC_CLASS_2"},
        {"label": "Modality + Teachers", "value": "LOGIC_CLASS_2_TEACHERS"},
    ],
    "dots_dropdown_options_disparity": [
        {"label": "Asian", "value": "RI_Asian"},
        {"label": "Black", "value": "RI_Black"},
        {"label": "Hispanic", "value": "RI_Hispanic"},
        {"label": "White", "value": "RI_White"},
        {"label": "Female", "value": "RI_Female"},
    ],
    "legend_titles": {
        "modality": "Modality",
        "expanded_modality": "Modality",
        "teachers_modality": "Modality + Teachers",
        "RI_Black": "Black Representation Index",
        "RI_Asian": "Asian Representation Index",
        "RI_Hispanic": "Hispanic Representation Index",
        "RI_White": "White Representation Index",
        "RI_Female": "Female Representation Index",
        "default": "Representation Index"
    },
    "overlay_legend": {
        "county": "County Boundaries",
        "highway": "Interstate Highways"
    }
}

# ---------- HOVER INFO ----------
HOVER_TEMPLATES = {
    "unified": (
        "<b><u>{SCHOOL_NAME}</u></b><br>"
        "📍 District: {district}<br>"
        "📍 City: {city}<br>"
        "📍 Locale Type: {locale}<br>"
        "📍 Grades: {GRADE_RANGE}<br>"
        "<br>"
        "<b>TOTAL STUDENT DEMOGRAPHICS</b><br>"
        "{total_race_vals}<br>"
        "<br>"
        "<b>CS TEACHING STAFF</b><br>"
        "   - CS Teachers: {approved_teachers}<br>"
        "   - Extra Certified Teachers: {extra_teachers}<br>"
        "   - Student-to-CS-Teacher Ratio: {ratio_display}<br>"
        "<br>"
        "<b>CS ENROLLMENT</b><br>"
        "{cs_race_vals}<br>"
        "   - CS Total: {cs_total}<br>"
        "<br>"
        "<b>REPRESENTATION INDEX (RI)</b><br>"
        "{ri_vals}"
    )
}
# ---------- COLORS ----------
MODALITY_COLOR_MAP = {
    "Both": "#47CEF5",
    "In Person": "#F54777",
    "Virtual": "#FFB300",
    "No": "#636363"
}

# Extended color map for teacher modality (same colors, will be differentiated by shape)
TEACHER_MODALITY_COLOR_MAP = {
    "Both + Extra Teachers": "#47CEF5",
    "Both": "#47CEF5",
    "In Person + Extra Teachers": "#F54777",
    "In Person": "#F54777",
    "Virtual + Extra Teachers": "#FFB300",
    "Virtual": "#FFB300",
    "No CS + Extra Teachers": "#636363",
    "No": "#636363"
}

RI_BIN_COLORS = ['#7f2704', '#fdae6b', '#ffffff', '#9ecae1', '#08519c']

GENDER_COLOR_BINS = [
    (-0.864929, -0.296520, '#7f2704'),
    (-0.296519, -0.211112, '#d94801'),
    (-0.211111, -0.051748, '#fdae6b'),
    (-0.051747, 0.032609, '#ffffff'),
    (0.034510, 0.257576, '#9ecae1'),
    (0.257577, 0.497095, '#3182bd'),
    (0.497096, 0.652174, '#08519c')
]

# ---------- DATABASE LINK ----------
DATABASE_URL = "postgresql+psycopg2://cosea_user:CoSeaIndex@pgsql.dataconn.net:5432/cosea_db"

# ---------- SHAPEFILES ----------
GA_OSM_QUERY = "Georgia, USA"
COUNTY_SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"
ROAD_SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip"

# ---------- DEFAULTS ----------
DEFAULT_MAP_OPTIONS = ["show_legend", "highways", "counties", "city_labels"]
DEFAULT_SCHOOL_TOGGLE = "modalities"
DEFAULT_DOTS_DROPDOWN_MODALITIES = "LOGIC_CLASS_2"
DEFAULT_DOTS_DROPDOWN_DISPARITY = "RI_Asian"
DEFAULT_UNDERLAY_OPTION = "none"

UNDERLAY_OPTIONS = [
    {"label": "None", "value": "none"},
    {"label": "Black Population Ratio",
     "value": "black_population_ratio"},
    {"label": "Median Household Income",
     "value": "median_household_income"},
    {"label": "High School or More Education",
     "value": "edu_hs_or_more"},
    {"label": "Internet Subscription",
     "value": "households_with_subscription"}
]

UNDERLAY_COLORS = ['#f7f7f7', '#d9d9d9', '#bdbdbd', '#969696', '#636363']

UNDERLAY_COLOR_SCALE = [
    [0, UNDERLAY_COLORS[0]],
    [0.25, UNDERLAY_COLORS[1]],
    [0.5, UNDERLAY_COLORS[2]],
    [0.75, UNDERLAY_COLORS[3]],
    [1, UNDERLAY_COLORS[4]]
]

# ---------- CITY LABEL CONFIGURATION ----------
# Offsets are in meters (EPSG:3857) from the city point to label anchor used by leader lines
CITY_LABEL_OFFSETS_M = {
    "Atlanta": (-120000, 5000),
    "Savannah": (6000, 40000),
    "Augusta": (30000, -8000),
    "Macon": (-170000, -80000),
    "Columbus": (-30000, 10000),
}

# Text positioning details: textposition (Plotly keyword) and an additional small
# text-only nudge (in meters) to shift only the text separately from the leader line anchor
CITY_LABEL_TEXT_SETTINGS = {
    "Atlanta": {"textposition": "middle left", "nudge": (-8000, 0), "text_nudge": (0, 0)},
    "Macon": {"textposition": "middle left", "nudge": (-8000, 0), "text_nudge": (0, 0)},
    "Augusta": {"textposition": "bottom right", "nudge": (30000, -8000), "text_nudge": (2000, 6000)},
    "Savannah": {"textposition": "top right", "nudge": (6000, 40000), "text_nudge": (-14000, 4000)},
    "Columbus": {"textposition": "middle left", "nudge": (-30000, 10000), "text_nudge": (-2000, 0)},
}

# City label text size (points)
CITY_LABEL_TEXT_SIZE = 13
