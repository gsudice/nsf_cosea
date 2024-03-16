from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from flask import Flask, render_template, redirect, url_for, request, jsonify

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
    
if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5000, debug=True)
