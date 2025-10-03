from flask import Flask, request, render_template
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def call_groq(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 512
    }

    response = requests.post(GROQ_API_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print("API ERROR:", response.text)
        return None

    result = response.json()
    return result["choices"][0]["message"]["content"]


def parse_ai_response(text):
    # Very simple parsing - split by lines, detect main sections, and format HTML
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    data = {
        "estimated_score": "",
        "required_score": "",
        "risk_level": "",
        "loan_decision": "",
        "key_points": [],
        "reasons": [],
        "note": ""
    }
    
    section = None
    for line in lines:
        # Parse Estimated Score
        if line.lower().startswith("estimated credit score"):
            data["estimated_score"] = line.split(":")[-1].strip()
        elif line.lower().startswith("score required for loan approval"):
            data["required_score"] = line.split(":")[-1].strip()
        elif line.lower().startswith("risk level"):
            data["risk_level"] = line.split(":")[-1].strip()
        elif line.lower().startswith("loan approval decision"):
            data["loan_decision"] = line.split(":")[-1].strip()
        elif line.lower().startswith("key points"):
            section = "key_points"
        elif line.lower().startswith("reasons for this loan decision"):
            section = "reasons"
        elif line.lower().startswith("note"):
            section = "note"
            data["note"] = line[len("note:"):].strip()
        else:
            if section == "key_points" and line.startswith("-"):
                data["key_points"].append(line[1:].strip())
            elif section == "reasons" and line.startswith("-"):
                data["reasons"].append(line[1:].strip())
            elif section == "note":
                data["note"] += " " + line

    return data


@app.route('/', methods=['GET', 'POST'])
def credit_simulator():
    error = None
    formatted_result = None
    name = ""

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        age = request.form.get('age', '').strip()
        income = request.form.get('income', '').strip()
        employment = request.form.get('employment', '').strip()
        debts = request.form.get('debts', '').strip()
        history = request.form.get('history', '').strip()
        missed = request.form.get('missed', '').strip()

        if not all([name, age, income, employment, debts, history, missed]):
            error = "Please fill all fields."
        else:
            prompt = f"""
You are an expert credit analyst. Given the following user data, generate a detailed credit report including:

- Estimated Credit Score (out of 850)
- Score Required for Loan Approval (assume 650)
- Risk Level (Low, Medium, High)
- Loan Approval Decision (Approved or Rejected)
- Key Points (short bullet points)
- Reasons for this loan decision (short bullet points)

Format the report clearly with each item on its own line, and prefix bullet points with '-'.

User Details:
Name: {name}
Age: {age}
Monthly Income: ₹{income}
Employment Status: {employment}
Total Current Debt: ₹{debts}
Credit History Length (years): {history}
Missed Payments in Last 12 Months: {missed}
"""
            ai_response = call_groq(prompt)
            if ai_response:
                parsed = parse_ai_response(ai_response)

                # Emoji map for risk and decision
                risk_emoji = {
                    "Low": "🟢",
                    "Medium": "🟠",
                    "High": "🔴"
                }
                decision_emoji = {
                    "Approved": "✅",
                    "Rejected": "❌"
                }

                formatted_result = {
                    "name": name,
                    "estimated_score": parsed["estimated_score"],
                    "required_score": parsed["required_score"],
                    "risk_level": parsed["risk_level"],
                    "risk_emoji": risk_emoji.get(parsed["risk_level"], ""),
                    "loan_decision": parsed["loan_decision"],
                    "decision_emoji": decision_emoji.get(parsed["loan_decision"], ""),
                    "key_points": parsed["key_points"],
                    "reasons": parsed["reasons"],
                    "note": parsed["note"]
                }
            else:
                error = "Failed to get response from AI."

    return render_template("credit_simulator.html", error=error, result=formatted_result, name=name)


if __name__ == "__main__":
    app.run(debug=True)
