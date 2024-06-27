from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from flask import Flask, render_template, redirect, url_for, request, jsonify
import folium

load_dotenv()

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
SERVER = os.getenv("SERVER")
DATABASE = os.getenv("DATABASE")
PORT = "5432"

try:
    # Create the connection URL to access the server as a text string
    db_connection_url = f"postgresql://{USERNAME}:{PASSWORD}@{SERVER}/{DATABASE}"
    # Connect to the engine
    engine = create_engine(db_connection_url)
    print("Succesful Connection to the DB")
except Exception as e:
    print(f'Unable to connect to the DB: {str(e)}')
    
app = Flask(__name__)

def generate_census_blocks_map(school_location):
    radius_meters = 1000 #Will have this variable to be school zone

    # Define the SQL query with ST_Transform to match SRID 4269
    query = text('''
        SELECT ST_AsGeoJSON(geom)
        FROM uscensus_tigerline_2023.blockgroups
        WHERE ST_DWithin(
            geom,
            ST_Transform(ST_SetSRID(ST_Point(:lon, :lat), 4326), 4269),
            :radius
        );
    ''')

    geojson_features = []
    with engine.connect() as connection:
        # Execute the query with a dictionary of parameter values
        result = connection.execute(
            query,
            {"lon": school_location[1], "lat": school_location[0], "radius": radius_meters}
        )
        for row in result:
            geojson_features.append(row[0])

    folium_map = folium.Map(location=school_location, zoom_start=12, tiles='OpenStreetMap')
    for feature in geojson_features:
        folium.GeoJson(
            feature,
            name='Census Block',
            style_function=lambda x: {'fillColor': 'blue', 'fillOpacity': 0.3, 'color': 'blue', 'weight': 1}
        ).add_to(folium_map)
    folium.Marker(school_location, popup='Selected School').add_to(folium_map)

    

    # Render the map to HTML
    map_html = folium_map._repr_html_()
    return map_html

@app.route("/")
def render_index():
    return render_template("home.html")

@app.route("/district")
def render_district():
    try:
        query = text("""
            SELECT DISTINCT nmcnty 
            FROM nces_schools.publicschools 
            WHERE state = 'GA'
            UNION
            SELECT DISTINCT nmcnty 
            FROM nces_schools.privateschools 
            WHERE state = 'GA'
            ORDER BY nmcnty ASC
        """)
        with engine.connect() as connection:
            options = connection.execute(query).fetchall()
        options = [option[0] for option in options] 
        return render_template("district.html", options=options)
    except Exception as e:
        return str(e)

@app.route("/get_schools", methods=["POST"])
def get_schools():
    selected_district = request.form.get("selected_district")
    query = text("""
                 SELECT DISTINCT name
                 FROM nces_schools.publicschools
                 WHERE state = 'GA' AND nmcnty = :district
                 UNION
                 SELECT DISTINCT name
                 FROM nces_schools.privateschools
                 WHERE state= 'GA' AND nmcnty = :district
                 ORDER BY name ASC
                 """)
    with engine.connect() as connection:
         schools = connection.execute(query, {"district": selected_district}).fetchall()
    schools = [school[0] for school in schools]
    return jsonify(schools=schools)

@app.route("/select", methods=["GET", "POST"])
def render_select():
    if request.method == "POST":
        selected_district = request.form.get('district')
        selected_school = request.form.get('school')

        # Retrieve the location (latitude, longitude) of the selected school from the database
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

        try:
            with engine.connect() as connection:
                result = connection.execute(query_location, {"district": selected_district, "school": selected_school}).fetchone()

                if result:
                    # Extract latitude and longitude from the query result tuple
                    latitude = result[0]  # Latitude (first element in the tuple)
                    longitude = result[1]  # Longitude (second element in the tuple)

                    # Generate the Folium map with census blocks around the selected school
                    school_location = (latitude, longitude)
                    map_html = generate_census_blocks_map(school_location)

                    # Pass the map HTML and other data to the template
                    return render_template('select.html', map_html=map_html, selected_district=selected_district, selected_school=selected_school)

                else:
                    # Handle the case if school location data is not found
                    error_message = "School location not found in the database."
                    return render_template('select.html', error_message=error_message)

        except Exception as e:
            # Handle database connection or query execution errors
            error_message = f"Error retrieving school location: {str(e)}"
            return render_template('select.html', error_message=error_message)

    return render_template('select.html')
   
if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5000, debug=True)