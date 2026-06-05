import dash
from dash import Dash, html, dcc, Input, Output
import os
from argparse import ArgumentParser
from flask_caching import Cache
from flask import Response
import json
import time

import data_dashboard.data_loader as data_loader


app = Dash(
    __name__,
    use_pages=True,
    assets_folder=os.path.join(os.path.dirname(__file__), "assets"),
    assets_url_path="assets",
    title="Who Has Access to and Who Participates in Computer Science Across Georgia? A Data Dashboard for Action",
    update_title="Loading...",
    meta_tags=[
        {
            "name": "description",
            "content": "Explore which Georgia schools offer computer science courses, how participation compares to enrollment, where teacher capacity may limit access, and how patterns differ across rural, town, suburban, and city schools.",
        },
        {
            "name": "keywords",
            "content": "Georgia computer science dashboard, school-level CS access, CS enrollment trends, CS participation, course offerings, teacher capacity, geography-aware analysis, school demographics, access gaps, rural schools, town schools, suburban schools, city schools, equity in computing, school data visualization",
        },
    ]
)

# Configure filesystem-based caching for server deployment
# Cache clears on restart, so long timeout is fine for static data
cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': 'cache',
    'CACHE_DEFAULT_TIMEOUT': 7200,  # 2 hours (clears on restart anyway)
    'CACHE_THRESHOLD': 3000  # Maximum number of cached filter combinations
})


page_options = [
    {"label": p["name"], "value": p["relative_path"]}
    for p in sorted(dash.page_registry.values(), key=lambda x: x["order"])
]


app.layout = html.Div([
    dcc.Location(id="url"),

    html.Div(className="header", children=[
        html.H1(
            dcc.Dropdown(
                id="page-dropdown",
                options=page_options,
                clearable=False,
                value="/",
                className="dropdown-header"
            )
        ),
        html.Div(className="header-logo-group", children=[
            html.A(
                html.Img(src="/assets/images/gsulogo.jpg",
                         className="header-logo-image header-logo-gsu", alt="Georgia State University logo"),
                href="https://csds.gsu.edu/",
                target="_blank",
                rel="noopener noreferrer",
                title="Georgia State University"
            ),
            html.A(
                html.Img(src="/assets/images/chailogo.png", className="header-logo-image header-logo-chai",
                         alt="CS Higher-level Alliance Institute logo"),
                href="https://chai.gsu.edu/",
                target="_blank",
                rel="noopener noreferrer",
                title="CS Higher-level Alliance Institute"
            ),
            html.Div(
                className="header-logo-placeholder header-logo-placeholder-last"),
        ]),
    ]),

    html.Div(id="app-container", children=[
        dash.page_container
    ])
])


@app.server.route("/cbg-underlay/<field>")
def cbg_underlay_geojson(field):
    start_time = time.perf_counter()
    print(f"[app] Serving CBG underlay geojson for {field}...", flush=True)
    field_data = data_loader.get_cbg_underlay(field)

    response = Response(
        json.dumps(field_data.get("geojson", {}), separators=(",", ":")),
        mimetype="application/json"
    )
    response.headers["Cache-Control"] = "public, max-age=86400"
    print(
        f"[app] Served CBG underlay geojson for {field} in {time.perf_counter() - start_time:.2f}s", flush=True)
    return response


@app.callback(
    Output("url", "pathname"),
    Output("page-dropdown", "value"),
    Input("page-dropdown", "value"),
    Input("url", "pathname"),
)
def sync_dropdown(drop_value, pathname):
    ctx = dash.callback_context

    if ctx.triggered_id == "url":
        return pathname, pathname

    if ctx.triggered_id == "page-dropdown":
        return drop_value, drop_value

    return pathname, pathname


if __name__ == "__main__":
    parser = ArgumentParser(
        prog='Dashboard',
        description='Dashboard for the NSF COSEA project.'
    )
    parser.add_argument('--hostname', default='localhost')
    parser.add_argument('--port', default='8050')
    args = parser.parse_args()

    app.run(debug=False, host=args.hostname, port=int(args.port))
