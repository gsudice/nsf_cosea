from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import folium
from folium import plugins
import os
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
SERVER = os.getenv("SERVER")
DATABASE = os.getenv("DATABASE")
PORT = "5432"

app = Flask(__name__)

# Database connection setup
try:
    db_connection_url = f"postgresql://{USERNAME}:{PASSWORD}@{SERVER}/{DATABASE}"
    engine = create_engine(db_connection_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Successfully connected to database")
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    engine = None

@app.route("/")
def home():
    return render_template('home.html')

#Fetching districts for the selection page
@app.route("/district")
def district():
    try:
        with engine.connect() as connection:
            districts_query = text("""
                SELECT DISTINCT nmcnty 
                FROM (
                    SELECT nmcnty 
                    FROM nces_schools.publicschools 
                    WHERE state = 'GA'
                    UNION
                    SELECT nmcnty 
                    FROM nces_schools.privateschools 
                    WHERE state = 'GA'
                ) AS combined_districts
                ORDER BY nmcnty
            """)
            districts = [row[0] for row in connection.execute(districts_query).fetchall()]
            return render_template('district.html', districts=districts)
    except Exception as e:
        logger.error(f"Error fetching districts: {e}")
        return render_template('district.html', error_message="Error fetching districts")

#Fetching schools upon district selection
@app.route("/get_schools")
def get_schools():
    district = request.args.get('district')
    try:
        with engine.connect() as connection:
            schools_query = text("""
                SELECT name 
                FROM (
                    SELECT name 
                    FROM nces_schools.publicschools 
                    WHERE state = 'GA' AND nmcnty = :district
                    UNION
                    SELECT name 
                    FROM nces_schools.privateschools 
                    WHERE state = 'GA' AND nmcnty = :district
                ) AS combined_schools
                ORDER BY name
            """)
            schools = [row[0] for row in connection.execute(schools_query, {"district": district}).fetchall()]
            return jsonify(schools)
    except Exception as e:
        logger.error(f"Error fetching schools: {e}")
        return jsonify([])

def get_block_groups(latitude, longitude, radius_miles=3):
    """Fetch block groups within a radius using Georgia State Plane East projection"""
    radius_feet = radius_miles * 5280  # Convert miles to feet
    
    logger.debug(f"Fetching block groups for: lat={latitude}, lon={longitude}, radius={radius_miles} miles")
    
    query = text("""
    WITH point_geom AS (
        SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 2239) as geom
    )
    SELECT 
        bg.geoid,
        ST_AsGeoJSON(ST_Transform(bg.geom, 4326))::json as geometry,
        bg.statefp,
        bg.countyfp,
        bg.tractce,
        bg.blkgrpce
    FROM uscensus_tigerline_2023.blockgroups bg
    CROSS JOIN point_geom
    WHERE bg.statefp = '13'  -- Georgia's FIPS code
    AND ST_DWithin(
        ST_Transform(bg.geom, 2239),
        point_geom.geom,
        :radius
    );
    """)
    
    try:
        with engine.connect() as conn:
            # Execute the main query
            logger.debug("Executing block groups query...")
            result = conn.execute(query, {
                "lat": latitude,
                "lon": longitude,
                "radius": radius_feet
            })
            
            # Explicitly create dictionaries with the correct keys
            rows = []
            for row in result:
                block_dict = {
                    'geoid': row.geoid,
                    'geometry': row.geometry,
                    'statefp': row.statefp,
                    'countyfp': row.countyfp,
                    'tractce': row.tractce,
                    'blkgrpce': row.blkgrpce
                }
                rows.append(block_dict)
            
            logger.debug(f"Found {len(rows)} block groups")
            if rows:
                logger.debug(f"Sample block group data: {rows[0]['geoid']}")
                logger.debug(f"Sample geometry: {rows[0]['geometry']}")
            
            return rows
            
    except Exception as e:
        logger.error(f"Error in get_block_groups: {str(e)}")
        return []

@app.route("/select", methods=["GET", "POST"])
def render_select():
    if request.method == "POST":
        selected_district = request.form.get('district')
        selected_school = request.form.get('school')
        
        logger.debug(f"Selected district: {selected_district}")
        logger.debug(f"Selected school: {selected_school}")
        
        if not engine:
            logger.error("Database connection is not available")
            return render_template('select.html', error_message="Database connection is not available.")

        try:
            with engine.connect() as connection:
                query_location = text("""
                    SELECT lat, lon
                    FROM (
                        SELECT lat, lon
                        FROM nces_schools.publicschools
                        WHERE state = 'GA' AND nmcnty = :district AND name = :school
                        UNION ALL
                        SELECT lat, lon
                        FROM nces_schools.privateschools
                        WHERE state = 'GA' AND nmcnty = :district AND name = :school
                    ) AS combined_schools
                    LIMIT 1
                """)
                
                result = connection.execute(query_location, {
                    "district": selected_district, 
                    "school": selected_school
                }).fetchone()

                if not result or result[0] is None or result[1] is None:
                    return render_template(
                        'select.html',
                        error_message="School location not found."
                    )

                latitude, longitude = result

                logger.debug(f"School coordinates: lat={latitude}, lon={longitude}")

                #  TAI : CHANGE THIS (approximately 3 miles)
                lat_offset = 3/69.0
                lon_offset = 3/55.0
                
                bounds = [
                    [latitude - lat_offset, longitude - lon_offset],
                    [latitude + lat_offset, longitude + lon_offset]
                ]

                # Create the map
                m = folium.Map(
                    location=[latitude, longitude],
                    zoom_start=18,
                    tiles='OpenStreetMap',
                    min_zoom=12,
                    max_zoom=16
                )
                
                # Create a mask for areas outside the boundary
                #COMMENTED OUT PER DR TIWARI SUGGESTION.
                # mask_coordinates = [
                #     [[90, -180],
                #      [90, 180],
                #      [-90, 180],
                #      [-90, -180]],  # Outer ring (whole world)
                #     [[bounds[0][0], bounds[0][1]],
                #      [bounds[0][0], bounds[1][1]],
                #      [bounds[1][0], bounds[1][1]],
                #      [bounds[1][0], bounds[0][1]]]  # Inner ring (boundary box)
                # ]

                # Add the mask as a polygon
                # folium.Polygon(
                #     locations=mask_coordinates,
                #     color='white',
                #     fill=True,
                #     fill_color='white',
                #     fill_opacity=1,
                #     weight=0
                # ).add_to(m)

                # Add school marker
                folium.Marker(
                    [latitude, longitude],
                    popup=selected_school,
                    icon=folium.Icon(color='red', icon='info-sign')
                ).add_to(m)

                # Get and add block groups
                block_groups = get_block_groups(latitude, longitude)
                logger.debug(f"Retrieved {len(block_groups)} block groups")
                
                if block_groups:
                    blocks_layer = folium.FeatureGroup(name='Block Groups')
                    
                    for block in block_groups:
                        try:
                            # Log the geometry type and coordinates for the first block
                            if block == block_groups[0]:
                                logger.debug(f"First block geometry: {block['geometry']}")
                            
                            folium.GeoJson(
                                {
                                    'type': 'Feature',
                                    'geometry': block['geometry'],
                                    'properties': {
                                        'geoid': block['geoid'],
                                        'tract': block['tractce'],
                                        'block_group': block['blkgrpce']
                                    }
                                },
                                style_function=lambda x: {
                                    'fillColor': '#ffcccb',
                                    'color': '#000000',
                                    'weight': 1,
                                    'fillOpacity': 0.3
                                },
                                highlight_function=lambda x: {
                                    'fillColor': '#ff0000',
                                    'color': '#000000',
                                    'weight': 2,
                                    'fillOpacity': 0.5
                                },
                                # @TIFFANY possibly look at this for the selection of reason popup.
                                popup=folium.Popup(
                                    f"""
                                    <div style="font-family: Arial, sans-serif; padding: 10px;">
                                        <h4 style="margin: 0 0 10px 0;">Census Block Group</h4>
                                        <p style="margin: 5px 0;"><b>GEOID:</b> {block['geoid']}</p>
                                        <p style="margin: 5px 0;"><b>Tract:</b> {block['tractce']}</p>
                                        <p style="margin: 5px 0;"><b>Block Group:</b> {block['blkgrpce']}</p>
                                    </div>
                                    """,
                                    min_width=200,
                                    max_width=300
                                )
                            ).add_to(blocks_layer)
                        except Exception as e:
                            logger.error(f"Error adding block to map: {str(e)}")
                            continue
                    
                    blocks_layer.add_to(m)
                else:
                    logger.warning("No block groups found for the given coordinates")

                # Add boundary rectangle
                folium.Rectangle(
                    bounds=bounds,
                    color='blue',
                    weight=2,
                    fill=False,
                ).add_to(m)

                # Set map bounds
                m.fit_bounds(bounds)
                m.options['maxBounds'] = bounds
                m.options['maxBoundsViscosity'] = 1.0

                # Add custom CSS to ensure the mask works properly
                # custom_css = """
                # <style>
                #     .leaflet-container {
                #         background-color: white !important;
                #     }
                # </style>
                # """

                # Inject custom CSS into the map HTML
                map_html = m._repr_html_()
                # map_html = custom_css + map_html

                return render_template(
                    'select.html',
                    map_html=map_html,
                    selected_district=selected_district,
                    selected_school=selected_school
                )

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return render_template(
                'select.html',
                error_message=f"Error retrieving data: {str(e)}"
            )

    return render_template('select.html')

if __name__ == '__main__':
    app.run(debug=True)