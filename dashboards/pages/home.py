import dash
from dash import html, dcc

dash.register_page(__name__, path='/', order=0)


def build_tool_row(title, image_src, image_alt, description, href, reverse=False, featured=False, tags=None):
    row_class = "tool-row tool-row-reverse" if reverse else "tool-row"
    tags = tags or []

    media_children = []
    media_children.append(html.Img(
        src=image_src,
        alt=image_alt,
        className="tool-row-image"
    ))

    content_children = [
        html.H3(title, className="tool-row-title"),
        html.P(description, className="tool-row-desc"),
    ]
    content_children.append(html.Div("Open tool", className="tool-row-cta"))

    card_children = []
    if featured:
        card_children.append(
            html.Div("New!", className="home-eyebrow tool-row-eyebrow"))
    card_children.append(html.Div([
        html.Div(media_children, className="tool-row-media"),
        html.Div(content_children, className="tool-row-content"),
    ], className=row_class))
    if tags:
        card_children.append(html.Div([
            html.Span(tag, className="tool-row-tag") for tag in tags
        ], className="tool-row-tags"))

    outer_classes = "tool-row-card"
    if featured:
        outer_classes += " attention-glow"

    return dcc.Link(
        html.Div(card_children, className=outer_classes),
        href=href,
        className="tool-link",
        style={"textDecoration": "none", "color": "inherit"}
    )


def build_help_video_card(title, description, label="Coming soon"):
    return html.Div([
        html.Div([
            html.Video(
                src="/assets/demo-subs.mp4",
                controls=True,
                preload="metadata",
                className="help-video-player",
                title=title,
            ),
            html.Div(label, className="help-video-badge"),
        ], className="help-video-preview"),
        html.Div([
            html.H3(title, className="help-video-title"),
            html.P(description, className="help-video-desc"),
        ], className="help-video-content"),
    ], className="help-video-card")


def build_help_faq_item(title, body):
    if isinstance(body, list):
        body_children = body
    else:
        body_children = [html.P(body)]

    return html.Div([
        html.H3(title, className="help-faq-title"),
        html.Div(body_children, className="help-faq-body"),
    ], className="help-faq-item")


def build_help_details(summary_title, summary_text, content_children, section_class):
    summary_children = [
        html.Div(summary_title, className="help-summary-title")]
    if summary_text:
        summary_children.append(
            html.Div(summary_text, className="help-summary-text"))

    return html.Details(
        [
            html.Summary(summary_children, className="help-summary"),
            html.Div(content_children, className=section_class),
        ],
        className="help-details",
    )


layout = html.Div([
    html.Div([
        html.P(
            "Choose a tool below to explore Georgia computer science education data through interactive dashboards and visualizations.",
            className="home-intro"
        ),
        html.Div([
            build_tool_row(
                title="CS Enrollment Data Dashboard",
                image_src="/assets/images/dataDashboardImg.png",
                image_alt="Data Dashboard visualization",
                description="Explore computer science enrollment and demographics at the school and district level. Visualize participation rates, course offerings, and demographic breakdowns across Georgia schools.",
                href="/data-dashboard",
                reverse=False,
                featured=True,
                tags=["School-level CS access",
                      "Course offerings", "Course delivery modes", "Geography-aware analysis"],
            ),
            # build_tool_row(
            #     title="Location Modeling",
            #     image_src="https://via.placeholder.com/400x200/0071ce/ffffff?text=Location+Modeling",
            #     image_alt="Location Modeling visualization",
            #     description="Analyze geographic and socioeconomic factors affecting CS education access. Examine how location, income, and community characteristics influence computer science opportunities.",
            #     href="/location-modeling",
            #     reverse=True,
            # ),
        ], className="tools-section"),
        html.Div([
            build_help_details(
                summary_title="Walkthrough",
                summary_text="",
                content_children=[
                    html.Div([
                        build_help_video_card(
                            title="Dashboard walkthrough video",
                            description="A short walkthrough video shows how to explore schools, filters, and access patterns in the dashboard. Use the player controls to view it and open fullscreen.",
                            label="Demo video",
                        ),
                    ], className="help-video-grid"),
                ],
                section_class="help-section help-section-collapsible"
            ),
            build_help_details(
                summary_title="FAQ",
                summary_text="",
                content_children=[
                    html.Div([
                        build_help_faq_item(
                            "What does '< 5' mean?",
                            "When you see '< 5' instead of a number, it means the value is between 1 and 4. We suppress these small numbers to protect student privacy and prevent identification of individual students. In some places, you may also see 'Suppressed' for a total when one or more of the parts used to make that total are too small to show safely."
                        ),
                        build_help_faq_item(
                            "What does 'Suppressed' mean?",
                            "'Suppressed' means the total cannot be shown because it would reveal a small count or could be worked back to a small count. This is done to protect student privacy, so the dashboard hides the value instead of showing a number that could identify individual students."
                        ),
                        build_help_faq_item(
                            "What are Course Modalities?",
                            "Course modality indicates how CS courses are offered at the school: In Person Only, Virtual Only, Both In Person and Virtual, or No approved CS classes. Virtual courses may be delivered fully online, through online modules, or in a hybrid setup such as a partnership with a local university or another approved instructional provider."
                        ),
                        build_help_faq_item(
                            "What is the Representation Index (RI)?",
                            "The RI shows how well different groups are represented in CS courses compared to their overall school population. Values between -0.05 and 0.05 indicate parity (balanced representation). Negative values mean under-representation in CS, while positive values mean over-representation."
                        ),
                        build_help_faq_item(
                            "What are Extra Certified Teachers?",
                            "These are teachers who are certified to teach CS but do not currently teach a CS course listed in the Courses Offered section. They represent potential CS teaching capacity at the school."
                        ),
                        build_help_faq_item(
                            "How is the Student-to-CS-Teacher Ratio calculated?",
                            "This ratio is calculated as Total Student Count divided by the sum of approved CS teachers and extra certified teachers at the school. It helps indicate how many students each CS teacher potentially serves."
                        ),
                        build_help_faq_item(
                            "What is Course Total Offered?",
                            "This is the number of distinct approved CS courses offered at a school. A course is counted if it is offered either virtually or in-person (or both)."
                        ),
                        build_help_faq_item(
                            "How does the Courses Offered filter work?",
                            [
                                html.P(
                                    "The courses listed are the approved CS courses at each school, based on Georgia State Bill 108. Select one or more courses and choose a filter mode:"),
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
                            ]
                        ),
                        build_help_faq_item(
                            "Where does the data come from?",
                            html.Ul([
                                html.Li([
                                    html.Strong(
                                        "Georgia Department of Education (GaDOE)"),
                                    ": School-level enrollment and CS course demographics. ",
                                    html.A("Data Requests", href="https://georgiainsights.gadoe.org/contact-request-data/",
                                           target="_blank", rel="noopener noreferrer")
                                ]),
                                html.Li([
                                    html.Strong(
                                        "National Center for Education Statistics (NCES)"),
                                    ": District characteristics and locale classifications. ",
                                    html.A("DataLab", href="https://nces.ed.gov/datalab/",
                                           target="_blank", rel="noopener noreferrer")
                                ]),
                                html.Li([
                                    html.Strong("U.S. Census Bureau"),
                                    ": Demographic, income, and educational data from the ",
                                    html.A("American Community Survey", href="https://www.census.gov/programs-surveys/acs.html",
                                           target="_blank", rel="noopener noreferrer"),
                                    " and geographic boundaries from ",
                                    html.A("TIGER/Line shapefiles", href="https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
                                           target="_blank", rel="noopener noreferrer")
                                ])
                            ])
                        ),
                        build_help_faq_item(
                            "Important Notice",
                            "CS enrollment numbers shown are estimates. Students may be enrolled in multiple CS courses, and we currently have no way to eliminate duplicates across courses. Therefore, CS enrollment counts may include the same student more than once."
                        ),
                    ], className="help-faq-grid"),
                ],
                section_class="help-faq-section help-section-collapsible"
            ),
        ], className="home-collapsible-stack"),
    ], id="home-container", className="home-container")
])
