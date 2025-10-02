import dash
from dash import html, dcc

dash.register_page(__name__, path='/', order=0)

layout = html.Div([
    html.Div([
        html.H1("NSF COSEA Dashboard", className="home-title"),
        html.P(
            "Explore computer science education data in Georgia through interactive tools and visualizations. "
            "Access data dashboards for enrollment analysis and location modeling for geographic insights, "
            "all powered by comprehensive data from state and federal education sources.",
            className="home-intro"
        ),
        html.H2("Available Tools", className="home-section-title"),
        html.Div([
            dcc.Link([
                html.Div([
                    html.H3("Data Dashboard", className="tool-title"),
                    html.Img(
                        src="/assets/images/dataDashboardImg.png",
                        alt="Data Dashboard visualization",
                        className="tool-gif"
                    ),
                    html.P(
                        "Explore computer science enrollment and demographics at the school and district level. "
                        "Visualize participation rates, course offerings, and demographic breakdowns across Georgia schools.",
                        className="tool-desc"
                    ),
                ], className="tool-block")
            ], href="/data-dashboard", style={"textDecoration": "none", "color": "inherit"}),
            # dcc.Link([
            #     html.Div([
            #         html.H3("Location Modeling", className="tool-title"),
            #         html.Img(
            #             src="https://via.placeholder.com/400x200/0071ce/ffffff?text=Location+Modeling",
            #             alt="Location Modeling visualization",
            #             className="tool-gif"
            #         ),
            #         html.P(
            #             "Analyze geographic and socioeconomic factors affecting CS education access. "
            #             "Examine how location, income, and community characteristics influence computer science opportunities.",
            #             className="tool-desc"
            #         ),
            #     ], className="tool-block")
            # ], href="/location-modeling", style={"textDecoration": "none", "color": "inherit"}),
        ], className="tools-section"),

        html.Div([
            html.H3("Data Sources", className="tool-title"),
            html.Ul([
                html.Li([
                    html.Strong("Georgia Department of Education (GaDOE)"),
                    ": School-level enrollment and CS course demographics. ",
                    html.A("Data Requests", href="https://georgiainsights.gadoe.org/contact-request-data/",
                           target="_blank", style={"color": "#0071ce"})
                ]),
                html.Li([
                    html.Strong(
                        "National Center for Education Statistics (NCES)"),
                    ": District characteristics and locale classifications. ",
                    html.A("DataLab", href="https://nces.ed.gov/datalab/",
                           target="_blank", style={"color": "#0071ce"})
                ]),
                html.Li([
                    html.Strong("U.S. Census Bureau"),
                    ": Demographic, income, and educational data from the ",
                    html.A("American Community Survey", href="https://www.census.gov/programs-surveys/acs.html",
                           target="_blank", style={"color": "#0071ce"}),
                    " and geographic boundaries from ",
                    html.A("TIGER/Line shapefiles", href="https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
                           target="_blank", style={"color": "#0071ce"})
                ])
            ], className="tool-desc", style={"textAlign": "left", "marginBottom": "0"})
        ], className="tool-block data-sources"),

        html.Div("© who should we copyright?", className="home-footer")
    ], id="home-container", className="home-container")
])
