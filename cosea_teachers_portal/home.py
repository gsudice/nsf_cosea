from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import folium
from folium import plugins
import os
import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

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
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-this")
CORS(app)

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

# NEW: Role selection route
@app.route("/role_selection", methods=["GET", "POST"])
def role_selection():
    if request.method == "POST":
        role = request.form.get('role')
        
        # Store role information in session
        session['role'] = role
        
        if role == 'teacher':
            subjects = request.form.getlist('subjects')
            if not subjects:
                return render_template('role_selection.html', 
                                     error_message="Please select at least one subject.")
            session['subjects'] = subjects
            session.pop('admin_level', None)  # Clear admin data if exists
            
        elif role == 'administrator':
            admin_level = request.form.get('admin_level')
            if not admin_level:
                return render_template('role_selection.html',
                                     error_message="Please select your administrative level.")
            session['admin_level'] = admin_level
            session.pop('subjects', None)  # Clear teacher data if exists
        
        logger.info(f"User role saved: {role}")
        logger.info(f"Session data: {dict(session)}")
        
        # Redirect to district selection
        return redirect(url_for('district'))
    
    return render_template('role_selection.html')

# Fetching districts for the selection page
@app.route("/district")
def district():
    # Check if user has completed role selection
    if 'role' not in session:
        logger.warning("User attempted to access district page without role selection")
        return redirect(url_for('role_selection'))
    
    try:
        with engine.connect() as connection:
            districts_query = text("""
                SELECT DISTINCT "SYSTEM_NAME" 
                FROM "allhsgrades24".tbl_approvedschools 
                ORDER BY "SYSTEM_NAME"
            """)
            districts = [row[0] for row in connection.execute(districts_query).fetchall()]
            
            # Pass user info to template
            user_info = {
                'role': session.get('role'),
                'subjects': session.get('subjects'),
                'admin_level': session.get('admin_level')
            }
            
            return render_template('district.html', districts=districts, user_info=user_info)
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
                FROM "allhsgrades24".tbl_approvedschools 
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
                FROM "allhsgrades24".tbl_approvedschools 
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
                    ST_AsGeoJSON(ST_Transform(cbgpolygeom, 4326))::json AS geometry, "GEOID" AS "geoid"
                FROM "allhsgrades24".tbl_cbg_finalassignment
                WHERE "UNIQUESCHOOLID" = :school_id
            """)
            result = connection.execute(block_groups_query, {"school_id": school_id}).fetchall()
            
            if result:
                block_groups = []
                for row in result:
                    block_groups.append({
                        "geometry": row.geometry,
                        "geoid": row.geoid
                    })
                return block_groups
            else:
                return []
    except Exception as e:
        logger.error(f"Error fetching block groups: {e}")
        return []

@app.route("/select", methods=["GET", "POST"])
def render_select():
    # Check if user has completed role selection
    if 'role' not in session:
        logger.warning("User attempted to access select page without role selection")
        return redirect(url_for('role_selection'))
    
    if request.method == "POST":
        selected_district = request.form.get('district')
        selected_school = request.form.get('school')
        
        # Store selections in session
        session['selected_district'] = selected_district
        session['selected_school'] = selected_school
        
        logger.debug(f"Selected district: {selected_district}")
        logger.debug(f"Selected school: {selected_school}")
        
        if not engine:
            logger.error("Database connection is not available")
            return render_template('select.html', error_message="Database connection is not available.")

        try:
            with engine.connect() as connection:
                query_location = text("""
                    SELECT lon, lat, "UNIQUESCHOOLID"
                    FROM "allhsgrades24".tbl_approvedschools
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
                    district_name = str(selected_district)
                    school_name = str(selected_school)

                    # Get user info from session
                    user_info = {
                        'role': session.get('role', 'unknown'),
                        'subjects': ','.join(session.get('subjects', [])) if session.get('role') == 'teacher' else None,
                        'admin_level': session.get('admin_level') if session.get('role') == 'administrator' else None
                    }
                    
                    logger.debug(f"Session data: {dict(session)}")
                    logger.debug(f"User info being passed to popup: {user_info}")
                    
                    for block in block_groups:
                        try:
                            if not block.get('geometry'):
                                logger.warning(f"Skipping block group with no geometry: {block}")
                                continue
                            
                            popUp_html = render_template("popUp.html", 
                                block=block,
                                selected_school=school_name,
                                selected_district=district_name,
                                user_info=user_info
                            )

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

                map_html = m._repr_html_()
               
                return render_template(
                    'select.html',
                    instructions=render_template("selectInstructions.html"),
                    map_html=map_html,
                    selected_district=selected_district,
                    selected_school=school_name
                )

        except Exception as e:
            logger.error(f"Error fetching school data: {str(e)}")
            return render_template('select.html', error_message="Error fetching school data")
    
    return render_template('select.html')

@app.route("/saveData", methods=["POST"])
def submit_barriers():
    try:
        logger.debug("=== SAVEDATA ENDPOINT CALLED ===")
        logger.debug(f"Form data received: {dict(request.form)}")
        
        # Get form data
        school_name = request.form.get('school')
        district = request.form.get('district')
        block_geoid = request.form.get('block_geoid')
        barriers = request.form.getlist('barriers')
        other_specify = request.form.get('other_specify', '')
        
        # Get user role information from form (passed from popup)
        user_role = request.form.get('user_role', 'unknown')
        user_subjects = request.form.get('user_subjects', None)
        user_admin_level = request.form.get('user_admin_level', None)
        
        # Clean up empty strings to None
        if user_subjects == '':
            user_subjects = None
        if user_admin_level == '':
            user_admin_level = None
        
        logger.debug(f"Parsed user info from form: role={user_role}, subjects={user_subjects}, admin_level={user_admin_level}")
        logger.debug(f"Barriers: {barriers}, School: {school_name}, District: {district}, GEOID: {block_geoid}")
        
        # Validate required fields
        if not all([school_name, district, block_geoid, barriers]):
            return jsonify({
                "success": False, 
                "message": "Missing required fields"
            }), 400
        
        # Get the school's UNIQUESCHOOLID
        with engine.connect() as connection:
            school_id_query = text("""
                SELECT "UNIQUESCHOOLID"
                FROM "allhsgrades24".tbl_approvedschools 
                WHERE "SCHOOL_NAME" = :school_name 
                AND "SYSTEM_NAME" = :district
            """)
            school_result = connection.execute(school_id_query, {
                "school_name": school_name, 
                "district": district
            }).fetchone()
            
            if not school_result:
                return jsonify({
                    "success": False, 
                    "message": "School not found"
                }), 404
            
            school_unique_id = school_result[0]
        
        # Generate a unique teacher ID
        teacher_id = str(uuid.uuid4())
        submitted_at = datetime.now(ZoneInfo("America/New_York"))
        
        logger.debug(f"About to insert with: teacher_id={teacher_id}, user_role={user_role}, user_subjects={user_subjects}, user_admin_level={user_admin_level}")
        
        # Insert each barrier as a separate row
        with engine.begin() as connection:
            for barrier in barriers:
                reason_code = barrier.lower()[:50]
                comment = other_specify if barrier == 'other' else barrier
                
                insert_query = text("""
                    INSERT INTO "allhsgrades24".teacher_reason_submissions
                    ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment, submitted_at, 
                     user_role, user_subjects, user_admin_level)
                    VALUES (:school_id, :teacher_id, :geoid, :reason_code, :comment, :submitted_at,
                            :user_role, :user_subjects, :user_admin_level)
                """)
                
                connection.execute(insert_query, {
                    "school_id": school_unique_id,
                    "teacher_id": teacher_id,
                    "geoid": block_geoid,
                    "reason_code": reason_code,
                    "comment": comment,
                    "submitted_at": submitted_at,
                    "user_role": user_role,
                    "user_subjects": user_subjects,
                    "user_admin_level": user_admin_level
                })
        
        logger.info(f"Successfully inserted {len(barriers)} barrier submissions for block group {block_geoid} with role data: {user_role}")
        return jsonify({
            "success": True, 
            "message": f"Successfully submitted {len(barriers)} barrier(s)"
        })

    except Exception as e:
        import traceback
        logger.error(f"Error in submit_barriers: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False, 
            "message": f"Server error: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run(debug=True)