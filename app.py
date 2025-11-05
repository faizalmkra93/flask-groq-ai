from flask import Flask, request, render_template, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import re
from dotenv import load_dotenv
from io import StringIO
import csv
from datetime import datetime
import pytz

# Load environment variables
load_dotenv()

app = Flask(__name__)

# --- Configuration ---
app.secret_key = os.getenv("SECRET_KEY", "replace_this_with_env_secret")

# Use DATABASE_URL from .env (already in postgresql+pg8000:// format)
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("⚠️  Warning: DATABASE_URL not set. Please check your .env file or Railway settings.")
    db_url = "sqlite:///fallback.db"

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize DB
db = SQLAlchemy(app)

# --- Groq AI ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# --- Admin credentials ---
ADMIN_USERNAME = os.getenv("ADMIN_USER")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS")

HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY")

# --- Database Model ---
class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200))
    location = db.Column(db.String(200))
    risk = db.Column(db.String(100))
    investment_amount = db.Column(db.String(100))
    asset_types = db.Column(db.String(300))
    sector = db.Column(db.String(200))
    needs = db.Column(db.String(500))
    feedback = db.Column(db.Text)
    ts = db.Column(db.DateTime, default=datetime.utcnow)

# Create the table if it doesn't exist
with app.app_context():
    db.create_all()

# --- Helper Functions ---
def get_groq_insight(location, sector):
    prompt = (
        f"Provide 3 top public companies or sectors to invest in {location} related to {sector}. "
        "Include company name and short description (max 15 words). "
        "Also include a concise market insight paragraph. "
        "Format as numbered list."
    )
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 400
    }
    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(AI insight unavailable: {str(e)})"


def shorten_ai_output(full_text, location, sector):
    cleaned_text = full_text.replace("**", "")
    cleaned_text = re.sub(r"As a neutral AI.*?before making any investment decisions\.", "", cleaned_text, flags=re.DOTALL).strip()

    entries = re.findall(r"(\d+\..*?)(?=\n\d+\.|$)", cleaned_text, flags=re.DOTALL)
    short_entries = []
    for entry in entries[:3]:
        sentences = entry.strip().split(". ")
        short_desc = ". ".join(sentences[:2]).replace("\n", " ").strip()
        short_entries.append(short_desc)

    if not short_entries:
        return (cleaned_text[:600] + "...") if len(cleaned_text) > 600 else cleaned_text

    header = f"🚀 Top Investment Opportunities in {location} – {sector} 💼"
    subheader = f"🔬 {sector} Sector Highlights:"
    market_insight = "🌟 Market Insight:\nThe sector is evolving rapidly with promising growth prospects."
    disclaimer = "\n\n*(Note: These insights are informational; perform your own research.)*"

    return f"{header}\n\n{subheader}\n\n" + "\n\n".join(short_entries) + f"\n\n{market_insight}{disclaimer}"


class FormDict(dict):
    def getlist(self, key):
        val = self.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]


# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        hcaptcha_response = request.form.get('h-captcha-response')
        if not hcaptcha_response:
            return render_template("index.html", error="Please complete the CAPTCHA.", form=FormDict(request.form))

        verify_url = 'https://hcaptcha.com/siteverify'
        data = {'secret': HCAPTCHA_SECRET_KEY, 'response': hcaptcha_response}
        resp = requests.post(verify_url, data=data)
        if not resp.json().get('success'):
            return render_template("index.html", error="CAPTCHA validation failed.", form=FormDict(request.form))

        # Collect form data
        name = request.form.get("name")
        email = request.form.get("email")
        location = request.form.get("location")
        if location == "Other":
            location = request.form.get("location_other", "").strip() or location
        risk = request.form.get("risk")
        investment_amount = request.form.get("investment_amount")
        asset_types = ", ".join(request.form.getlist("asset_types") or [])
        sector = request.form.get("sector")
        needs = request.form.get("needs")
        feedback = request.form.get("feedback")

        # Save feedback
        fb = Feedback(
            name=name, email=email, location=location, risk=risk,
            investment_amount=investment_amount, asset_types=asset_types,
            sector=sector, needs=needs, feedback=feedback
        )
        db.session.add(fb)
        db.session.commit()

        full_ai_output = get_groq_insight(location, sector)
        short_output = shorten_ai_output(full_ai_output, location, sector)
        session['ai_output'] = short_output
        return redirect(url_for("thank_you"))

    return render_template("index.html", form=FormDict())


@app.route("/thankyou")
def thank_you():
    ai_output = session.pop('ai_output', None)
    if ai_output is None:
        return redirect(url_for("index"))
    return render_template("thankyou.html", ai_output=ai_output)


@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


@app.route("/cookie-policy")
def cookie_policy():
    return render_template("cookie_policy.html")


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for("admin_panel"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/admin-feedback")
def admin_panel():
    if not session.get("logged_in"):
        return redirect(url_for("admin_login"))

    rows = Feedback.query.order_by(Feedback.ts.desc()).all()
    india_tz = pytz.timezone("Asia/Kolkata")
    formatted_rows = [
        (
            row.id, row.name, row.email, row.location, row.risk,
            row.investment_amount, row.asset_types, row.sector,
            row.needs, row.feedback, row.ts.replace(tzinfo=pytz.utc).astimezone(india_tz).strftime("%d-%m-%Y %I:%M %p")
        ) for row in rows
    ]
    return render_template("results.html", rows=formatted_rows, enumerate=enumerate)


@app.route("/admin-feedback/download")
def admin_feedback_download():
    if not session.get("logged_in"):
        return redirect(url_for("admin_login"))

    rows = Feedback.query.order_by(Feedback.ts.desc()).all()
    india_tz = pytz.timezone("Asia/Kolkata")
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID", "Name", "Email", "Location", "Risk Tolerance", "Investment Amount", "Asset Types", "Sector", "Needs", "Feedback", "Timestamp (IST)"])
    for row in rows:
        local_ts = row.ts.replace(tzinfo=pytz.utc).astimezone(india_tz)
        cw.writerow([row.id, row.name, row.email, row.location, row.risk,
                     row.investment_amount, row.asset_types, row.sector,
                     row.needs, row.feedback, local_ts.strftime("%d-%m-%Y %I:%M %p")])

    response = make_response(si.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=survey_feedback.csv"
    response.headers["Content-type"] = "text/csv"
    return response


@app.route("/admin-logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


if __name__ == "__main__":
    # Bind to Railway's port and disable debug for production
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
