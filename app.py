"""
YT-MP3 Flask Backend
Run: pip install flask yt-dlp flask-cors
     python app.py
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading

app = Flask(__name__)
CORS(app)  # Allow requests from the HTML frontend

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Track job status in memory
jobs = {}

# ── Helper ────────────────────────────────────────────────────────────────────
def get_output_path(job_id):
    return os.path.join(DOWNLOAD_DIR, job_id)

# ── Route: Get video info ─────────────────────────────────────────────────────
@app.route("/info", methods=["POST"])
def get_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            mins, secs = divmod(int(duration), 60)
            return jsonify({
                "title": info.get("title", "Unknown"),
                "uploader": info.get("uploader", "Unknown"),
                "duration": f"{mins}:{secs:02d}",
                "thumbnail": info.get("thumbnail", ""),
                "video_id": info.get("id", ""),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Route: Start conversion job ───────────────────────────────────────────────
@app.route("/convert", methods=["POST"])
def convert():
    data = request.json
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp3").lower()
    quality = data.get("quality", "192")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "progress": 0, "file": None, "error": None}

    def progress_hook(d):
        if d["status"] == "downloading":
            pct_str = d.get("_percent_str", "0%").strip().replace("%", "")
            try:
                jobs[job_id]["progress"] = float(pct_str)
                jobs[job_id]["status"] = "downloading"
            except ValueError:
                pass
        elif d["status"] == "finished":
            jobs[job_id]["status"] = "converting"
            jobs[job_id]["progress"] = 95

    def run_download():
        out_template = os.path.join(get_output_path(job_id) + ".%(ext)s")

        if fmt == "mp4":
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "outtmpl": out_template,
                "progress_hooks": [progress_hook],
                "quiet": True,
                "no_warnings": True,
            }
        else:
            codec_map = {"mp3": "mp3", "wav": "wav", "aac": "aac", "opus": "opus", "webm": "webm"}
            codec = codec_map.get(fmt, "mp3")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": out_template,
                "progress_hooks": [progress_hook],
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": quality,
                }],
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find the output file
            for ext in [fmt, "mp3", "mp4", "wav", "aac", "opus", "webm", "m4a"]:
                candidate = get_output_path(job_id) + f".{ext}"
                if os.path.exists(candidate):
                    jobs[job_id]["file"] = candidate
                    break

            jobs[job_id]["status"] = "done"
            jobs[job_id]["progress"] = 100

        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    thread = threading.Thread(target=run_download, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


# ── Route: Poll job status ────────────────────────────────────────────────────
@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ── Route: Download the file ──────────────────────────────────────────────────
@app.route("/download/<job_id>", methods=["GET"])
def download_file(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "File not ready"}), 404

    file_path = job["file"]
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File missing"}), 404

    filename = os.path.basename(file_path)
    return send_file(file_path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n🎵 YT-MP3 Backend running on port {port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
