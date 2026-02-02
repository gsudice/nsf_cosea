# keep this at the top to silence warning
import data_dashboard.data_loader as data_loader
from data_dashboard.data_loader import suppress_value
from data_dashboard.settings import *
from data_dashboard.settings import APPROVED_COURSES, COURSE_DISPLAY_MAP, CITY_LABEL_OFFSETS_M, CITY_LABEL_TEXT_SETTINGS, CITY_LABEL_TEXT_SIZE
from sqlalchemy import create_engine
import pandas as pd
import plotly.graph_objs as go
from dash import register_page, html, dcc, callback, Input, Output, State, callback_context
import math
from pyproj import Transformer
import warnings

# this is how we make a page recognized by Dash, comment out to hide
register_page(
    __name__,
    path='/data-dashboard',
    name='Data Dashboard',
    order=1
)

engine = create_engine(DATABASE_URL)

overlay_options = LABELS["overlay_options"]
highway_label_option = {"label": "Highway Labels", "value": "highway_labels"}
overlay_options = LABELS["overlay_options"] + [highway_label_option]

# Build map options list with highway labels next to highways
map_options_list = []
for opt in LABELS["map_options"]:
    map_options_list.append(opt)
    if opt.get("value") == "highways":
        map_options_list.append(highway_label_option)

school_options = [{"label": f"School: {row['SCHOOL_NAME']}", "value": f"school:{row['UNIQUESCHOOLID']}"}
                  for _, row in data_loader.SCHOOLDATA["approved_all"].iterrows()]

school_locales = data_loader.SCHOOLDATA["approved_all"]["Locale"].dropna(
).unique()
locale_options = [{"label": locale, "value": locale}
                  for locale in sorted(school_locales)]

district_options = [{"label": f"District: {district}", "value": f"district:{district}"}
                    for district in sorted(data_loader.SCHOOLDATA["approved_all"]["SYSTEM_NAME"].dropna().unique())]

city_options = [{"label": f"City: {city}", "value": f"city:{city}"}
                for city in sorted(data_loader.SCHOOLDATA["approved_all"]["School City"].dropna().unique())]

all_search_options = school_options + district_options + city_options


def get_course_display(course_key: str) -> str:
    """Return the frontend display label for a course key.

    Looks up COURSE_DISPLAY_MAP (keys are the lowercase course strings
    as they appear in APPROVED_COURSES). Falls back to title-casing.
    """
    return COURSE_DISPLAY_MAP.get(course_key, course_key.title())


def filter_by_courses(df, courses_filter, courses_filter_mode):
    """Apply course filtering to a dataframe based on selected courses and mode.

    Args:
        df: DataFrame with UNIQUESCHOOLID column
        courses_filter: List of course names to filter by
        courses_filter_mode: "all", "any", or "none"

    Returns:
        Filtered DataFrame
    """
    if not courses_filter:
        return df

    if courses_filter_mode == "all":
        # All selected courses must be offered
        return df[df['UNIQUESCHOOLID'].apply(lambda x: all(
            course.lower() in data_loader.SCHOOLDATA["courses"].get(str(x), {}) and (
                data_loader.SCHOOLDATA["courses"][str(x)][course.lower()]['virtual'] +
                data_loader.SCHOOLDATA["courses"][str(
                    x)][course.lower()]['inperson'] > 0
            ) for course in courses_filter
        ))]
    elif courses_filter_mode == "any":
        # At least one selected course must be offered
        return df[df['UNIQUESCHOOLID'].apply(lambda x: any(
            course.lower() in data_loader.SCHOOLDATA["courses"].get(str(x), {}) and (
                data_loader.SCHOOLDATA["courses"][str(x)][course.lower()]['virtual'] +
                data_loader.SCHOOLDATA["courses"][str(
                    x)][course.lower()]['inperson'] > 0
            ) for course in courses_filter
        ))]
    elif courses_filter_mode == "none":
        # None of the selected courses should be offered
        return df[df['UNIQUESCHOOLID'].apply(lambda x: not any(
            course.lower() in data_loader.SCHOOLDATA["courses"].get(str(x), {}) and (
                data_loader.SCHOOLDATA["courses"][str(x)][course.lower()]['virtual'] +
                data_loader.SCHOOLDATA["courses"][str(
                    x)][course.lower()]['inperson'] > 0
            ) for course in courses_filter
        ))]
    else:
        return df


def calculate_total_offered(df):
    """Add a total_offered column counting approved courses offered at each school.

    Args:
        df: DataFrame with UNIQUESCHOOLID column

    Returns:
        DataFrame with total_offered column added
    """
    df["total_offered"] = df['UNIQUESCHOOLID'].apply(lambda x: sum(
        1 for course in APPROVED_COURSES
        if course.lower() in data_loader.SCHOOLDATA["courses"].get(str(x), {}) and (
            data_loader.SCHOOLDATA["courses"][str(x)][course.lower()]['virtual'] +
            data_loader.SCHOOLDATA["courses"][str(
                x)][course.lower()]['inperson'] > 0
        )
    ))
    return df


def apply_location_filter_and_get_center(df, selected_school, default_zoom=6.5, school_zoom=11, area_zoom=10):
    """Filter dataframe by selected school/district/city and calculate map center/zoom.

    Args:
        df: DataFrame with location columns (UNIQUESCHOOLID, SYSTEM_NAME, School City, lat, lon)
        selected_school: Selection string in format "school:ID", "district:NAME", or "city:NAME"
        default_zoom: Zoom level when no selection (default 6.5)
        school_zoom: Zoom level when school selected (default 11)
        area_zoom: Zoom level when district/city selected (default 10)

    Returns:
        Tuple of (filtered_df, center_dict, zoom_level)
    """
    default_center = {"lat": 32.9, "lon": -83.5}

    if not selected_school:
        return df, default_center, default_zoom

    if selected_school.startswith("school:"):
        school_id = selected_school.split(":", 1)[1]
        school_row = data_loader.SCHOOLDATA["approved_all"][
            data_loader.SCHOOLDATA["approved_all"]["UNIQUESCHOOLID"] == school_id]
        if not school_row.empty:
            center = {"lat": school_row["lat"].iloc[0],
                      "lon": school_row["lon"].iloc[0]}
            return df, center, school_zoom
        else:
            return df, default_center, default_zoom

    elif selected_school.startswith("district:"):
        district_name = selected_school.split(":", 1)[1]
        filtered_df = df[df['SYSTEM_NAME'] == district_name]
        if filtered_df.empty:
            return filtered_df, default_center, default_zoom
        else:
            center = {"lat": filtered_df["lat"].mean(
            ), "lon": filtered_df["lon"].mean()}
            return filtered_df, center, area_zoom

    elif selected_school.startswith("city:"):
        city_name = selected_school.split(":", 1)[1]
        filtered_df = df[df['School City'] == city_name]
        if filtered_df.empty:
            return filtered_df, default_center, default_zoom
        else:
            center = {"lat": filtered_df["lat"].mean(
            ), "lon": filtered_df["lon"].mean()}
            return filtered_df, center, area_zoom

    return df, default_center, default_zoom


courses_options = [{"label": get_course_display(course), "value": course}
                   for course in APPROVED_COURSES]

modality_options = [{"label": "Virtual", "value": "Virtual"}, {"label": "In Person", "value": "In Person"}, {
    "label": "Both", "value": "Both"}, {"label": "None", "value": "No"}]

layout = html.Div([
    html.Div([
        dcc.Loading(
            id="map-loading",
            custom_spinner=html.Div([
                html.Div(className="loading-spinner"),
                html.Div(id="loading-message")
            ]),
            children=[dcc.Graph(
                id="main-map",
                className="main-map-graph",
                config={
                    "displayModeBar": True,
                    "scrollZoom": True,
                    "doubleClick": "reset",
                    # Only show the reset view button, remove all others including pan and Plotly logo
                    "modeBarButtonsToRemove": [
                        "zoom2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
                        "select2d", "lasso2d", "zoomInMapbox", "zoomOutMapbox", "toImage",
                        "sendDataToCloud", "hoverClosestCartesian", "hoverCompareCartesian",
                        "hoverClosestMapbox", "hoverClosestGeo", "hoverClosestGl2d",
                        "hoverClosestPie", "toggleHover", "resetViewMapbox", "pan2d", "pan"
                    ],
                    "modeBarButtonsToAdd": ["resetViewMapbox"],
                    "displaylogo": False
                }
            )]
        ),
        html.Div(
            id="custom-legend-container",
            className="custom-legend-container"
        )
    ], className="main-map-area", id="main-map-area"),
    html.Button("▶", id="sidebar-toggle",
                className="sidebar-toggle-btn", title="Collapse Sidebar"),
    html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.Button("?", id="faq-button",
                                className="faq-button", title="Help & FAQ"),
                ], className="sidebar-header-right"),
                dcc.Dropdown(
                    id="school-search",
                    options=all_search_options,
                    placeholder="Search for schools, districts, or cities...",
                    searchable=True,
                    clearable=True,
                    className="school-search"
                ),
            ], className="sidebar-section"),
            html.Div([
                html.Strong("Map Options", style={
                    'font-size': '1.17em', 'font-weight': '700', 'color': '#2a3b4c'})
            ], className="sidebar-header"),
            dcc.Checklist(
                id="map-options-toggle",
                options=map_options_list,
                value=DEFAULT_MAP_OPTIONS + ["highway_labels"],
                className="sidebar-legend-toggle",
                labelStyle={'display': 'inline-block',
                            'margin-right': '6px', 'font-size': '0.9em'},
                style={'display': 'flex', 'flex-direction': 'row',
                       'gap': '6px', 'align-items': 'center'}
            ),
            html.Div([
                html.Strong(LABELS["school_dots"]),
                html.Div([
                    html.Div([
                        dcc.RadioItems(
                            id="school-toggles",
                            options=[
                                {
                                    "label": html.Span([
                                        opt["label"],
                                        html.Span(
                                            "i",
                                            title=("Indicates how CS courses are offered at the school.") if opt.get("value") == "modalities" else (
                                                "Shows how well different groups are represented in CS courses compared to the school population."),
                                            className="sidebar-info-icon",
                                            style={"margin-left": "6px"}
                                        )
                                    ]),
                                    "value": opt["value"]
                                }
                                for opt in LABELS["school_toggles"]
                            ],
                            value=DEFAULT_SCHOOL_TOGGLE,
                            className="sidebar-school-toggles",
                            style={'display': 'flex',
                                   'flex-direction': 'row', 'gap': '10px'}
                        ),
                    ], style={'display': 'flex', 'align-items': 'center'}),
                    html.Div([
                        html.Label(id="dots-dropdown-label",
                                   className="sidebar-dots-dropdown-label"),
                        dcc.Dropdown(
                            id="dots-dropdown",
                            options=[],
                            value=None,
                            clearable=False,
                            className="sidebar-dots-dropdown"
                        ),
                    ], style={'margin-left': '20px', 'flex': '1'}),
                ], style={'display': 'flex', 'align-items': 'center'}),
            ], className="sidebar-section", style={'margin-bottom': '-6px'}),
            html.Div([
                html.Strong("Underlays"),
                dcc.Dropdown(
                    id="underlay-dropdown",
                    options=UNDERLAY_OPTIONS,
                    value=DEFAULT_UNDERLAY_OPTION,
                    clearable=False,
                    className="sidebar-underlay-dropdown"
                ),
            ], className="sidebar-section", style={'margin-bottom': '12px'}),
            html.Details([
                html.Summary([
                    html.Div([
                        html.Span(
                            "", style={'font-size': '12px', 'margin-right': '5px'}),
                        html.Strong("Filters", style={
                            'font-size': '1.17em', 'font-weight': '700', 'color': '#2a3b4c'})
                    ], style={'display': 'flex', 'align-items': 'center'}),
                    html.Button("Reset Filters", id="reset-filters",
                                className="reset-button")
                ], className="sidebar-header"),
                html.Div([
                    html.Div([
                        html.Strong("Locale Type"),
                        dcc.Checklist(
                            id="locale-filter",
                            options=locale_options,
                            value=[],
                            className="sidebar-locale-checklist"
                        ),
                    ], style={'flex': '1'}),
                    html.Div([
                        html.Strong([
                            "Modality",
                            html.Span(
                                "i",
                                title="Indicates how CS courses are offered at the school.",
                                className="sidebar-info-icon"
                            )
                        ]),
                        dcc.Checklist(
                            id="modality-filter",
                            options=modality_options,
                            value=[],
                            className="sidebar-modality-checklist"
                        ),
                    ], style={'flex': '1'}),
                    html.Div([
                        html.Strong([
                            "Extra Teachers",
                            html.Span(
                                "i",
                                title="These are teachers who do not teach a CS course on the Courses Offered list below, but are certified to teach CS.",
                                className="sidebar-info-icon"
                            )
                        ]),
                        dcc.Checklist(
                            id="extra-teachers-filter",
                            options=[
                                {"label": "Has Extra Teachers", "value": "extra"}],
                            value=[],
                            className="sidebar-extra-teachers-checklist"
                        ),
                    ], style={'flex': '1'}),
                ], style={'display': 'flex', 'gap': '20px', 'margin-bottom': '24px'}),
                html.Div([
                    html.Div([
                        html.Strong("Courses Offered"),
                        dcc.RadioItems(
                            id="courses-filter-mode",
                            options=[
                                {"label": "All", "value": "all"},
                                {"label": "Any", "value": "any"},
                                {"label": "None", "value": "none"},
                            ],
                            value="all",
                            inline=True,
                            className="courses-filter-mode-radio"
                        ),
                        html.Span(
                            "i",
                            title="Select courses and choose a filter mode: 'All' requires schools to offer ALL selected courses, 'Any' requires at least one selected course, and 'None' excludes schools offering any selected courses.",
                            className="sidebar-info-icon"
                        )
                    ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "8px"}),
                    dcc.Checklist(
                        id="courses-filter",
                        options=courses_options,
                        value=[],
                        className="sidebar-courses-checklist"
                    ),
                ], className="sidebar-section"),
                html.Div([
                    html.Strong([
                        "Student-to-CS-Teacher Ratio",
                        html.Span(
                            "i",
                            title="Number of total students per CS teacher. Calculated as Total Student Count divided by the sum of approved and extra CS teachers at the school.",
                            className="sidebar-info-icon"
                        )
                    ]),
                    dcc.RangeSlider(
                        id="ratio-threshold",
                        min=0,
                        max=2500,
                        value=[0, 2500],
                        step=1,
                        marks={0: '0', 500: '500', 1000: '1000',
                               1500: '1500', 2000: '2000', 2500: '2500'},
                        tooltip={"placement": "bottom",
                                 "always_visible": True},
                        className="sidebar-ratio-slider"
                    ),
                ], className="sidebar-section"),
                html.Div([
                    html.Strong([
                        "RI Thresholds",
                        html.Span(
                            "i",
                            title="Filter schools by how well different groups are represented in CS courses compared to their overall school population. Values between -0.05 and 0.05 indicate parity; negative or positive values indicate under- or over-representation.",
                            className="sidebar-info-icon"
                        )
                    ]),
                    dcc.RangeSlider(
                        id="ri-threshold",
                        min=-1.0,
                        max=1.0,
                        step=0.01,
                        value=[-1.0, 1.0],
                        marks={-1: '-1', -0.05: '-0.05', 0.05: '0.05', 1: '1'},
                        tooltip={"placement": "bottom",
                                 "always_visible": True},
                        className="sidebar-ri-slider"
                    ),
                ], id="ri-threshold-container", className="sidebar-section"),
                html.Div([
                    html.Strong([
                        "Course Total Offered",
                        html.Span(
                            "i",
                            title="Number of distinct approved CS courses that are offered at the school. A course is counted if it is offered virtually or in-person.",
                            className="sidebar-info-icon",
                            style={'margin-left': '6px'}
                        )
                    ]),
                    dcc.RangeSlider(
                        id="course-total-offered",
                        min=0,
                        max=16,
                        value=[0, 16],
                        step=1,
                        marks={0: '0', 4: '4', 8: '8', 12: '12', 16: '16'},
                        tooltip={"placement": "bottom",
                                 "always_visible": True},
                        className="sidebar-course-slider"
                    ),
                ], className="sidebar-section"),
            ], open=True),
            html.Div([
                html.Div(id="course-list", className="course-list-box")
            ], className="sidebar-section course-list-section"),
        ], id="sidebar-content", className="sidebar-content"),
    ], id="sidebar", className="sidebar"),

    # Course Info Legend (visible when sidebar is collapsed)
    html.Div([
        html.Div([
            html.Button("×", id="legend-minimize",
                        className="legend-minimize-btn", title="Minimize Legend"),
            html.Div(id="course-legend-list",
                     className="course-legend-content")
        ], id="course-legend-content-wrapper", className="course-legend-expanded"),
        html.Button([
            html.Img(src="/assets/images/laptop-svgrepo-com.svg",
                     className="legend-expand-icon")
        ], id="legend-expand", className="legend-expand-btn", title="Show Course Info", style={"display": "none"})
    ], id="course-info-legend", className="course-info-legend", style={"display": "none"}),

    # FAQ Modal
    html.Div([
        html.Div([
            html.Div([
                html.H2("Resources & Information"),
                html.Button("×", id="close-faq",
                            className="close-modal-button"),
            ], className="modal-header"),

            # Tab Navigation
            html.Div([
                html.Button("FAQ", id="tab-faq",
                            className="tab-button active-tab"),
                html.Button("Data Request", id="tab-data-request",
                            className="tab-button"),
            ], className="tab-navigation"),

            # FAQ Tab Content
            html.Div([
                html.Div([
                    html.P([
                        html.Strong("Important Notice: "),
                        "CS enrollment numbers shown are estimates. Students may be enrolled in multiple CS courses, and we currently have no way to eliminate duplicates across courses. Therefore, CS enrollment counts may include the same student more than once."
                    ], className="faq-notice")
                ]),
                html.Div([
                    html.H3("What does 'suppressed' mean?"),
                    html.P("When you see 'suppressed' instead of a number, it means the value is between 1 and 4. We suppress these small numbers to protect student privacy and prevent identification of individual students."),
                ], className="faq-item"),

                html.Div([
                    html.H3("Where does the data come from?"),
                    html.Ul([
                        html.Li([
                            html.Strong(
                                "Georgia Department of Education (GaDOE): "),
                            "School-level enrollment and CS course demographics. ",
                            html.A("Data Requests", href="https://georgiainsights.gadoe.org/contact-request-data/",
                                   target="_blank", rel="noopener noreferrer")
                        ]),
                        html.Li([
                            html.Strong(
                                "National Center for Education Statistics (NCES): "),
                            "District characteristics and locale classifications. ",
                            html.A("DataLab", href="https://nces.ed.gov/datalab/",
                                   target="_blank", rel="noopener noreferrer")
                        ]),
                        html.Li([
                            html.Strong("U.S. Census Bureau: "),
                            "Demographic, income, and educational data from the ",
                            html.A("American Community Survey", href="https://www.census.gov/programs-surveys/acs.html",
                                   target="_blank", rel="noopener noreferrer"),
                            " and geographic boundaries from ",
                            html.A("TIGER/Line shapefiles", href="https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
                                   target="_blank", rel="noopener noreferrer")
                        ])
                    ]),
                ], className="faq-item"),

                html.Div([
                    html.H3("What are Course Modalities?"),
                    html.P("Course modality indicates how CS courses are offered at the school: In Person Only, Virtual Only, Both In Person and Virtual, or No approved CS classes."),
                ], className="faq-item"),

                html.Div([
                    html.H3("What is the Representation Index (RI)?"),
                    html.P("The RI shows how well different groups are represented in CS courses compared to their overall school population. Values between -0.05 and 0.05 indicate parity (balanced representation). Negative values mean under-representation in CS, while positive values mean over-representation."),
                ], className="faq-item"),

                html.Div([
                    html.H3("What are Extra Certified Teachers?"),
                    html.P("These are teachers who are certified to teach CS but do not currently teach a CS course listed in the Courses Offered section. They represent potential CS teaching capacity at the school."),
                ], className="faq-item"),

                html.Div([
                    html.H3("How is the Student-to-CS-Teacher Ratio calculated?"),
                    html.P("This ratio is calculated as Total Student Count divided by the sum of approved CS teachers and extra certified teachers at the school. It helps indicate how many students each CS teacher potentially serves."),
                ], className="faq-item"),

                html.Div([
                    html.H3("How does the Courses Offered filter work?"),
                    html.P("The courses listed are the approved CS courses at each school, based on Georgia State Bill 108. Select one or more courses and choose a filter mode:"),
                    html.Ul([
                        html.Li([html.Strong(
                            "All"), " (default): Shows schools that offer ALL of the selected courses"]),
                        html.Li([html.Strong(
                            "Any"), ": Shows schools that offer at least ONE of the selected courses"]),
                        html.Li([html.Strong(
                            "None"), ": Shows schools that do NOT offer any of the selected courses"]),
                    ]),
                    html.P(
                        "A course is counted as offered if it is available either virtually or in-person (or both)."),
                ], className="faq-item"),

                html.Div([
                    html.H3("What is Course Total Offered?"),
                    html.P("This is the number of distinct approved CS courses offered at a school. A course is counted if it is offered either virtually or in-person (or both)."),
                ], className="faq-item"),

                html.P([
                    "Questions? Contact: ",
                    html.A("placeholder@placeholder.com",
                           href="mailto:placeholder@placeholder.com")
                ], className="form-footer"),
            ], id="faq-content", className="modal-body tab-content"),

            # Data Request Tab Content
            html.Div([
                html.H3("Request Access to Research Data"),
                html.P("Please complete the form below to request access to the underlying research data. We will review your request and respond as soon as possible.", className="data-request-intro"),

                html.Div([
                    html.Label("Contact Information",
                               className="form-section-header"),

                    html.Div([
                        html.Label("Full Name *"),
                        dcc.Input(id="req-name", type="text",
                                  placeholder="Enter your full name", className="form-input"),
                    ], className="form-group"),

                    html.Div([
                        html.Label("Email Address *"),
                        dcc.Input(id="req-email", type="email",
                                  placeholder="your.email@institution.edu", className="form-input"),
                    ], className="form-group"),

                    html.Div([
                        html.Label("Institution/Organization *"),
                        dcc.Input(id="req-institution", type="text",
                                  placeholder="University or organization name", className="form-input"),
                    ], className="form-group"),

                    html.Div([
                        html.Label("Position/Role *"),
                        dcc.Input(id="req-role", type="text",
                                  placeholder="e.g., Graduate Student, Faculty, Researcher", className="form-input"),
                    ], className="form-group"),
                ]),

                html.Div([
                    html.Label("Research Purpose",
                               className="form-section-header"),

                    html.Div([
                        html.Label("Research Question/Purpose *"),
                        dcc.Textarea(
                            id="req-purpose", placeholder="Briefly describe your research question and how you plan to use this data", className="form-textarea"),
                    ], className="form-group"),
                ]),

                html.Div([
                    html.Button("Submit Data Request", id="submit-data-request",
                                className="submit-button", disabled=True),
                    html.Div(id="data-request-output",
                             className="form-output"),
                ], className="form-submit-section"),

                html.P([
                    "Questions? Contact: ",
                    html.A("placeholder@placeholder.com",
                           href="mailto:placeholder@placeholder.com")
                ], className="form-footer"),

            ], id="data-request-content", className="modal-body tab-content", style={"display": "none"}),
        ], className="modal-content"),
    ], id="faq-modal", className="modal", style={"display": "none"}),
], id="app-root", className="app-root")


@callback(
    Output("submit-data-request", "disabled"),
    [Input("req-name", "value"),
     Input("req-email", "value"),
     Input("req-institution", "value"),
     Input("req-role", "value"),
     Input("req-purpose", "value")]
)
def toggle_submit_button(name, email, institution, role, purpose):
    # Button is enabled (disabled=False) only if all fields have values
    if all([name, email, institution, role, purpose]):
        return False
    return True


@callback(
    [Output("faq-content", "style"),
     Output("data-request-content", "style"),
     Output("tab-faq", "className"),
     Output("tab-data-request", "className")],
    [Input("tab-faq", "n_clicks"),
     Input("tab-data-request", "n_clicks")],
    prevent_initial_call=True
)
def switch_tabs(faq_clicks, data_clicks):
    ctx = callback_context
    if not ctx.triggered:
        return {"display": "block"}, {"display": "none"}, "tab-button active-tab", "tab-button"

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if button_id == "tab-faq":
        return {"display": "block"}, {"display": "none"}, "tab-button active-tab", "tab-button"
    else:  # tab-data-request
        return {"display": "none"}, {"display": "block"}, "tab-button", "tab-button active-tab"


@callback(
    Output("faq-modal", "style"),
    [Input("faq-button", "n_clicks"), Input("close-faq", "n_clicks")],
    [State("faq-modal", "style")],
    prevent_initial_call=True
)
def toggle_faq_modal(open_clicks, close_clicks, current_style):
    ctx = callback_context
    if not ctx.triggered:
        return {"display": "none"}

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if button_id == "faq-button":
        return {"display": "block"}
    elif button_id == "close-faq":
        return {"display": "none"}

    return current_style if current_style else {"display": "none"}


@callback(
    [Output("dots-dropdown", "options"), Output("dots-dropdown",
                                                "value"), Output("dots-dropdown-label", "children")],
    [Input("school-toggles", "value")]
)
def update_dots_dropdown(school):
    if school == "modalities":
        options = LABELS["dots_dropdown_options_modality"]
        value = DEFAULT_DOTS_DROPDOWN_MODALITIES
        label = LABELS["dots_dropdown_label_modality"]
    elif school == "disparity":
        options = LABELS["dots_dropdown_options_disparity"]
        value = DEFAULT_DOTS_DROPDOWN_DISPARITY
        label = LABELS["dots_dropdown_label_disparity"]
    else:
        options = []
        value = None
        label = ""
    return options, value, label


@callback(
    Output("ri-threshold-container", "style"),
    Input("school-toggles", "value")
)
def toggle_ri_threshold(school):
    if school == "disparity":
        return {"display": "block"}
    else:
        return {"display": "none"}


@callback(
    [
        Output("locale-filter", "value"),
        Output("courses-filter", "value"),
        Output("courses-filter-mode", "value"),
        Output("modality-filter", "value"),
        Output("extra-teachers-filter", "value"),
        Output("ratio-threshold", "value"),
        Output("ri-threshold", "value"),
        Output("course-total-offered", "value"),
    ],
    Input("reset-filters", "n_clicks"),
    prevent_initial_call=True
)
def reset_filters(n_clicks):
    # Calculate initial max_course_total from all data
    all_schools = data_loader.SCHOOLDATA["approved_all"]
    all_schools_with_courses = calculate_total_offered(all_schools.copy())
    initial_max = int(all_schools_with_courses['total_offered'].max(
    )) if not all_schools_with_courses.empty else 16
    return [], [], "all", [], [], [0, 2500], [-1.0, 1.0], [0, initial_max]


@callback(
    [
        Output("main-map", "figure"),
        Output("custom-legend-container", "children"),
        Output("ratio-threshold", "max"),
        Output("ratio-threshold", "marks"),
        Output("course-total-offered", "max"),
        Output("course-total-offered", "marks"),
    ],
    [
        Input("map-options-toggle", "value"),
        Input("school-toggles", "value"),
        Input("dots-dropdown", "value"),
        Input("underlay-dropdown", "value"),
        Input("school-search", "value"),
        Input("locale-filter", "value"),
        Input("courses-filter", "value"),
        Input("courses-filter-mode", "value"),
        Input("modality-filter", "value"),
        Input("extra-teachers-filter", "value"),
        Input("ratio-threshold", "value"),
        Input("ri-threshold", "value"),
        Input("course-total-offered", "value"),
    ]
)
def update_map(map_options, school, dots_dropdown, underlay_dropdown, selected_school, locale_filter, courses_filter, courses_filter_mode, modality_filter, extra_teachers_filter, ratio_threshold, ri_threshold, course_total_offered):

    ctx = callback_context
    triggered = ctx.triggered if ctx else []
    if triggered:
        triggered_id = triggered[0]['prop_id'].split('.')[0]
    else:
        triggered_id = None

    fig = go.Figure()
    outline_lon = []
    outline_lat = []
    for x, y in data_loader.GEODATA["ga_outline"]:
        outline_lon.extend(x + [None])
        outline_lat.extend(y + [None])
    fig.add_trace(go.Scattermapbox(
        lon=outline_lon, lat=outline_lat, mode="lines",
        line=dict(color="black", width=1),
        opacity=1.0,
        name="Georgia Outline", showlegend=False, visible=True,
        hoverinfo="skip"
    ))

    # Add city labels if toggled
    if "city_labels" in map_options:
        # Draw labels outside the points with leader lines (approximate offsets)
        city_df = data_loader.SCHOOLDATA["city_labels"].copy()
        # Use city label configuration from settings
        offsets_m = CITY_LABEL_OFFSETS_M
        city_text_settings = CITY_LABEL_TEXT_SETTINGS
        city_text_size = CITY_LABEL_TEXT_SIZE
        # Use proper projection to EPSG:3857 to apply meter offsets accurately (like map1)
        transformer_to_3857 = Transformer.from_crs(
            "EPSG:4326", "EPSG:3857", always_xy=True)
        transformer_to_4326 = Transformer.from_crs(
            "EPSG:3857", "EPSG:4326", always_xy=True)
        # Add highway labels if toggled
        if "highway_labels" in map_options:
            highway_labels = data_loader.GEODATA.get("highway_labels", [])
            # Offset in degrees latitude (approx 0.04 deg ~ 4.5km)
            label_offset_deg = 0.04
            for h in highway_labels:
                # Leader line from highway point to label
                label_lat = h["lat"] + label_offset_deg
                label_lon = h["lon"]
                # Draw stapled leader line by drawing small line segments (dash imitation)
                num_dashes = 6
                dash_frac = 0.08  # fraction of total length occupied by each dash
                lons = []
                lats = []
                for i in range(num_dashes):
                    center = (i + 0.5) / num_dashes
                    start = max(0.0, center - dash_frac / 2)
                    end = min(1.0, center + dash_frac / 2)
                    sx = h["lon"] + (label_lon - h["lon"]) * start
                    sy = h["lat"] + (label_lat - h["lat"]) * start
                    ex = h["lon"] + (label_lon - h["lon"]) * end
                    ey = h["lat"] + (label_lat - h["lat"]) * end
                    lons.extend([sx, ex, None])
                    lats.extend([sy, ey, None])
                fig.add_trace(go.Scattermapbox(
                    lon=lons, lat=lats, mode="lines",
                    line=dict(color="#2a3b4c", width=1), showlegend=False, hoverinfo="skip"
                ))
                # Draw label text (invisible marker + text)
                fig.add_trace(go.Scattermapbox(
                    lon=[label_lon], lat=[label_lat], mode="markers+text",
                    marker=dict(size=2, color="#2a3b4c", opacity=0),
                    text=[h["name"]], textfont=dict(size=12, color="#2a3b4c"),
                    name=h["name"], showlegend=False, hoverinfo="skip",
                    textposition="top center"
                ))

        # Add leader line and label for each city using projected offsets
        for _, row in city_df.iterrows():
            city = row["city"]
            lat = float(row["lat"])
            lon = float(row["lon"])
            # project to meters
            px, py = transformer_to_3857.transform(lon, lat)
            dx_m, dy_m = offsets_m.get(city, (20000, 20000))
            # Determine label anchor for the leader line (keep original map1 offsets)
            nudge_x, nudge_y = city_text_settings.get(
                city, {}).get("nudge", (0, 0))
            label_px = px + dx_m + nudge_x
            label_py = py + dy_m + nudge_y
            # Compute a separate text anchor (small shift in meters) that only affects text placement
            text_nudge_x, text_nudge_y = city_text_settings.get(
                city, {}).get("text_nudge", (0, 0))
            label_px_text = label_px + text_nudge_x
            label_py_text = label_py + text_nudge_y
            # reproject label anchor back to lat/lon (used by leader line)
            label_lon, label_lat = transformer_to_4326.transform(
                label_px, label_py)
            # reproject text-only anchor for text symbol placement
            label_lon_text, label_lat_text = transformer_to_4326.transform(
                label_px_text, label_py_text)
            # line from point to label
            fig.add_trace(go.Scattermapbox(
                lon=[lon, label_lon], lat=[lat, label_lat], mode="lines",
                line=dict(color="black", width=1), showlegend=False, hoverinfo="skip"
            ))
            # label text (use an invisible marker + text to ensure placement)
            textposition = city_text_settings.get(
                city, {}).get("textposition", "middle right")
            fig.add_trace(go.Scattermapbox(
                lon=[label_lon_text], lat=[
                    label_lat_text], mode="markers+text",
                marker=dict(size=2, color="black", opacity=0),
                text=[city], textfont=dict(size=city_text_size, color="black"),
                showlegend=False, hoverinfo="skip",
                textposition=textposition
            ))

    # Add underlay if selected
    if underlay_dropdown != DEFAULT_UNDERLAY_OPTION:
        geojson = data_loader.CBGDATA[underlay_dropdown]['geojson']
        locations = data_loader.CBGDATA[underlay_dropdown]['locations']
        z_values = data_loader.CBGDATA[underlay_dropdown]['z_values']
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=locations,
            z=z_values,
            colorscale=UNDERLAY_COLOR_SCALE,
            zmin=0,
            zmax=4,
            showscale=False,
            marker_opacity=1,
            marker_line_width=0,
            marker_line_color='rgba(0,0,0,0)',
            hoverinfo='skip'
        ))

    underlay_legend = None
    if underlay_dropdown != DEFAULT_UNDERLAY_OPTION and "show_legend" in map_options:
        underlay_label = next(
            (opt['label'] for opt in UNDERLAY_OPTIONS if opt['value'] == underlay_dropdown), underlay_dropdown)
        underlay_items = []
        if underlay_dropdown == "black_population_ratio":
            labels = ["Lowest 20%", "20–40%",
                      "40–60%", "60–80%", "Highest 20%"]
        elif underlay_dropdown == "median_household_income":
            labels = ["$2,499 - $53,240", "$53,240 - $84,175",
                      "$84,175 - $122,700", "$122,700 - $180,134", "$180,134 - $250,001"]
        elif underlay_dropdown == "edu_hs_or_more":
            labels = ["0 - 508", "508 - 832", "832 - 1,199",
                      "1,199 - 1,711", "1,711 - 3,965"]
        elif underlay_dropdown == "households_with_subscription":
            labels = ["0 - 288", "288 - 472",
                      "472 - 679", "679 - 965", "965 - 2,070"]
        else:
            labels = ["Lowest 20%", "20–40%",
                      "40–60%", "60–80%", "Highest 20%"]
        for color, label in zip(UNDERLAY_COLORS, labels):
            underlay_items.append(html.Div([
                html.Span(style={"backgroundColor": color, "width": "12px", "height": "12px", "display": "inline-block",
                          "marginRight": "8px", "border": "1px solid #000" if color == UNDERLAY_COLORS[0] else "none"}),
                html.Span(label, className="legend-dot-label")
            ], className="legend-dot-row-underlay"))
        underlay_legend = html.Div([
            html.Div(underlay_label, className="legend-title"),
            html.Div(underlay_items, className="legend-dot-row-wrap-underlay")
        ], className="legend-block legend-underlay-block")

    if "counties" in map_options:
        all_lon = []
        all_lat = []
        for x, y in data_loader.GEODATA["county_lines"]:
            all_lon.extend(x + [None])
            all_lat.extend(y + [None])
        fig.add_trace(go.Scattermapbox(
            lon=all_lon, lat=all_lat, mode="lines",
            line=dict(color="gray", width=0.5),
            opacity=0.8,
            name="County Lines", showlegend=True, visible=True,
            hoverinfo="skip"
        ))

    if "highways" in map_options:
        all_lon = []
        all_lat = []
        for x, y in data_loader.GEODATA["highway_lines"]:
            all_lon.extend(x + [None])
            all_lat.extend(y + [None])
        fig.add_trace(go.Scattermapbox(
            lon=all_lon, lat=all_lat, mode="lines",
            line=dict(color="gray", width=1.5),
            opacity=1.0,
            name="Highways", showlegend=True, visible=True,
            hoverinfo="skip"
        ))

    legend_html = None
    legend_extra = None
    if school == "modalities":
        modality_type = dots_dropdown
        merged = data_loader.SCHOOLDATA["gadoe"].copy()
        coords = data_loader.SCHOOLDATA["approved_all"][[
            "UNIQUESCHOOLID", "SCHOOL_NAME", "lat", "lon", "SYSTEM_NAME", "School City", "Locale",
            "Race: Asian", "Race: Black", "Ethnicity: Hispanic", "Race: White",
            "Total Student Count", "Female", "Male"
        ]]
        merged = merged.merge(coords, on="UNIQUESCHOOLID", how="left")
        # Merge in precomputed modality info (grade range, course counts)
        modality_info = data_loader.SCHOOLDATA["school_modality_info"][[
            "UNIQUESCHOOLID", "GRADE_RANGE", "virtual_course_count", "inperson_course_count", "virtual_course_count_2", "inperson_course_count_2", "approved_course_count", "approved_course_count_2"
        ]]
        merged = merged.merge(modality_info, on="UNIQUESCHOOLID", how="left")
        merged["approved_teachers"] = merged["UNIQUESCHOOLID"].apply(
            lambda x: data_loader.SCHOOLDATA["approved_teachers_count"].get(str(x), 0))
        merged["extra_teachers"] = merged["UNIQUESCHOOLID"].apply(
            lambda x: data_loader.SCHOOLDATA["extra_teachers_count"].get(str(x), 0))
        # Determine which column to use for logic classification
        if modality_type == "LOGIC_CLASS_2_TEACHERS":
            logic_col = "LOGIC_CLASS_2"
        else:
            logic_col = modality_type

        # Choose classification function based on modality type
        if modality_type == "LOGIC_CLASS_2_TEACHERS":
            merged["Classification"] = merged[logic_col].apply(
                data_loader.classify_modality_with_teachers)
        else:
            merged["Classification"] = merged[logic_col].apply(
                data_loader.classify_modality)

        # Override classification if no CS enrollment
        merged.loc[merged['CS_Enrollment'] == 0, 'Classification'] = "No"

        # Calculate student teacher ratio for filtering
        merged["Total Student Count"] = merged["Total Student Count"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        merged["approved_teachers"] = merged["approved_teachers"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        merged["extra_teachers"] = merged["extra_teachers"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        merged["student_teacher_ratio"] = merged.apply(
            lambda row: row["Total Student Count"] /
            (row["approved_teachers"] + row["extra_teachers"])
            if (row["approved_teachers"] + row["extra_teachers"]) not in [0, None, "", float('nan')] else 0.0,
            axis=1
        )

        # Apply filters
        if locale_filter:
            merged = merged[merged['Locale'].isin(locale_filter)]

        # Courses filter with mode (All/Any/None)
        merged = filter_by_courses(merged, courses_filter, courses_filter_mode)

        if modality_filter:
            merged = merged[merged['Classification'].isin(modality_filter)]

        if extra_teachers_filter:
            merged = merged[merged['UNIQUESCHOOLID'].apply(
                lambda x: data_loader.SCHOOLDATA["extra_teachers"].get(str(x), False))]

        merged = merged[(merged['student_teacher_ratio'] >= ratio_threshold[0]) & (
            merged['student_teacher_ratio'] <= ratio_threshold[1])]

        # Course total offered filter
        merged = calculate_total_offered(merged)
        # Calculate max course total before applying filter
        max_course_total = int(
            merged['total_offered'].max()) if not merged.empty else 16
        merged = merged[(merged['total_offered'] >= course_total_offered[0]) & (
            merged['total_offered'] <= course_total_offered[1])]

        # Selected school/district/city filter and center/zoom
        merged, center, zoom = apply_location_filter_and_get_center(
            merged, selected_school)

        modality_counts = merged["Classification"].value_counts()
        # Choose color map based on modality type
        if modality_type == "LOGIC_CLASS_2_TEACHERS":
            color_map = TEACHER_MODALITY_COLOR_MAP
        else:
            color_map = MODALITY_COLOR_MAP

        # Add red highlight for selected school (behind all other dots)
        if selected_school and selected_school.startswith("school:"):
            school_id = selected_school.split(":", 1)[1]
            highlight_school = merged[merged["UNIQUESCHOOLID"] == school_id]
            if not highlight_school.empty:
                # Add larger red circle behind the selected school
                fig.add_trace(go.Scattermapbox(
                    lon=highlight_school["lon"],
                    lat=highlight_school["lat"],
                    mode="markers",
                    marker=dict(size=15, color="red", opacity=0.8),
                    name="",
                    visible=True,
                    showlegend=False,
                    hoverinfo="skip"  # Don't show hover for the highlight circle
                ))

        for modality, color in color_map.items():
            df = merged[merged["Classification"] == modality].copy()
            df["Total Student Count"] = df["Total Student Count"].apply(
                lambda x: int(x) if pd.notnull(x) else 0)
            df["approved_teachers"] = df["approved_teachers"].apply(
                lambda x: int(x) if pd.notnull(x) else 0)
            df["extra_teachers"] = df["extra_teachers"].apply(
                lambda x: int(x) if pd.notnull(x) else 0)

            df["student_teacher_ratio"] = df.apply(
                lambda row: row["Total Student Count"] /
                (row["approved_teachers"] + row["extra_teachers"])
                if (row["approved_teachers"] + row["extra_teachers"]) not in [0, None, "", float('nan')] else 0.0,
                axis=1
            )

            from data_dashboard.data_loader import ratio_fmt, build_unified_hover
            df["ratio_display"] = df["student_teacher_ratio"].apply(ratio_fmt)
            df["school_hover"] = df.apply(lambda row: data_loader.build_unified_hover(
                row, HOVER_TEMPLATES["unified"]), axis=1)
            # Determine marker symbol for teacher modality
            marker_symbol = "circle"
            if modality_type == "LOGIC_CLASS_2_TEACHERS" and "Extra Teachers" in modality:
                marker_symbol = "triangle"

            if modality == "No":
                # White outline
                fig.add_trace(go.Scattermapbox(
                    lon=df["lon"], lat=df["lat"],
                    mode="markers", marker=dict(size=11, color="white", opacity=1, symbol=marker_symbol),
                    name="",
                    visible=True,
                    showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["school_hover", "UNIQUESCHOOLID"]].values,
                    hoverlabel=dict(bgcolor="white",
                                    bordercolor=color, font_color="black")
                ))
                # Gray center
                fig.add_trace(go.Scattermapbox(
                    lon=df["lon"], lat=df["lat"],
                    mode="markers", marker=dict(size=9, color=color, opacity=1, symbol=marker_symbol),
                    name="",
                    visible=True,
                    showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["school_hover", "UNIQUESCHOOLID"]].values,
                    hoverlabel=dict(bgcolor="white",
                                    bordercolor=color, font_color="black")
                ))
            else:
                fig.add_trace(go.Scattermapbox(
                    lon=df["lon"], lat=df["lat"],
                    mode="markers", marker=dict(size=9, color=color, opacity=1, symbol=marker_symbol),
                    name="",
                    visible=True,
                    showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["school_hover", "UNIQUESCHOOLID"]].values,
                    hoverlabel=dict(bgcolor="white",
                                    bordercolor=color, font_color="black")
                ))

        if "show_legend" in map_options:
            if modality_type == "LOGIC_CLASS_2_TEACHERS":
                modality_title = LABELS["legend_titles"]["teachers_modality"]
                legend_labels = TEACHER_MODALITY_LABELS
                legend_class_map = TEACHER_MODALITY_CLASS_MAP
                legend_color_map = TEACHER_MODALITY_COLOR_MAP
            else:
                modality_title = LABELS["legend_titles"]["expanded_modality"]
                legend_labels = MODALITY_LABELS
                legend_class_map = MODALITY_CLASS_MAP
                legend_color_map = MODALITY_COLOR_MAP

            legend_html = html.Div([
                html.Div(modality_title, className="legend-title"),
                html.Div([
                    html.Div([
                        html.Span(
                            className=f"legend-dot legend-dot-{legend_class_map[k]}"),
                        html.Span(
                            f"{legend_labels[k]} ({modality_counts.get(k, 0)})", className="legend-dot-label")
                    ], className="legend-dot-row")
                    for k in legend_color_map if k in modality_counts
                ], className="legend-dot-row-wrap")
            ], className="legend-block legend-modality-block")
    elif school == "disparity":
        legend_items = []
        disparity_col = dots_dropdown
        # Use preloaded data
        schools = data_loader.SCHOOLDATA["approved_all"][[
            "UNIQUESCHOOLID", "SCHOOL_NAME", "lat", "lon", "GRADE_RANGE",
            "Race: Asian", "Race: Black", "Ethnicity: Hispanic", "Race: White",
            "Total Student Count", "Female", "Male", "SYSTEM_NAME", "School City", "Locale"
        ]].copy()
        disparity = data_loader.SCHOOLDATA["disparity"]
        schools = schools.merge(disparity, on="UNIQUESCHOOLID", how="inner")

        # Calculate student teacher ratio for filtering
        schools["CS_Enrollment"] = schools["CS_Enrollment"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        schools["Certified_Teachers"] = schools["Certified_Teachers"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        # Include extra certified teachers in the denominator
        schools["extra_teachers"] = schools["UNIQUESCHOOLID"].apply(
            lambda x: data_loader.SCHOOLDATA["extra_teachers_count"].get(str(x), 0))
        schools["student_teacher_ratio"] = schools.apply(
            lambda row: row["CS_Enrollment"] /
            (row["Certified_Teachers"] + row["extra_teachers"])
            if (row["Certified_Teachers"] + row["extra_teachers"]) not in [0, None, "", float('nan')] else 0.0,
            axis=1
        )

        # Apply filters
        if locale_filter:
            schools = schools[schools['Locale'].isin(locale_filter)]

        # Courses filter
        schools = filter_by_courses(
            schools, courses_filter, courses_filter_mode)

        # Modality filter not applied for disparity
        # Extra teachers not applied for disparity

        schools = schools[(schools['student_teacher_ratio'] >= ratio_threshold[0]) & (
            schools['student_teacher_ratio'] <= ratio_threshold[1])]

        # RI thresholds
        schools = schools[(schools[disparity_col] >= ri_threshold[0]) & (
            schools[disparity_col] <= ri_threshold[1])]

        # Course total offered filter
        schools = calculate_total_offered(schools)
        # Calculate max course total before applying filter
        max_course_total = int(
            schools['total_offered'].max()) if not schools.empty else 16
        schools = schools[(schools['total_offered'] >= course_total_offered[0]) & (
            schools['total_offered'] <= course_total_offered[1])]

        # Selected school/district/city filter and center/zoom
        schools, center, zoom = apply_location_filter_and_get_center(
            schools, selected_school, school_zoom=12)

        ri_cols = ["RI_Asian", "RI_Black",
                   "RI_Hispanic", "RI_White", "RI_Female"]

        vals = pd.to_numeric(schools[disparity_col], errors='coerce')
        bin_edges = data_loader.get_ri_bin_edges(vals)
        bin_labels = [
            f"{bin_edges[0]:.4f} to {bin_edges[1]:.4f}",
            f"{bin_edges[1]:.4f} to -0.0500",
            "-0.0500 to 0.0500",
            f"0.0500 to {bin_edges[4]:.4f}",
            f"{bin_edges[4]:.4f} to {bin_edges[5]:.4f}"
        ]
        schools['RI_bin'] = pd.cut(
            vals,
            bins=bin_edges,
            labels=range(5),
            include_lowest=True,
            right=True
        )
        schools['Color'] = schools['RI_bin'].map(
            lambda x: RI_BIN_COLORS[int(x)] if pd.notnull(x) else None)

        # Add red highlight for selected school (behind all other dots)
        if selected_school and selected_school.startswith("school:"):
            school_id = selected_school.split(":", 1)[1]
            highlight_school = schools[schools["UNIQUESCHOOLID"] == school_id]
            if not highlight_school.empty:
                # Add larger red circle behind the selected school
                fig.add_trace(go.Scattermapbox(
                    lon=highlight_school["lon"],
                    lat=highlight_school["lat"],
                    mode="markers",
                    marker=dict(size=15, color="red", opacity=0.8),
                    name="",
                    visible=True,
                    showlegend=False,
                    hoverinfo="skip"  # Don't show hover for the highlight circle
                ))

        # Parity bin (i=2) - outlined dots: black (outline) then white (center)
        i_parity = 2
        color = RI_BIN_COLORS[i_parity]
        label = bin_labels[i_parity]
        df = schools[schools['RI_bin'] == i_parity].copy()
        if not df.empty:
            df["ri_hover"] = df.apply(lambda row: data_loader.build_unified_hover(
                row, HOVER_TEMPLATES["unified"], disparity_col=disparity_col, ri_cols=ri_cols), axis=1)
            # Black outline dot (same size as others)
            fig.add_trace(go.Scattermapbox(
                lon=df['lon'], lat=df['lat'],
                mode='markers', marker=dict(size=9, color='black', opacity=1),
                name="", visible=True, showlegend=False,
                hoverinfo="skip"
            ))
            # White center dot (smaller, on top, with hover)
            fig.add_trace(go.Scattermapbox(
                lon=df['lon'], lat=df['lat'],
                mode='markers', marker=dict(size=7, color='white', opacity=1),
                name="", visible=True, showlegend=False,
                hovertemplate="%{customdata[0]}",
                customdata=df[["ri_hover", "UNIQUESCHOOLID"]].values,
                hoverlabel=dict(bgcolor="white",
                                bordercolor="#cccccc", font_color="black")
            ))
        # Other bins
        for i in [0, 1, 3, 4]:
            color = RI_BIN_COLORS[i]
            label = bin_labels[i]
            df = schools[schools['RI_bin'] == i].copy()
            if not df.empty:
                df["ri_hover"] = df.apply(lambda row: data_loader.build_unified_hover(
                    row, HOVER_TEMPLATES["unified"], disparity_col=disparity_col, ri_cols=ri_cols), axis=1)
                fig.add_trace(go.Scattermapbox(
                    lon=df['lon'], lat=df['lat'],
                    mode='markers', marker=dict(size=9, color=color, opacity=1),
                    name="", visible=True, showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["ri_hover", "UNIQUESCHOOLID"]].values,
                    hoverlabel=dict(bgcolor="white",
                                    bordercolor=color, font_color="black")
                ))

        legend_items = []
        for i in range(5):
            color = RI_BIN_COLORS[i]
            label = bin_labels[i]
            count = (schools['RI_bin'] == i).sum()
            legend_items.append(html.Div([
                html.Span(style={
                    "backgroundColor": color,
                    "width": "12px",
                    "height": "12px",
                    "display": "inline-block",
                    "border": "1px solid black" if color == "#ffffff" else "none",
                    "marginRight": "8px",
                    "borderRadius": "50%"
                }),
                html.Span(f"{label} ({count} schools)",
                          className="legend-dot-label")
            ], className="legend-dot-row"))
        if "show_legend" in map_options:
            legend_title = LABELS["legend_titles"].get(
                disparity_col, LABELS["legend_titles"]["default"])
            legend_html = html.Div([
                html.Div(legend_title, className="legend-title"),
                html.Div([
                    html.Div(item, className="legend-dot-row")
                    for item in legend_items
                ], className="legend-dot-row-wrap")
            ], className="legend-block legend-disparity-block")
    elif school == "gender":
        gender_col = dots_dropdown
        # Use preloaded data
        schools = data_loader.SCHOOLDATA["gender"]
        schools = schools.merge(data_loader.SCHOOLDATA["approved_all"][[
                                "UNIQUESCHOOLID", "Locale"]], on="UNIQUESCHOOLID", how="left")
        schools = schools.merge(data_loader.SCHOOLDATA["gadoe"][[
                                "UNIQUESCHOOLID", "CS_Enrollment", "Certified_Teachers"]], on="UNIQUESCHOOLID", how="left")

        # Calculate student teacher ratio for filtering
        schools["CS_Enrollment"] = schools["CS_Enrollment"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        schools["Certified_Teachers"] = schools["Certified_Teachers"].apply(
            lambda x: int(x) if pd.notnull(x) else 0)
        # Include extra teachers in gender view as well
        schools["extra_teachers"] = schools["UNIQUESCHOOLID"].apply(
            lambda x: data_loader.SCHOOLDATA["extra_teachers_count"].get(str(x), 0))
        schools["student_teacher_ratio"] = schools.apply(
            lambda row: row["CS_Enrollment"] /
            (row["Certified_Teachers"] + row["extra_teachers"])
            if (row["Certified_Teachers"] + row["extra_teachers"]) not in [0, None, "", float('nan')] else 0.0,
            axis=1
        )

        # Apply filters
        if locale_filter:
            schools = schools[schools['Locale'].isin(locale_filter)]

        # Courses filter
        schools = filter_by_courses(
            schools, courses_filter, courses_filter_mode)

        # Modality and extra teachers not applied for gender

        schools = schools[(schools['student_teacher_ratio'] >= ratio_threshold[0]) & (
            schools['student_teacher_ratio'] <= ratio_threshold[1])]

        # RI thresholds
        schools = schools[(schools[gender_col] >= ri_threshold[0]) & (
            schools[gender_col] <= ri_threshold[1])]

        # Course total offered filter
        schools = calculate_total_offered(schools)
        # Calculate max course total before applying filter
        max_course_total = int(
            schools['total_offered'].max()) if not schools.empty else 16
        schools = schools[(schools['total_offered'] >= course_total_offered[0]) & (
            schools['total_offered'] <= course_total_offered[1])]

        # Selected school/district/city filter and center/zoom
        schools, center, zoom = apply_location_filter_and_get_center(
            schools, selected_school, school_zoom=12)

        color_bins = GENDER_COLOR_BINS
        legend_labels = [
            f'{low} to {high}' for (low, high, _) in color_bins
        ]
        schools['Color'] = pd.to_numeric(
            schools[gender_col], errors='coerce').apply(lambda v: data_loader.get_gender_color(v, color_bins))
        for i, (low, high, color) in enumerate(color_bins):
            df = schools[schools['Color'] == color]
            fig.add_trace(go.Scattermapbox(
                lon=df['lon'], lat=df['lat'],
                mode='markers', marker=dict(size=9, color=color, opacity=0.8),
                name=f"{legend_labels[i]} ({len(df)})",
                visible=True,
                showlegend=False,
                hovertemplate="%{customdata[0]}",
                customdata=df[["SCHOOL_NAME", "UNIQUESCHOOLID"]].values
            ))

    fig.update_layout(
        mapbox_style="white-bg",  # blank basemap
        mapbox_zoom=zoom,
        mapbox_center=center,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="white",
        plot_bgcolor="white",
        dragmode="pan",
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="black",
            font_color="black",
            font_size=12,
            font_family="Arial, sans-serif"
        )
    )
    overlay_legend = None
    if "show_legend" in map_options:
        overlay_items = []
        if "counties" in map_options:
            overlay_items.append(
                html.Div([
                    html.Span(
                        className="legend-overlay-line legend-overlay-county"),
                    html.Span(LABELS["overlay_legend"]["county"],
                              className="legend-overlay-label")
                ], className="legend-overlay-row legend-overlay-county-row")
            )
        if "highways" in map_options:
            overlay_items.append(
                html.Div([
                    html.Span(
                        className="legend-overlay-line legend-overlay-highway"),
                    html.Span(LABELS["overlay_legend"]["highway"],
                              className="legend-overlay-label")
                ], className="legend-overlay-row legend-overlay-highway-row")
            )
        if overlay_items:
            overlay_legend = html.Div(
                overlay_items,
                className="legend-block legend-overlay-block"
            )

    legend_combined = []
    if legend_html:
        legend_combined.append(
            html.Div(legend_html, className="legend-flex-8"))
    if overlay_legend:
        legend_combined.append(
            html.Div(overlay_legend, className="legend-flex-2"))
    if underlay_legend:
        legend_combined.append(
            html.Div(underlay_legend, className="underlay-legend"))
    if not legend_combined:
        legend_combined = None

    max_ratio = 2500
    marks = {0: '0', 500: '500', 1000: '1000',
             1500: '1500', 2000: '2000', 2500: '2500'}

    # Dynamic course total marks
    course_marks = {i: str(i) for i in range(
        0, max_course_total + 1, max(1, max_course_total // 4))}
    if max_course_total not in course_marks:
        course_marks[max_course_total] = str(max_course_total)

    return fig, legend_combined, max_ratio, marks, max_course_total, course_marks


@callback(
    Output("loading-message", "children"),
    [
        Input("map-options-toggle", "value"),
        Input("school-toggles", "value"),
        Input("dots-dropdown", "value"),
        Input("underlay-dropdown", "value"),
        Input("locale-filter", "value"),
        Input("courses-filter", "value"),
        Input("courses-filter-mode", "value"),
        Input("modality-filter", "value"),
        Input("extra-teachers-filter", "value"),
        Input("ratio-threshold", "value"),
        Input("ri-threshold", "value"),
        Input("course-total-offered", "value"),
    ]
)
def update_loading_message(map_options, school, dots_dropdown, underlay_dropdown, locale_filter, courses_filter, courses_filter_mode, modality_filter, extra_teachers_filter, ratio_threshold, ri_threshold, course_total_offered):
    components = []
    messages = []
    if underlay_dropdown != DEFAULT_UNDERLAY_OPTION:
        messages.append("Loading map underlay")
    if school == "modalities":
        messages.append("Loading modality dots")
    elif school == "disparity":
        messages.append("Loading representation index dots")
    elif school == "gender":
        messages.append("Loading gender dots")
    if "counties" in map_options:
        messages.append("Loading county lines")
    if "highways" in map_options:
        messages.append("Loading highways")
    if messages:
        components.append(" | ".join(messages))
    # if underlay_dropdown != DEFAULT_UNDERLAY_OPTION:
    #     components.append(html.Br())
    #     components.append(
    #         html.Div("This might take a minute...", style={"textAlign": "center"}))
    if not components:
        components.append("Loading map")
    return components


@callback(
    Output("course-list", "children"),
    [Input("main-map", "hoverData"), Input("school-search",
                                           "value"), Input("school-toggles", "value")]
)
def update_course_list(hoverData, selected_school, school_toggles):
    if hoverData is not None and hoverData.get('points'):
        point = hoverData['points'][0]
        if 'customdata' in point and len(point['customdata']) >= 2:
            school_id = str(point['customdata'][1])
            school_name = data_loader.SCHOOLDATA["school_names"].get(
                school_id, f"School {school_id}")
        else:
            # Fallback if no customdata
            return html.Div("No course data available.")
    elif selected_school and selected_school.startswith("school:"):
        school_id = selected_school.split(":", 1)[1]
        school_name = data_loader.SCHOOLDATA["school_names"].get(
            school_id, f"School {school_id}")
    else:
        # No school hovered or selected: show nothing
        return html.Div()

    courses_counts = data_loader.SCHOOLDATA["courses"].get(school_id, {})

    total_offered = 0
    total_v = 0
    total_i = 0
    for course in APPROVED_COURSES:
        counts = courses_counts.get(course, {'virtual': 0, 'inperson': 0})
        virtual = counts.get('virtual', 0)
        inperson = counts.get('inperson', 0)
        total = virtual + inperson
        if total > 0:
            total_offered += 1
            total_v += virtual
            total_i += inperson

    summary = f"[Total: {total_offered} ({total_v + total_i})] [{total_i} In-Person (IP), {total_v} Virtual (V)]"

    # Show total students for disparity view if available
    show_total_students = (school_toggles == "disparity")
    total_students = None
    if show_total_students:
        school_row = data_loader.SCHOOLDATA["approved_all"][data_loader.SCHOOLDATA["approved_all"]
                                                            ["UNIQUESCHOOLID"] == school_id]
        if not school_row.empty and "Total Student Count" in school_row:
            total_students = school_row["Total Student Count"].iloc[0]
        if total_students is not None:
            total_students_display = suppress_value(total_students)
            summary += f" | Total Students: {total_students_display}"

    course_items = []
    for course in APPROVED_COURSES:
        counts = courses_counts.get(course, {'virtual': 0, 'inperson': 0})
        virtual = counts.get('virtual', 0)
        inperson = counts.get('inperson', 0)
        total = virtual + inperson
        if total == 0:
            count_str = "[0] "
            count_style = {"color": "red"}
            name_style = {}
        else:
            parts = []
            if inperson > 0:
                parts.append(f"{inperson} IP")
            if virtual > 0:
                parts.append(f"{virtual} V")
            count_str = f"[{', '.join(parts)}] "
            count_style = {"font-weight": "bold"}
            name_style = {"font-weight": "bold"}
        course_items.append(
            html.Li([html.Span(count_str, style=count_style), html.Span(get_course_display(course), style=name_style)]))

    return html.Div([
        html.Div([
            html.Strong(f"CS Courses at {school_name}:", style={
                        'margin-bottom': '8px', 'display': 'block', 'font-size': '1.17em', 'font-weight': '700', 'color': '#2a3b4c'}),
        ], className="sidebar-header"),
        html.Div(summary, style={'margin-bottom': '12px'}),
        html.Ul(course_items, style={
                'list-style': 'none', 'padding-left': '0'})
    ])


# Callback for sidebar toggle functionality
@callback(
    [Output("sidebar", "className"),
     Output("main-map-area", "className"),
     Output("course-info-legend", "style"),
     Output("sidebar-toggle", "children"),
     Output("sidebar-toggle", "title")],
    [Input("sidebar-toggle", "n_clicks"),
     Input("course-list", "children")],
    [State("sidebar", "className")]
)
def toggle_sidebar(n_clicks, course_list_content, current_sidebar_class):
    ctx = callback_context

    # Check if there's actual course content
    has_content = course_list_content and not (
        isinstance(course_list_content, dict) and
        course_list_content.get('props', {}).get('children') == []
    )

    # If no clicks yet, start with sidebar open
    if not n_clicks:
        return "sidebar", "main-map-area", {"display": "none"}, "▶", "Collapse Sidebar"

    # Only respond to sidebar toggle clicks, not course-list changes
    if ctx.triggered and ctx.triggered[0]['prop_id'].split('.')[0] == "sidebar-toggle":
        if "sidebar-collapsed" in (current_sidebar_class or ""):
            # Expanding sidebar - hide legend
            return "sidebar", "main-map-area", {"display": "none"}, "▶", "Collapse Sidebar"
        else:
            # Collapsing sidebar - show legend only if there's content
            legend_style = {"display": "block"} if has_content else {
                "display": "none"}
            return "sidebar sidebar-collapsed", "main-map-area sidebar-collapsed", legend_style, "◄", "Expand Sidebar"

    # For course-list changes, update legend visibility if sidebar is collapsed
    if "sidebar-collapsed" in (current_sidebar_class or ""):
        legend_style = {"display": "block"} if has_content else {
            "display": "none"}
        return current_sidebar_class, "main-map-area sidebar-collapsed", legend_style, "◄", "Expand Sidebar"

    # Default state
    return current_sidebar_class or "sidebar", "main-map-area", {"display": "none"}, "▶", "Collapse Sidebar"


# Callback for legend minimize/expand functionality
@callback(
    [Output("course-legend-content-wrapper", "className"),
     Output("legend-minimize", "style"),
     Output("legend-expand", "style")],
    [Input("legend-minimize", "n_clicks"),
     Input("legend-expand", "n_clicks")],
    [State("course-legend-content-wrapper", "className")]
)
def toggle_legend(minimize_clicks, expand_clicks, current_class):
    ctx = callback_context
    if not ctx.triggered:
        return "course-legend-expanded", {"display": "block"}, {"display": "none"}

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == "legend-minimize":
        return "course-legend-minimized", {"display": "none"}, {"display": "block"}
    elif button_id == "legend-expand":
        return "course-legend-expanded", {"display": "block"}, {"display": "none"}

    return current_class, {"display": "block"}, {"display": "none"}


# Callback to update course legend content based on current course list
@callback(
    Output("course-legend-list", "children"),
    [Input("course-list", "children")]
)
def update_course_legend(course_list_content):
    # Just return the course list content for the legend
    return course_list_content or html.Div()
