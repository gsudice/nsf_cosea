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
review_cache = {}
# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from pathlib import Path
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

USERNAME = os.getenv("DB_USERNAME")
PASSWORD = os.getenv("DB_PASSWORD")
SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_DATABASE")
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
            cs_teaching = request.form.get('cs_teaching')
            if not cs_teaching:
                return render_template('role_selection.html', 
                                     error_message="Please answer the Computer Science teaching question.")
            
            session['cs_teaching'] = cs_teaching
            session.pop('admin_level', None)
            
        elif role == 'administrator':
            admin_level = request.form.get('admin_level')
            if not admin_level:
                return render_template('role_selection.html',
                                     error_message="Please select your administrative level.")
            session['admin_level'] = admin_level
            session.pop('cs_teaching', None)
        
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
            
            # Load individual Q3 values
            q3_text = school_data.get('q3_biggest_barrier', '')
            q3_parts = q3_text.split('\n') if q3_text else []
            session['q3_1'] = q3_parts[0] if len(q3_parts) > 0 else ''
            session['q3_2'] = q3_parts[1] if len(q3_parts) > 1 else ''
            session['q3_3'] = q3_parts[2] if len(q3_parts) > 2 else ''
            
            session['district_barriers'] = school_data.get('district_barriers', [])
            session['district_barriers_other'] = school_data.get('district_barriers_other', '')
            logger.info(f"✅ Loaded previous data for {school_key}")
            logger.debug(f"Loaded barriers: {session['district_barriers']}")
        else:
            # Clear previous school's data for new school
            session.pop('q1_familiarity', None)
            session.pop('q2_accessibility', None)
            session.pop('q3_biggest_barrier', None)
            session.pop('q3_1', None)
            session.pop('q3_2', None)
            session.pop('q3_3', None)
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
        # Save survey responses to session
        session['q1_familiarity'] = request.form.get('q1_familiarity', '')
        session['q2_accessibility'] = request.form.get('q2_accessibility', '')
        q3_1 = request.form.get('q3_1', '').strip()
        q3_2 = request.form.get('q3_2', '').strip()
        q3_3 = request.form.get('q3_3', '').strip()
        session['q3_biggest_barrier'] = "\n".join([x for x in [q3_1, q3_2, q3_3] if x])
        
        # Save individual Q3 values
        session['q3_1'] = q3_1
        session['q3_2'] = q3_2
        session['q3_3'] = q3_3
        
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
                         q3_1_value=session.get('q3_1'),
                         q3_2_value=session.get('q3_2'),
                         q3_3_value=session.get('q3_3'))

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
    """Save ALL collected user data to database and redirect to review page."""
    # ------------------------------------------------------
    # 1. READ INPUT + SESSION-SAVED SURVEY DATA
    # ------------------------------------------------------
    try:
        data = request.get_json()
        local_storage_data = data.get("localStorage", {})

        if "school_submissions" not in session:
            return jsonify({"success": False, "error": "No data to save"}), 400

        school_submissions = session["school_submissions"]

        teacher_id = str(uuid.uuid4())
        client_session_id = session["session_id"]
        ip_hash = session.get("ip_hash", get_ip_hash())
        user_role = session.get("role")
        user_subjects = ",".join(session.get("subjects", [])) if user_role == "teacher" else None
        user_admin_level = session.get("admin_level") if user_role == "administrator" else None

        # Timestamp
        try:
            eastern = ZoneInfo("America/New_York")
            submitted_at = datetime.now(eastern).replace(tzinfo=None)
        except:
            submitted_at = datetime.utcnow()

    except Exception as e:
        logger.error(f"Error parsing end_session input: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    # ------------------------------------------------------
    # 2. WRITE ALL DATA TO DATABASE
    # ------------------------------------------------------
    try:
        with engine.begin() as conn:

            for school_key, school_data in school_submissions.items():
                district = school_data["district"]
                school_name = school_data["school"]

                # Get school ID
                row = conn.execute(
                    text("""
                        SELECT "UNIQUESCHOOLID"
                        FROM "allhsgrades24".tbl_approvedschools
                        WHERE "SYSTEM_NAME" = :d AND "SCHOOL_NAME" = :s
                    """),
                    {"d": district, "s": school_name}
                ).fetchone()

                if not row:
                    continue

                school_id = row[0]

                # Remove old entries for same session
                conn.execute(
                    text("""
                        DELETE FROM "allhsgrades24".teacher_reason_submissions
                        WHERE "UNIQUESCHOOLID" = :sid AND session_id = :sess
                    """),
                    {"sid": school_id, "sess": client_session_id}
                )

                # District-level barriers
                db_barriers = ",".join(school_data.get("district_barriers", []))
                db_other = school_data.get("district_barriers_other")

                # Get census block data from local storage
                block_key = school_name.replace(" ", "_")
                block_json = local_storage_data.get(f"school_{block_key}_submissions", "{}")
                try:
                    block_data = json.loads(block_json)
                except:
                    block_data = {}

                # If no block groups → write one row
                if not block_data:
                    conn.execute(
                        text("""
                            INSERT INTO "allhsgrades24".teacher_reason_submissions
                            ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment,
                             submitted_at, user_role, user_subjects, user_admin_level,
                             session_id, ip_hash, q1_familiarity, q2_accessibility,
                             q3_biggest_barrier, district_barriers, district_barriers_other)
                            VALUES (:sid, :tid, NULL, 'no_census_assessment', NULL,
                                    :time, :role, :subj, :admin, :sess, :ip,
                                    :q1, :q2, :q3, :dbarr, :dbother)
                        """),
                        {
                            "sid": school_id,
                            "tid": teacher_id,
                            "time": submitted_at,
                            "role": user_role,
                            "subj": user_subjects,
                            "admin": user_admin_level,
                            "sess": client_session_id,
                            "ip": ip_hash,
                            "q1": school_data.get("q1_familiarity"),
                            "q2": school_data.get("q2_accessibility"),
                            "q3": school_data.get("q3_biggest_barrier"),
                            "dbarr": db_barriers,
                            "dbother": db_other
                        }
                    )
                else:
                    # Save each block row
                    for geoid, block_info in block_data.items():
                        barriers = block_info.get("barriers", [])
                        notes = block_info.get("notes")

                        for b in barriers:
                            reason_code = b.lower()
                            comment = notes if b == "other" else None

                            conn.execute(
                                text("""
                                    INSERT INTO "allhsgrades24".teacher_reason_submissions
                                    ("UNIQUESCHOOLID", teacher_id, geoid, reason_code, comment,
                                     submitted_at, user_role, user_subjects, user_admin_level,
                                     session_id, ip_hash, q1_familiarity, q2_accessibility,
                                     q3_biggest_barrier, district_barriers, district_barriers_other)
                                    VALUES (:sid, :tid, :geoid, :reason, :comment, :time,
                                            :role, :subj, :admin, :sess, :ip,
                                            :q1, :q2, :q3, :dbarr, :dbother)
                                """),
                                {
                                    "sid": school_id,
                                    "tid": teacher_id,
                                    "geoid": geoid,
                                    "reason": reason_code,
                                    "comment": comment,
                                    "time": submitted_at,
                                    "role": user_role,
                                    "subj": user_subjects,
                                    "admin": user_admin_level,
                                    "sess": client_session_id,
                                    "ip": ip_hash,
                                    "q1": school_data.get("q1_familiarity"),
                                    "q2": school_data.get("q2_accessibility"),
                                    "q3": school_data.get("q3_biggest_barrier"),
                                    "dbarr": db_barriers,
                                    "dbother": db_other
                                }
                            )

    except Exception as e:
        logger.error(f"Database write error in end_session: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    # ------------------------------------------------------
    # 3. BUILD REVIEW TOKEN + STORE REVIEW DATA
    # ------------------------------------------------------
    token = str(uuid.uuid4())
    review_cache[token] = {"schools": []}

    for school_key, school_data in school_submissions.items():
        district = school_data["district"]
        school_name = school_data["school"]

        block_key = school_name.replace(" ", "_")
        block_json = local_storage_data.get(f"school_{block_key}_submissions", "{}")
        try:
            school_blocks = json.loads(block_json)
        except:
            school_blocks = {}

        review_cache[token]["schools"].append({
            "district": district,
            "school": school_name,
            "survey": {
                "q1": school_data.get("q1_familiarity"),
                "q2": school_data.get("q2_accessibility"),
                "q3": school_data.get("q3_biggest_barrier")
            },
            "district_barriers": school_data.get("district_barriers"),
            "district_barriers_other": school_data.get("district_barriers_other"),
            "blocks": school_blocks
        })

    # Session can now be cleared
    session.clear()

    return jsonify({
        "success": True,
        "redirect": url_for("review_page", token=token)
    })
    

@app.route("/review")
def review_page():

    token = request.args.get("token")
    if not token or token not in review_cache:
        return "Invalid or expired review token", 404

    data = review_cache[token]
    return render_template("review.html", schools=data["schools"])

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, debug=False)

