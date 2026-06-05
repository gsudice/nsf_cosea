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
    use_pages=True
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
        )
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
    print(f"[app] Served CBG underlay geojson for {field} in {time.perf_counter() - start_time:.2f}s", flush=True)
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
