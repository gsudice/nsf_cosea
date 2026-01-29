from flask import Flask, request, jsonify
from location_modelling import run_location_models
import re
import uuid
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import threading
import time

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)


jobs = {}

DEMAND_METRIC_MAP = {
    "sfr": "sfr",
    "cs_enrollment": "cs_enrollment",
    "certified_teachers": "certified_teachers",
}



def slugify_scenario_name(name: str) -> str:
    """Turn free-text scenario name into a safe slug for folders / DB."""
    if not name:
        return "scenario"
    value = name.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"^_+|_+$", "", value)
    if not value:
        value = "scenario"
    if not value[0].isalpha():
        value = f"s_{value}"
    return value[:50]


def run_location_models_async(job_id, metric_slug, p_value, coverage_miles, scenario_slug, model_choice):
    """Run the location models in a background thread."""
    try:
        jobs[job_id]["status"] = "running"
        result = run_location_models(
            demand_metric=metric_slug,
            p=p_value,
            coverage_miles=coverage_miles,
            knearest=-1,
            metric_type="haversine",
            aggregate_block_groups=False,
            plot_assignments=False,
            scenario_slug=scenario_slug,
        )
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
        jobs[job_id]["results_url"] = f"/analysis/results/{scenario_slug}"
        if jobs[job_id].get("notify_email"):
            send_results_email(
                to_email=jobs[job_id].get("user_email"),
                scenario_slug=scenario_slug,
                result=result,
            )
    except Exception as exc:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(exc)


def send_results_email(to_email: str, scenario_slug: str, result: dict) -> None:
    """
    Send an email with links / attachments for the analysis results.

    This uses standard SMTP settings from environment variables:

      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL

    If those are not set, the function just logs and returns.
    """
    if not to_email:
        return

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL", smtp_user or to_email)

    if not (smtp_host and smtp_user and smtp_password):
        print("[email] SMTP not configured – skipping email send.")
        return

    msg = EmailMessage()
    msg["Subject"] = f"[Location Modeling] Results for scenario {scenario_slug}"
    msg["From"] = from_email
    msg["To"] = to_email

    body_lines = [
        "Hi,",
        "",
        f"Your location modeling analysis for scenario '{scenario_slug}' has finished.",
        f"Demand metric: {result.get('metric')}",
        "",
        "Attached you should find:",
        "  • Maps for the P-Median, LSCP, and MCLP models (PNG).",
        "  • KPI JSON files for each model (objective / coverage stats).",
        "",
        "You can also access these files on disk on the server under:",
        f"  {result.get('export_dir')}",
        "",
        "Best,",
        "Location Modeling Portal",
    ]
    msg.set_content("\n".join(body_lines))

    rel_paths = []
    for key in (
        "pmedian_map",
        "lscp_map",
        "mclp_map",
        "pmedian_kpis",
        "lscp_kpis",
        "mclp_kpis",
    ):
        p = result.get(key)
        if not p:
            continue
        rel_paths.append(p)

    base_dir = os.path.dirname(__file__)
    for rel in rel_paths:
        full_path = rel
        if not os.path.isabs(full_path):
            full_path = os.path.join(base_dir, rel)
        if not os.path.exists(full_path):
            print(f"[email] Attachment not found, skipping: {full_path}")
            continue

        filename = os.path.basename(full_path)
        with open(full_path, "rb") as f:
            data = f.read()

        if filename.lower().endswith(".png"):
            maintype, subtype = "image", "png"
        elif filename.lower().endswith(".json"):
            maintype, subtype = "application", "json"
        else:
            maintype, subtype = "application", "octet-stream"

        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        print(f"[email] Sent results email to {to_email}")


@app.route("/api/candidate-sites", methods=["GET"])
def get_candidate_sites():
    """
    Return counts of available candidate sites by type.
    In a real app, this would query the database.
    For now, return hardcoded counts matching the frontend.
    """
    sites = {
        "elementary": 124,
        "middle": 59,
        "high": 41,
        "libraries": 37,
    }
    return jsonify({"status": "ok", "sites": sites}), 200


@app.route("/api/scenarios/run", methods=["POST"])
def run_scenario():
    payload = request.get_json(force=True) or {}

    scenario_name = payload.get("scenarioName") or ""
    user_email = payload.get("email") or ""
    notify_email = bool(payload.get("notifyEmail", True))

    demand_metric_ui = payload.get("demandMetric")
    if not demand_metric_ui or demand_metric_ui not in DEMAND_METRIC_MAP:
        return jsonify(
            {
                "status": "error",
                "message": f"Invalid demand metric: {demand_metric_ui!r}",
            }
        ), 400

    metric_slug = DEMAND_METRIC_MAP[demand_metric_ui]

    try:
        p_value = int(payload.get("p", 5))
    except (TypeError, ValueError):
        p_value = 5

    try:
        coverage_miles = float(payload.get("coverageMiles", 5.0))
    except (TypeError, ValueError):
        coverage_miles = 5.0

    model_choice = payload.get("model")
    candidate_sites = payload.get("candidateSites", {})

    print(
        f"[api] Running scenario: name={scenario_name!r}, slug metric={metric_slug}, "
        f"p={p_value}, coverage_miles={coverage_miles}, model={model_choice}, "
        f"candidate_sites={candidate_sites}"
    )

    base_slug = slugify_scenario_name(scenario_name)
    scenario_slug = f"{base_slug}_{uuid.uuid4().hex[:6]}"

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "scenario_slug": scenario_slug,
        "user_email": user_email,
        "notify_email": notify_email,
        "created_at": time.time(),
    }

    # Start the background thread
    thread = threading.Thread(
        target=run_location_models_async,
        args=(job_id, metric_slug, p_value, coverage_miles, scenario_slug, model_choice)
    )
    thread.daemon = True
    thread.start()

    return (
        jsonify(
            {
                "status": "ok",
                "job_id": job_id,
                "message": "Analysis started. Check status with /api/jobs/{job_id}",
            }
        ),
        202,  
    )


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    if job_id not in jobs:
        return jsonify({"status": "error", "message": "Job not found"}), 404

    job = jobs[job_id]
    response = {
        "job_id": job_id,
        "status": job["status"],
        "scenario_slug": job["scenario_slug"],
    }

    if job["status"] == "completed":
        response["results_url"] = job["results_url"]
        response["backend"] = job["result"]
    elif job["status"] == "failed":
        response["error"] = job["error"]

    return jsonify(response), 200
from flask import send_from_directory

OUTPUT_BASE_DIR = "outputs_location_models_miles"


@app.route("/analysis/results/<scenario_slug>")
def view_results(scenario_slug):
    base_dir = os.path.join(OUTPUT_BASE_DIR, scenario_slug)

    if not os.path.exists(base_dir):
        return f"No results found for {scenario_slug}", 404

    files = []
    for root, _, filenames in os.walk(base_dir):
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), base_dir)
            files.append(rel)

    html = f"<h2>Results for scenario: {scenario_slug}</h2><ul>"
    for f in files:
        html += f'<li><a href="/analysis/files/{scenario_slug}/{f}">{f}</a></li>'
    html += "</ul>"

    return html
@app.route("/analysis/files/<scenario_slug>/<path:filename>")
def serve_result_file(scenario_slug, filename):
    return send_from_directory(
        os.path.join(OUTPUT_BASE_DIR, scenario_slug),
        filename,
        as_attachment=False,
    )


if __name__ == "__main__":
    app.run(port=5050, debug=True)
