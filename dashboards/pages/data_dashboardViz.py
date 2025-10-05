# keep this at the top to silence warning
import data_dashboard.data_loader as data_loader
from data_dashboard.settings import *
from sqlalchemy import create_engine
import pandas as pd
import plotly.graph_objs as go
from dash import register_page, html, dcc, callback, Input, Output, State, callback_context
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
    ], className="main-map-area"),
    html.Div([
        html.H3("Map Options", className="sidebar-title"),
        dcc.Checklist(
            id="map-options-toggle",
            options=LABELS["map_options"],
            value=DEFAULT_MAP_OPTIONS,
            className="sidebar-legend-toggle"
        ),
        html.Div([
            html.Strong(LABELS["school_dots"]),
            dcc.RadioItems(
                id="school-toggles",
                options=LABELS["school_toggles"],
                value=DEFAULT_SCHOOL_TOGGLE,
                className="sidebar-school-toggles"
            ),
            html.Label(id="dots-dropdown-label",
                       className="sidebar-dots-dropdown-label"),
            dcc.Dropdown(
                id="dots-dropdown",
                options=[],
                value=None,
                clearable=False,
                className="sidebar-dots-dropdown"
            ),
        ], className="sidebar-section"),
        html.Div([
            html.Strong("Underlays"),
            dcc.Dropdown(
                id="underlay-dropdown",
                options=UNDERLAY_OPTIONS,
                value=DEFAULT_UNDERLAY_OPTION,
                clearable=False,
                className="sidebar-underlay-dropdown"
            ),
        ], className="sidebar-section"),
        html.Div([
            html.Div(id="course-list", className="course-list")
        ], className="sidebar-section"),
    ], className="sidebar"),
], className="app-root")


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
    [
        Output("main-map", "figure"),
        Output("custom-legend-container", "children"),
    ],
    [
        Input("map-options-toggle", "value"),
        Input("school-toggles", "value"),
        Input("dots-dropdown", "value"),
        Input("underlay-dropdown", "value"),
    ]
)
def update_map(map_options, school, dots_dropdown, underlay_dropdown):

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

    if triggered_id != 'map-options-toggle':
        # Add underlay if selected
        if underlay_dropdown != DEFAULT_UNDERLAY_OPTION:
            geojson = data_loader.CBGDATA['geojson']
            locations = data_loader.CBGDATA['locations']
            z_values = data_loader.CBGDATA['z_values']
            custom_greys = [
                [0, '#f0f0f0'],  # lightest
                [0.25, '#bdbdbd'],
                [0.5, '#969696'],
                [0.75, '#636363'],
                [1, '#252525']   # darkest
            ]
            fig.add_trace(go.Choroplethmapbox(
                geojson=geojson,
                locations=locations,
                z=z_values,
                colorscale=custom_greys,
                zmin=0,
                zmax=4,
                showscale=False,
                marker_opacity=0.55,
                marker_line_width=0,
                marker_line_color='rgba(0,0,0,0)',
                hoverinfo='skip'
            ))

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
            "UNIQUESCHOOLID", "SCHOOL_NAME", "lat", "lon"]]
        merged = merged.merge(coords, on="UNIQUESCHOOLID", how="left")
        # Merge in precomputed modality info (grade range, course counts)
        modality_info = data_loader.SCHOOLDATA["school_modality_info"][[
            "UNIQUESCHOOLID", "GRADE_RANGE", "virtual_course_count", "inperson_course_count", "virtual_course_count_2", "inperson_course_count_2", "approved_course_count", "approved_course_count_2"
        ]]
        merged = merged.merge(modality_info, on="UNIQUESCHOOLID", how="left")
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

        modality_counts = merged["Classification"].value_counts()
        # Choose color map based on modality type
        if modality_type == "LOGIC_CLASS_2_TEACHERS":
            color_map = TEACHER_MODALITY_COLOR_MAP
        else:
            color_map = MODALITY_COLOR_MAP

        for modality, color in color_map.items():
            df = merged[merged["Classification"] == modality].copy()
            df["CS_Enrollment"] = df["CS_Enrollment"].apply(
                lambda x: int(x) if pd.notnull(x) else 0)
            df["Certified_Teachers"] = df["Certified_Teachers"].apply(
                lambda x: int(x) if pd.notnull(x) else 0)

            df["student_teacher_ratio"] = df.apply(
                lambda row: row["CS_Enrollment"] / row["Certified_Teachers"]
                if row["Certified_Teachers"] not in [0, None, "", float('nan')] else 0.0,
                axis=1
            )

            from data_dashboard.data_loader import ratio_fmt, build_modality_hover
            df["ratio_display"] = df["student_teacher_ratio"].apply(ratio_fmt)
            df["school_hover"] = df.apply(lambda row: build_modality_hover(
                row, modality_type, HOVER_TEMPLATES), axis=1)
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
                    customdata=df[["school_hover", "UNIQUESCHOOLID"]].values
                ))
                # Gray center
                fig.add_trace(go.Scattermapbox(
                    lon=df["lon"], lat=df["lat"],
                    mode="markers", marker=dict(size=9, color=color, opacity=1, symbol=marker_symbol),
                    name="",
                    visible=True,
                    showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["school_hover", "UNIQUESCHOOLID"]].values
                ))
            else:
                fig.add_trace(go.Scattermapbox(
                    lon=df["lon"], lat=df["lat"],
                    mode="markers", marker=dict(size=9, color=color, opacity=1, symbol=marker_symbol),
                    name="",
                    visible=True,
                    showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["school_hover", "UNIQUESCHOOLID"]].values
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
            "Total Student Count", "Female", "Male"
        ]].copy()
        disparity = data_loader.SCHOOLDATA["disparity"]
        schools = schools.merge(disparity, on="UNIQUESCHOOLID", how="inner")
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

        from data_dashboard.data_loader import make_ri_hover

        # Parity bin (i=2) - outlined dots: black (outline) then white (center)
        i_parity = 2
        color = RI_BIN_COLORS[i_parity]
        label = bin_labels[i_parity]
        df = schools[schools['RI_bin'] == i_parity].copy()
        if not df.empty:
            df["ri_hover"] = df.apply(lambda row: make_ri_hover(
                row, disparity_col, ri_cols, HOVER_TEMPLATES), axis=1)
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
                customdata=df[["ri_hover", "UNIQUESCHOOLID"]].values
            ))
        # Other bins
        for i in [0, 1, 3, 4]:
            color = RI_BIN_COLORS[i]
            label = bin_labels[i]
            df = schools[schools['RI_bin'] == i].copy()
            if not df.empty:
                df["ri_hover"] = df.apply(lambda row: make_ri_hover(
                    row, disparity_col, ri_cols, HOVER_TEMPLATES), axis=1)
                fig.add_trace(go.Scattermapbox(
                    lon=df['lon'], lat=df['lat'],
                    mode='markers', marker=dict(size=9, color=color, opacity=1),
                    name="", visible=True, showlegend=False,
                    hovertemplate="%{customdata[0]}",
                    customdata=df[["ri_hover", "UNIQUESCHOOLID"]].values
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
        mapbox_zoom=6.5,
        mapbox_center={"lat": 32.9, "lon": -83.5},
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="white",
        plot_bgcolor="white",
        dragmode="pan"
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

    legend_combined = None
    if legend_html and overlay_legend:
        legend_combined = [
            html.Div(legend_html, className="legend-flex-8"),
            html.Div(overlay_legend, className="legend-flex-2")
        ]
    elif legend_html:
        legend_combined = [
            html.Div(legend_html, className="legend-full-width")]
    elif overlay_legend:
        legend_combined = [
            html.Div(overlay_legend, className="legend-full-width")]
    else:
        legend_combined = None
    return fig, legend_combined


@callback(
    Output("loading-message", "children"),
    [
        Input("map-options-toggle", "value"),
        Input("school-toggles", "value"),
        Input("dots-dropdown", "value"),
        Input("underlay-dropdown", "value"),
    ]
)
def update_loading_message(map_options, school, dots_dropdown, underlay_dropdown):
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
    if underlay_dropdown != DEFAULT_UNDERLAY_OPTION:
        components.append(html.Br())
        components.append(
            html.Div("This might take a minute...", style={"textAlign": "center"}))
    if not components:
        components.append("Loading map")
    return components


@callback(
    Output("course-list", "children"),
    Input("main-map", "hoverData")
)
def update_course_list(hoverData):
    if hoverData is None or not hoverData.get('points'):
        # Show full list with [0] in red
        course_items = []
        for course in APPROVED_COURSES:
            course_items.append(
                html.Li([html.Span("[0] ", style={"color": "red"}), course.title()]))
        return html.Div([html.Strong("Offered Courses:"), html.Ul(course_items)])

    point = hoverData['points'][0]
    if 'customdata' not in point or len(point['customdata']) < 2:
        return html.Div("No course data available.")

    school_id = str(point['customdata'][1])
    school_name = data_loader.SCHOOLDATA["school_names"].get(
        school_id, f"School {school_id}")

    courses_counts = data_loader.SCHOOLDATA["courses"].get(school_id, {})

    course_items = []
    for course in APPROVED_COURSES:
        count = courses_counts.get(course, 0)
        count_str = f"[{count}] "
        style = {"font-weight": "bold"} if count > 0 else {"color": "red"}
        course_items.append(
            html.Li([html.Span(count_str, style=style), course.title()]))

    return html.Div([html.Strong(f"Courses at {school_name}:"), html.Ul(course_items)])
