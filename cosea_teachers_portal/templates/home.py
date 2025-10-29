from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import folium
from folium import plugins
import os
import logging
import uuid
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
import json

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
    engine = create_engine(
        db_connection_url,
        connect_args={'connect_timeout': 10},
        pool_pre_ping=True
    )
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Successfully connected to database")
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    engine = None

def get_ip_hash():
    """Generate a one-way hash of the user's IP address"""
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_address:
        return hashlib.sha256(ip_address.encode()).hexdigest()
    return None

@app.before_request
def ensure_session_id():
    """Create a unique session ID for each user if they don't have one"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session['ip_hash'] = get_ip_hash()
        session['school_submissions'] = {}
        logger.info(f"New session created: {session['session_id']}")

@app.route("/")
def home():
    # Clear any existing session data when returning to home
    session.clear()
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
            
            # Handle "other" subject - replace with "other(specified text)"
            subject_other_specify = request.form.get('subject_other_specify', '').strip()
            if 'other' in subjects and subject_other_specify:
                # Replace "other" with "other(text)"
                subjects = [s if s != 'other' else f'other({subject_other_specify})' for s in subjects]
            
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

def get_school_key(district, school):
    """Generate a unique key for a district-school combination"""
    return f"{district}|||{school}"

@app.route("/district", methods=["GET", "POST"])
def district():
    if 'role' not in session:
        logger.warning("User attempted to access district page without role selection")
        return redirect(url_for('role_selection'))
    
    if request.method == "POST":
        selected_district = request.form.get('district')
        selected_school = request.form.get('school')
        
        if not selected_district or not selected_school:
            districts = get_districts()
            return render_template('district.html', 
                                 districts=districts,
                                 error_message="Please select both district and school.")
        
        # Store current selections
        session['selected_district'] = selected_district
        session['selected_school'] = selected_school
        
        # Check if we have previous data for this school
        school_key = get_school_key(selected_district, selected_school)
        if 'school_submissions' not in session:
            session['school_submissions'] = {}
        
        if school_key in session.get('school_submissions', {}):
            # Load previous data for this school
            school_data = session['school_submissions'][school_key]
            session['q1_familiarity'] = school_data.get('q1_familiarity')
            session['q2_accessibility'] = school_data.get('q2_accessibility')
            session['q3_biggest_barrier'] = school_data.get('q3_biggest_barrier')
            session['district_barriers'] = school_data.get('district_barriers', [])
            session['district_barriers_other'] = school_data.get('district_barriers_other', '')
            logger.info(f"✅ Loaded previous data for {school_key}")
            logger.debug(f"Loaded barriers: {session['district_barriers']}")
        else:
            # Clear previous school's data for new school
            session.pop('q1_familiarity', None)
            session.pop('q2_accessibility', None)
            session.pop('q3_biggest_barrier', None)
            session.pop('district_barriers', None)
            session.pop('district_barriers_other', None)
            logger.info(f"Starting fresh for new school: {school_key}")
        
        session.modified = True
        logger.info(f"District and school selected: {selected_district}, {selected_school}")
        return redirect(url_for('survey_questions'))
    
    try:
        districts = get_districts()
        user_info = {
            'role': session.get('role'),
            'subjects': session.get('subjects'),
            'admin_level': session.get('admin_level')
        }
        
        return render_template('district.html', districts=districts, user_info=user_info)
    except Exception as e:
        logger.error(f"Error fetching districts: {e}")
        return render_template('district.html', error_message="Error fetching districts")

def get_districts():
    """Helper function to get list of districts"""
    try:
        with engine.connect() as connection:
            districts_query = text("""
                SELECT DISTINCT "SYSTEM_NAME" 
                FROM "allhsgrades24".tbl_approvedschools 
                ORDER BY "SYSTEM_NAME"
            """)
            return [row[0] for row in connection.execute(districts_query).fetchall()]
    except Exception as e:
        logger.error(f"Error fetching districts: {e}")
        return []

@app.route("/survey_questions", methods=["GET", "POST"])
def survey_questions():
    if 'selected_district' not in session or 'selected_school' not in session:
        logger.warning("User attempted to access survey without selecting district/school")
        return redirect(url_for('district'))
    
    if request.method == "POST":
        # Save survey responses to session - NO VALIDATION, all optional
        session['q1_familiarity'] = request.form.get('q1_familiarity', '')
        session['q2_accessibility'] = request.form.get('q2_accessibility', '')
        session['q3_biggest_barrier'] = request.form.get('q3_biggest_barrier', '')
        
        # Save to school_submissions immediately after survey
        school_key = get_school_key(session['selected_district'], session['selected_school'])
        if 'school_submissions' not in session:
            session['school_submissions'] = {}
        
        # Update or create the school submission with survey data
        if school_key not in session['school_submissions']:
            session['school_submissions'][school_key] = {}
        
        session['school_submissions'][school_key].update({
            'district': session['selected_district'],
            'school': session['selected_school'],
            'q1_familiarity': session['q1_familiarity'],
            'q2_accessibility': session['q2_accessibility'],
            'q3_biggest_barrier': session['q3_biggest_barrier']
        })
        
        session.modified = True
        logger.info(f"✅ Survey saved to school_submissions for {school_key}")
        return redirect(url_for('district_barriers'))
    
    # Pre-fill form if data exists
    return render_template('survey_questions.html',
                         selected_school=session.get('selected_school'),
                         selected_district=session.get('selected_district'),
                         q1_value=session.get('q1_familiarity'),
                         q2_value=session.get('q2_accessibility'),
                         q3_value=session.get('q3_biggest_barrier'))

@app.route("/district_barriers", methods=["GET", "POST"])
def district_barriers():
    if 'q1_familiarity' not in session:
        logger.warning("User attempted to access barriers without completing survey")
        return redirect(url_for('survey_questions'))
    
    if request.method == "POST":
        barriers = request.form.getlist('barriers')
        other_specify = request.form.get('other_specify', '')
        
        if not barriers:
            return render_template('district_barriers.html',
                                 selected_school=session.get('selected_school'),
                                 selected_district=session.get('selected_district'),
                                 saved_barriers=session.get('district_barriers', []),
                                 saved_other=session.get('district_barriers_other', ''),
                                 error_message="Please select at least one barrier.")
        
        if 'other' in barriers and not other_specify.strip():
            return render_template('district_barriers.html',
                                 selected_school=session.get('selected_school'),
                                 selected_district=session.get('selected_district'),
                                 saved_barriers=barriers,
                                 saved_other=other_specify,
                                 error_message="Please specify the 'Other' barrier.")
        
        # Save barriers to session
        session['district_barriers'] = barriers
        session['district_barriers_other'] = other_specify
        
        # Save this school's complete data to school_submissions
        school_key = get_school_key(session['selected_district'], session['selected_school'])
        if 'school_submissions' not in session:
            session['school_submissions'] = {}
        
        # Update the existing entry (created in survey_questions) with barriers
        if school_key not in session['school_submissions']:
            session['school_submissions'][school_key] = {}
        
        session['school_submissions'][school_key].update({
            'district': session['selected_district'],
            'school': session['selected_school'],
            'q1_familiarity': session.get('q1_familiarity'),
            'q2_accessibility': session.get('q2_accessibility'),
            'q3_biggest_barrier': session.get('q3_biggest_barrier'),
            'district_barriers': barriers,
            'district_barriers_other': other_specify
        })
        
        session.modified = True
        
        logger.info(f"✅ District barriers saved for {school_key}")
        logger.debug(f"Complete school data: {session['school_submissions'][school_key]}")
        logger.info(f"Total schools in session: {len(session['school_submissions'])}")
        return redirect(url_for('render_select'))
    
    # Pre-fill form if data exists
    return render_template('district_barriers.html',
                         selected_school=session.get('selected_school'),
                         selected_district=session.get('selected_district'),
                         saved_barriers=session.get('district_barriers', []),
                         saved_other=session.get('district_barriers_other', ''))

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

@app.route("/select", methods=["GET"])
def render_select():
    if 'district_barriers' not in session:
        logger.warning("User attempted to access map without completing barriers assessment")
        return redirect(url_for('district_barriers'))
    
    selected_district = session.get('selected_district')
    selected_school = session.get('selected_school')
    
    if not selected_district or not selected_school:
        return redirect(url_for('district'))
    
    logger.debug(f"Rendering select page for: {selected_district}, {selected_school}")
    
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

            return render_template(
                'select.html',
                instructions=render_template("selectInstructions.html"),
                selected_district=selected_district,
                selected_school=selected_school,
                latitude=latitude,
                longitude=longitude,
                block_groups=block_groups,
                school_submissions=session.get('school_submissions', {}),
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

@app.route("/saveData", methods=["POST"])
def submit_barriers():
    """Save individual block barrier data"""
    try:
        logger.debug("=== SAVEDATA ENDPOINT CALLED ===")
        return jsonify({"success": True, "message": "Data received"})
    except Exception as e:
        import traceback
        logger.error(f"Error in submit_barriers: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route("/end_session", methods=["POST"])
def end_session():
    """Save ALL data from localStorage and Flask session when user clicks 'End Session'"""
    try:
        logger.debug("=== END SESSION - SAVING ALL DATA ===")
        data = request.get_json()
        
        # Get localStorage data sent from client
        local_storage_data = data.get('localStorage', {})
        
        logger.info(f"Received localStorage keys: {list(local_storage_data.keys())}")
        
        # Extract all school block submissions from localStorage
        all_school_blocks = {}
        for key, value in local_storage_data.items():
            if key.startswith('school_') and key.endswith('_submissions'):
                school_identifier = key.replace('school_', '').replace('_submissions', '')
                try:
                    parsed_value = json.loads(value) if isinstance(value, str) else value
                    all_school_blocks[school_identifier] = parsed_value
                    logger.info(f"Parsed localStorage for {school_identifier}: {len(parsed_value)} blocks")
                except Exception as parse_error:
                    logger.error(f"Failed to parse localStorage data for key {key}: {parse_error}")
        
        logger.info(f"Found {len(all_school_blocks)} schools with block data in localStorage")
        
        # Get Flask session data
        school_submissions = session.get('school_submissions', {})
        
        logger.info(f"Flask session has {len(school_submissions)} schools")
        logger.debug(f"Session school keys: {list(school_submissions.keys())}")
        
        if not school_submissions:
            logger.error("No school submissions found in Flask session!")
            return jsonify({"success": False, "error": "No survey/barrier data found. Please complete the survey."}), 400
        
        teacher_id = str(uuid.uuid4())
        client_session_id = session.get('session_id')
        ip_hash = session.get('ip_hash') or get_ip_hash()
        eastern = ZoneInfo("America/New_York")
        submitted_at = datetime.now(eastern).replace(tzinfo=None)
        
        user_role = session.get('role', 'unknown')
        user_subjects = ','.join(session.get('subjects', [])) if session.get('role') == 'teacher' else None
        user_admin_level = session.get('admin_level') if session.get('role') == 'administrator' else None
        
        total_saved = 0
        total_failed = 0
        schools_processed = []
        processed_school_ids = set()
        
        with engine.begin() as connection:
            # Process each school's data
            for school_key, school_session_data in school_submissions.items():
                try:
                    district = school_session_data.get('district')
                    school_name = school_session_data.get('school')
                    
                    # Get survey and district barrier data from session
                    q1_familiarity = school_session_data.get('q1_familiarity', '').strip()
                    q2_accessibility = school_session_data.get('q2_accessibility', '').strip()
                    q3_biggest_barrier = school_session_data.get('q3_biggest_barrier', '').strip()
                    district_barriers = ','.join(school_session_data.get('district_barriers', []))
                    district_barriers_other = school_session_data.get('district_barriers_other', '').strip()
                    
                    # Convert empty strings to None (NULL in database)
                    q1_familiarity = q1_familiarity if q1_familiarity else None
                    q2_accessibility = q2_accessibility if q2_accessibility else None
                    q3_biggest_barrier = q3_biggest_barrier if q3_biggest_barrier else None
                    district_barriers_other = district_barriers_other if district_barriers_other else None
                    
                    logger.info(f"Processing school: {school_name}")
                    logger.debug(f"Session data - Q1: {q1_familiarity}, Q2: {q2_accessibility}, Q3: {q3_biggest_barrier}")
                    logger.debug(f"District barriers: {district_barriers}")
                    
                    # Get school ID first
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
                        logger.error(f"❌ School not found in database: {school_name}")
                        continue
                    
                    school_unique_id = school_result[0]
                    logger.info(f"School ID: {school_unique_id}")
                    
                    # Check if we've already processed this school
                    if school_unique_id in processed_school_ids:
                        logger.warning(f"⚠️ School {school_name} (ID: {school_unique_id}) already processed, skipping duplicate")
                        continue
                    
                    # Mark this school as processed
                    processed_school_ids.add(school_unique_id)
                    
                    # Match localStorage key
                    school_name_clean = school_name.replace(' ', '_')
                    block_submissions = None
                    
                    # Try different key formats
                    possible_keys = [
                        school_name_clean,
                        school_name.replace(' ', '_'),
                        f"{district}_{school_name}".replace(' ', '_'),
                    ]
                    
                    for possible_key in possible_keys:
                        if possible_key in all_school_blocks:
                            block_submissions = all_school_blocks[possible_key]
                            logger.info(f"✅ Found block data with key: {possible_key}")
                            break
                    
                    # Handle case where there are NO census blocks
                    if not block_submissions or len(block_submissions) == 0:
                        logger.info(f"ℹ️ No block submissions found for {school_name}. Saving survey/barrier data with NULL geoid.")
                        
                        insert_query = text("""
                            INSERT INTO "allhsgrades24".teacher_reason_submissions
                            ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment, submitted_at, 
                             user_role, user_subjects, user_admin_level, session_id, ip_hash,
                             q1_familiarity, q2_accessibility, q3_biggest_barrier,
                             district_barriers, district_barriers_other)
                            VALUES (:school_id, :teacher_id, NULL, 'no_census_assessment', NULL, :submitted_at,
                                    :user_role, :user_subjects, :user_admin_level, :session_id, :ip_hash,
                                    :q1_familiarity, :q2_accessibility, :q3_biggest_barrier,
                                    :district_barriers, :district_barriers_other)
                        """)
                        
                        connection.execute(insert_query, {
                            "school_id": school_unique_id,
                            "teacher_id": teacher_id,
                            "submitted_at": submitted_at,
                            "user_role": user_role,
                            "user_subjects": user_subjects,
                            "user_admin_level": user_admin_level,
                            "session_id": client_session_id,
                            "ip_hash": ip_hash,
                            "q1_familiarity": q1_familiarity,
                            "q2_accessibility": q2_accessibility,
                            "q3_biggest_barrier": q3_biggest_barrier,
                            "district_barriers": district_barriers,
                            "district_barriers_other": district_barriers_other
                        })
                        
                        logger.info(f"✅ Saved survey/barrier data for {school_name} (no census blocks)")
                        schools_processed.append(school_name)
                        total_saved += 1
                        continue
                    
                    logger.info(f"Processing {len(block_submissions)} blocks for {school_name}")
                    
                    # DELETE previous submissions for this school and session
                    delete_school_query = text("""
                        DELETE FROM "allhsgrades24".teacher_reason_submissions
                        WHERE "UNIQUESCHOOLID" = :school_id 
                        AND session_id = :session_id
                    """)
                    delete_result = connection.execute(delete_school_query, {
                        'school_id': school_unique_id,
                        'session_id': client_session_id
                    })
                    logger.info(f"🗑️ Deleted {delete_result.rowcount} previous submissions for school {school_name}")
                    
                    # Insert new data
                    blocks_saved_for_school = 0
                    for geoid, block_data in block_submissions.items():
                        try:
                            barriers = block_data.get('barriers', [])
                            notes = block_data.get('notes', '')
                            
                            if not barriers:
                                logger.warning(f"No barriers for block {geoid}, skipping")
                                continue
                            
                            # Insert submissions for each barrier
                            for barrier in barriers:
                                reason_code = barrier.lower()[:50]
                                # Comment is NULL unless barrier is 'other' with notes
                                if barrier.lower() == 'other' and notes.strip():
                                    comment = notes.strip()
                                else:
                                    comment = None
                                
                                insert_query = text("""
                                    INSERT INTO "allhsgrades24".teacher_reason_submissions
                                    ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment, submitted_at, 
                                     user_role, user_subjects, user_admin_level, session_id, ip_hash,
                                     q1_familiarity, q2_accessibility, q3_biggest_barrier,
                                     district_barriers, district_barriers_other)
                                    VALUES (:school_id, :teacher_id, :geoid, :reason_code, :comment, :submitted_at,
                                            :user_role, :user_subjects, :user_admin_level, :session_id, :ip_hash,
                                            :q1_familiarity, :q2_accessibility, :q3_biggest_barrier,
                                            :district_barriers, :district_barriers_other)
                                """)
                                
                                connection.execute(insert_query, {
                                    "school_id": school_unique_id,
                                    "teacher_id": teacher_id,
                                    "geoid": geoid,
                                    "reason_code": reason_code,
                                    "comment": comment,
                                    "submitted_at": submitted_at,
                                    "user_role": user_role,
                                    "user_subjects": user_subjects,
                                    "user_admin_level": user_admin_level,
                                    "session_id": client_session_id,
                                    "ip_hash": ip_hash,
                                    "q1_familiarity": q1_familiarity,
                                    "q2_accessibility": q2_accessibility,
                                    "q3_biggest_barrier": q3_biggest_barrier,
                                    "district_barriers": district_barriers,
                                    "district_barriers_other": district_barriers_other
                                })
                                
                                logger.debug(f"✅ Saved barrier '{barrier}' for block {geoid}")
                            
                            blocks_saved_for_school += 1
                            total_saved += 1
                            
                        except Exception as block_error:
                            logger.error(f"❌ Failed to save block {geoid}: {str(block_error)}")
                            total_failed += 1
                    
                    logger.info(f"✅ Saved {blocks_saved_for_school} blocks for {school_name}")
                    schools_processed.append(school_name)
                    
                except Exception as school_error:
                    import traceback
                    logger.error(f"❌ Failed to process school {school_key}: {str(school_error)}")
                    logger.error(traceback.format_exc())
                    total_failed += 1
        
        logger.info(f"=== SESSION SAVE COMPLETE ===")
        logger.info(f"✅ Saved: {total_saved} blocks across {len(schools_processed)} schools")
        logger.info(f"❌ Failed: {total_failed} blocks")
        logger.info(f"📚 Schools: {schools_processed}")
        
        # Clear Flask session after successful save
        session.clear()
        
        return jsonify({
            "success": True, 
            "count": total_saved,
            "schools": len(schools_processed),
            "failed": total_failed,
            "redirect": url_for('home')
        })
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Error in end_session: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, debug=False)