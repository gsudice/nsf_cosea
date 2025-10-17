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

@app.before_request
def ensure_session_id():
    """Create a unique session ID for each user if they don't have one"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        logger.info(f"New session created: {session['session_id']}")

@app.route("/")
def home():
    return render_template('home.html')

@app.route("/role_selection", methods=["GET", "POST"])
def role_selection():
    if request.method == "POST":
        role = request.form.get('role')
        session['role'] = role
        
        if role == 'teacher':
            subjects = request.form.getlist('subjects')
            if not subjects:
                return render_template('role_selection.html', 
                                     error_message="Please select at least one subject.")
            session['subjects'] = subjects
            session.pop('admin_level', None)
            
        elif role == 'administrator':
            admin_level = request.form.get('admin_level')
            if not admin_level:
                return render_template('role_selection.html',
                                     error_message="Please select your administrative level.")
            session['admin_level'] = admin_level
            session.pop('subjects', None)
        
        logger.info(f"User role saved: {role}, Session ID: {session['session_id']}")
        return redirect(url_for('district'))
    
    return render_template('role_selection.html')

@app.route("/district")
def district():
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
            
            user_info = {
                'role': session.get('role'),
                'subjects': session.get('subjects'),
                'admin_level': session.get('admin_level')
            }
            
            return render_template('district.html', districts=districts, user_info=user_info)
    except Exception as e:
        logger.error(f"Error fetching districts: {e}")
        return render_template('district.html', error_message="Error fetching districts")

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

def get_block_groups(school_id):
    try:
        with engine.connect() as connection:
            block_groups_query = text("""
                SELECT 
                    ST_AsGeoJSON(ST_Transform(cbgpolygeom, 4326))::json AS geometry, 
                    "GEOID" AS "geoid"
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

@app.route("/api/census_blocks/<int:school_id>")
def get_census_blocks_api(school_id):
    """API endpoint to fetch census blocks as GeoJSON for a given school"""
    try:
        with engine.connect() as connection:
            block_groups_query = text("""
                SELECT 
                    ST_AsGeoJSON(ST_Transform(cbgpolygeom, 4326))::json AS geometry, 
                    "GEOID" AS "geoid"
                FROM "allhsgrades24".tbl_cbg_finalassignment
                WHERE "UNIQUESCHOOLID" = :school_id
            """)
            result = connection.execute(block_groups_query, {"school_id": school_id}).fetchall()
            
            features = []
            for row in result:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "geoid": row.geoid
                    },
                    "geometry": row.geometry
                })
            
            geojson = {
                "type": "FeatureCollection",
                "features": features
            }
            
            logger.debug(f"Returning {len(features)} census blocks for school {school_id}")
            return jsonify(geojson)
            
    except Exception as e:
        logger.error(f"Error fetching census blocks: {e}")
        return jsonify({"type": "FeatureCollection", "features": []}), 500

@app.route("/api/save_session", methods=["POST"])
def save_session_to_database():
    """Save all session submissions to database when user clicks 'End Session'"""
    try:
        data = request.get_json()
        school_id = data.get('school_id')
        submissions = data.get('submissions', {})
        
        if not school_id or not submissions:
            return jsonify({"success": False, "error": "Missing data"}), 400
        
        teacher_id = str(uuid.uuid4())
        client_session_id = session.get('session_id')
        eastern = ZoneInfo("America/New_York")
        submitted_at = datetime.now(eastern).replace(tzinfo=None)
        
        user_role = session.get('role', 'unknown')
        user_subjects = ','.join(session.get('subjects', [])) if session.get('role') == 'teacher' else None
        user_admin_level = session.get('admin_level') if session.get('role') == 'administrator' else None
        
        saved_count = 0
        
        with engine.begin() as connection:
            for geoid, data in submissions.items():
                barriers = data.get('barriers', [])
                notes = data.get('notes', '')
                
                # Delete any existing submissions for this block in this session
                delete_query = text("""
                    DELETE FROM "allhsgrades24".teacher_reason_submissions
                    WHERE session_id = :session_id AND geoid = :geoid
                """)
                connection.execute(delete_query, {
                    'session_id': client_session_id,
                    'geoid': geoid
                })
                
                # Insert new submissions
                for barrier in barriers:
                    reason_code = barrier.lower()[:50]
                    comment = notes if barrier == 'other' else barrier
                    
                    insert_query = text("""
                        INSERT INTO "allhsgrades24".teacher_reason_submissions
                        ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment, submitted_at, 
                         user_role, user_subjects, user_admin_level, session_id)
                        VALUES (:school_id, :teacher_id, :geoid, :reason_code, :comment, :submitted_at,
                                :user_role, :user_subjects, :user_admin_level, :session_id)
                    """)
                    
                    connection.execute(insert_query, {
                        "school_id": school_id,
                        "teacher_id": teacher_id,
                        "geoid": geoid,
                        "reason_code": reason_code,
                        "comment": comment,
                        "submitted_at": submitted_at,
                        "user_role": user_role,
                        "user_subjects": user_subjects,
                        "user_admin_level": user_admin_level,
                        "session_id": client_session_id
                    })
                    
                    saved_count += 1
        
        logger.info(f"Successfully saved {saved_count} submissions for school {school_id}")
        return jsonify({"success": True, "count": saved_count})
        
    except Exception as e:
        logger.error(f"Error saving session: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/select", methods=["GET", "POST"])
def render_select():
    if 'role' not in session:
        logger.warning("User attempted to access select page without role selection")
        return redirect(url_for('role_selection'))
    
    if request.method == "POST":
        selected_district = request.form.get('district')
        selected_school = request.form.get('school')
        
        session['selected_district'] = selected_district
        session['selected_school'] = selected_school
        
        logger.debug(f"Selected district: {selected_district}, school: {selected_school}")
        
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
                        instructions='',
                        selected_district=selected_district,
                        selected_school=selected_school,
                        latitude=0,
                        longitude=0,
                        block_groups=[],
                        user_info={},
                        error_message="School location not found."
                    )

                longitude, latitude, school_id = result
                block_groups = get_block_groups(school_id)
                logger.debug(f"Retrieved {len(block_groups)} block groups")

                # Pass data to template
                return render_template(
                    'select.html',
                    instructions=render_template("selectInstructions.html"),
                    selected_district=selected_district,
                    selected_school=selected_school,
                    latitude=latitude,
                    longitude=longitude,
                    block_groups=block_groups,
                    user_info={
                        'role': session.get('role', 'unknown'),
                        'subjects': ','.join(session.get('subjects', [])) if session.get('role') == 'teacher' else None,
                        'admin_level': session.get('admin_level') if session.get('role') == 'administrator' else None
                    }
                )

        except Exception as e:
            logger.error(f"Error fetching school data: {str(e)}")
            return render_template(
                'select.html',
                instructions='',
                selected_district=selected_district or 'Unknown',
                selected_school=selected_school or 'Unknown',
                latitude=0,
                longitude=0,
                block_groups=[],
                user_info={},
                error_message="Error fetching school data"
            )
    
    # If GET request, show empty page with error
    return render_template(
        'select.html',
        instructions='',
        selected_district='',
        selected_school='',
        latitude=0,
        longitude=0,
        block_groups=[],
        user_info={},
        error_message='Please select a school from the district page.'
    )

@app.route("/saveData", methods=["POST"])
def submit_barriers():
    try:
        logger.debug("=== SAVEDATA ENDPOINT CALLED ===")
        
        # Get session_id from client
        client_session_id = request.form.get('client_session_id')
        
        # Support multiple block submissions
        block_geoids_raw = request.form.get('block_geoids', '')
        if block_geoids_raw:
            block_geoids = [b.strip() for b in block_geoids_raw.split(',') if b.strip()]
        else:
            single_block = request.form.get('block_geoid', '').strip()
            block_geoids = [single_block] if single_block else []
        
        school_name = request.form.get('school')
        district = request.form.get('district')
        barriers = request.form.getlist('barriers')
        other_specify = request.form.get('other_specify', '')
        
        user_role = request.form.get('user_role', 'unknown')
        user_subjects = request.form.get('user_subjects', None)
        user_admin_level = request.form.get('user_admin_level', None)
        
        if user_subjects == '':
            user_subjects = None
        if user_admin_level == '':
            user_admin_level = None
        
        logger.debug(f"Client Session: {client_session_id}, Blocks: {block_geoids}, Barriers: {barriers}")
        
        if not all([school_name, district, block_geoids, barriers]):
            return jsonify({
                "success": False, 
                "message": "Missing required fields"
            }), 400
        
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
        
        teacher_id = str(uuid.uuid4())
        eastern = ZoneInfo("America/New_York")
        submitted_at = datetime.now(eastern).replace(tzinfo=None)
        
        saved_blocks = []
        
        with engine.begin() as connection:
            for block_geoid in block_geoids:
                if not block_geoid or block_geoid == 'N/A':
                    continue
                
                # Delete existing submissions for this block in this client session (allows editing)
                if client_session_id:
                    delete_query = text("""
                        DELETE FROM "allhsgrades24".teacher_reason_submissions
                        WHERE session_id = :session_id AND geoid = :geoid
                    """)
                    connection.execute(delete_query, {
                        'session_id': client_session_id,
                        'geoid': block_geoid
                    })
                
                # Insert new submissions
                for barrier in barriers:
                    reason_code = barrier.lower()[:50]
                    comment = other_specify if barrier == 'other' else barrier
                    
                    insert_query = text("""
                        INSERT INTO "allhsgrades24".teacher_reason_submissions
                        ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment, submitted_at, 
                         user_role, user_subjects, user_admin_level, session_id)
                        VALUES (:school_id, :teacher_id, :geoid, :reason_code, :comment, :submitted_at,
                                :user_role, :user_subjects, :user_admin_level, :session_id)
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
                        "user_admin_level": user_admin_level,
                        "session_id": client_session_id
                    })
                
                saved_blocks.append(block_geoid)
        
        logger.info(f"Successfully saved {len(barriers)} barriers for {len(saved_blocks)} block(s)")
        return jsonify({
            "success": True, 
            "message": f"Successfully submitted {len(barriers)} barrier(s) for {len(saved_blocks)} block(s)",
            "saved_blocks": saved_blocks
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