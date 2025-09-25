import os
import threading
from flask import Flask, render_template, request, jsonify
from automation_new import run_automation, progress

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

automation_thread = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def start():
    global automation_thread, progress

    if progress["running"]:
        return jsonify({"error": "Automation already running"}), 400

    if "json_file" not in request.files:
        return jsonify({"error": "JSON file required"}), 400

    file = request.files["json_file"]
    sheet_name = request.form.get("sheet_name")

    if not sheet_name:
        return jsonify({"error": "Sheet name required"}), 400

    json_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(json_path)

    # Replace with your login creds
    email = os.getenv("LOGIN_EMAIL", "likepeas@gmail.com")
    password = os.getenv("LOGIN_PASSWORD", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    def task():
        run_automation(json_path, sheet_name, email, password)

    automation_thread = threading.Thread(target=task, daemon=True)
    automation_thread.start()
    return jsonify({"message": "Automation started"})


@app.route("/stop", methods=["POST"])
def stop():
    progress["running"] = False
    return jsonify({"message": "Stop signal sent"})


@app.route("/status")
def status():
    return jsonify(progress)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
