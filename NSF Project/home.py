from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import folium
from folium import plugins
import os
import logging
import json  # Added missing import

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

# Fetching districts for the selection page
@app.route("/district")
def district():
    try:
        with engine.connect() as connection:
            districts_query = text("""
                SELECT DISTINCT "SYSTEM_NAME" 
                FROM "2024".tbl_approvedschools 
                ORDER BY "SYSTEM_NAME"
            """)
            districts = [row[0] for row in connection.execute(districts_query).fetchall()]
            return render_template('district.html', districts=districts)
    except Exception as e:
        logger.error(f"Error fetching districts: {e}")
        return render_template('district.html', error_message="Error fetching districts")

# Fetching schools upon district selection
@app.route("/get_schools")
def get_schools():
    district = request.args.get('district')
    try:
        with engine.connect() as connection:
            schools_query = text("""
                SELECT "SCHOOL_NAME" 
                FROM "2024".tbl_approvedschools 
                WHERE "SYSTEM_NAME" = :district
                ORDER BY "SCHOOL_NAME"
            """)
            schools = [row[0] for row in connection.execute(schools_query, {"district": district}).fetchall()]
            return jsonify(schools)
    except Exception as e:
        logger.error(f"Error fetching schools: {e}")
        return jsonify([])
    
@app.route("/get_school_id")
def get_school_id():
    school_name = request.args.get('school_name')
    district = request.args.get('district')
    try:
        with engine.connect() as connection:
            school_id_query = text("""
                SELECT "UNIQUESCHOOLID"
                FROM "2024".tbl_approvedschools 
                WHERE "SCHOOL_NAME" = :school_name 
                AND "SYSTEM_NAME" = :district
            """)
            school_id = connection.execute(school_id_query, {"school_name": school_name, "district": district}).fetchone()
            if school_id:
                return jsonify({"UNIQUESCHOOLID": school_id[0]})
            else:
                return jsonify({"error": "School not found"})
    except Exception as e:
        logger.error(f"Error fetching school ID: {e}")
        return jsonify({"error": "Error fetching school ID"})

# Function to retrieve block groups for the given school
def get_block_groups(school_id):
    try:
        with engine.connect() as connection:
            block_groups_query = text("""
                SELECT 
                    ST_AsGeoJSON(ST_Transform(cbgpolygeom, 4326))::json AS geometry
                FROM "2024".tbl_cbg_finalassignment
                WHERE "UNIQUESCHOOLID" = :school_id
            """)
            result = connection.execute(block_groups_query, {"school_id": school_id}).fetchall()
            
            if result:
                block_groups = []
                for row in result:
                    block_groups.append({
                        "geometry": row.geometry,
                    })
                return block_groups
            else:
                return []
    except Exception as e:
        logger.error(f"Error fetching block groups: {str(e)}")
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
                    SELECT lon, lat, "UNIQUESCHOOLID"
                    FROM "2024".tbl_approvedschools
                    WHERE "SYSTEM_NAME" = :district AND "SCHOOL_NAME" = :school
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

                longitude, latitude, school_id = result

                logger.debug(f"School coordinates: lat={latitude}, lon={longitude}")

                # Create the map
                m = folium.Map(
                    location=[latitude, longitude],
                    zoom_start=12,
                    tiles='OpenStreetMap'
                )
                
                # Add school marker
                folium.Marker(
                    [latitude, longitude],
                    popup=selected_school,
                    icon=folium.Icon(color='red', icon='info-sign')
                ).add_to(m)

                # Get and add block groups
                block_groups = get_block_groups(school_id)
                logger.debug(f"Retrieved {len(block_groups)} block groups")
               
                if block_groups:
                    blocks_layer = folium.FeatureGroup(name='Block Groups')
                    
                    for block in block_groups:
                        try:
                            # Ensure geometry is a valid GeoJSON
                            if not block.get('geometry'):
                                logger.warning(f"Skipping block group with no geometry: {block}")
                                continue

                            popUp_html = render_template("popUp.html", block={
                                "geoid": block.get("geoid", "N/A"),
                                "tractce": block.get("tractce", "N/A"),
                                "blkgrpce": block.get("blkgrpce", "N/A")
                            })
                            
                            iframe = folium.IFrame(popUp_html, width=300, height=200)
                            popup = folium.Popup(iframe, min_width=200, max_width=300)
                            
                            folium.GeoJson(
                                block['geometry'],
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
                                popup=popup
                            ).add_to(blocks_layer)
                        except Exception as e:
                            logger.error(f"Error adding block to map: {str(e)}")
                            continue
                    
                    blocks_layer.add_to(m)
                else:
                    logger.warning("No block groups found for the given school")

                # Inject custom CSS into the map HTML
                map_html = m._repr_html_()
               
                return render_template(
                    'select.html',
                    instructions=render_template("selectInstructions.html"),
                    map_html=map_html,
                    selected_district=selected_district,
                    selected_school=selected_school
                )

        except Exception as e:
            logger.error(f"Error fetching school data: {str(e)}")
            return render_template('select.html', error_message="Error fetching school data")
    
    return render_template('select.html')

if __name__ == "__main__":
    app.run(debug=True)