from flask import Flask, request, render_template, redirect, url_for, session
import sqlite3
import os
import requests
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DB_FILE = "survey.db"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

app.secret_key = os.getenv("SECRET_KEY", "replace_this_with_env_secret")

ADMIN_USERNAME = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "your_password_here")

HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY")


def create_table():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            location TEXT,
            sector TEXT,
            needs TEXT,
            feedback TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
create_table()


def get_groq_insight(location, sector):
    prompt = (
        f"Provide 3 top public companies or sectors to invest in {location} related to {sector}. "
        "For each, include the company name and a short description with max of 15 words. "
        "Also include a concise market insight paragraph shortly. If the sector or location is new or invalid, please reply politely that data is not correct. "
        "Format your response as a numbered list."
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
        short_text = (cleaned_text[:600] + "...") if len(cleaned_text) > 600 else cleaned_text
        return short_text

    header = f"🚀 Top Investment Opportunities in {location} – {sector} 💼"
    subheader = f"🔬 {sector} Sector Highlights:"

    market_insight = "🌟 Market Insight:\nThe sector is evolving rapidly with promising growth prospects driven by innovation, demand, and strategic developments."

    disclaimer = "\n\n*(Note: These insights are informational and reflect community activity; please perform your own research.)*"

    output = (
        f"{header}\n\n"
        f"{subheader}\n\n"
        + "\n\n".join(short_entries)
        + f"\n\n{market_insight}"
        + disclaimer
    )
    return output


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        hcaptcha_response = request.form.get('h-captcha-response')
        if not hcaptcha_response:
            return render_template("index.html", error="Please complete the CAPTCHA.", form=request.form)

        verify_url = 'https://hcaptcha.com/siteverify'
        data = {
            'secret': HCAPTCHA_SECRET_KEY,
            'response': hcaptcha_response
        }
        resp = requests.post(verify_url, data=data)
        result = resp.json()
        if not result.get('success'):
            return render_template("index.html", error="CAPTCHA validation failed, please try again.", form=request.form)

        name = request.form.get("name")
        email = request.form.get("email")
        location = request.form.get("location")
        if location == "Other":
            location_other = request.form.get("location_other", "").strip()
            if location_other:
                location = location_other
        sector = request.form.get("sector")
        needs = request.form.get("needs")
        feedback = request.form.get("feedback")

        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT INTO feedback (name, email, location, sector, needs, feedback) VALUES (?, ?, ?, ?, ?, ?)",
                (name, email, location, sector, needs, feedback)
            )

        full_ai_output = get_groq_insight(location, sector)
        short_output = shorten_ai_output(full_ai_output, location, sector)
        session['ai_output'] = short_output
        return redirect(url_for("thank_you"))

    return render_template("index.html")


@app.route("/thankyou", methods=["GET"])
def thank_you():
    ai_output = session.pop('ai_output', None)
    if ai_output is None:
        return redirect(url_for("index"))
    return render_template("thankyou.html", ai_output=ai_output)


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for("admin_panel"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/admin-feedback")
def admin_panel():
    if not session.get("logged_in"):
        return redirect(url_for("admin_login"))
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT name, email, location, sector, needs, feedback, ts FROM feedback ORDER BY ts DESC"
        ).fetchall()
    return render_template("results.html", rows=rows, enumerate=enumerate)


@app.route("/admin-logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


if __name__ == "__main__":
    app.run(debug=True)
