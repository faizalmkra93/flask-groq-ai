from flask import Flask, request, render_template, make_response
import os
from dotenv import load_dotenv
import requests
import fitz  # PyMuPDF
import docx

# Load environment variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

app = Flask(__name__)

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB


# Function to send prompt to Groq API
def call_groq(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",  # ✅ Updated model
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }

    response = requests.post(GROQ_API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        print("❌ API ERROR:", response.text)
        response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]


# Extract text from file (.txt, .pdf, .docx)
def extract_text(file):
    filename = file.filename.lower()

    if filename.endswith('.txt'):
        return file.read().decode('utf-8')

    elif filename.endswith('.pdf'):
        text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text

    elif filename.endswith('.docx'):
        doc = docx.Document(file)
        return "\n".join([p.text for p in doc.paragraphs])

    else:
        raise ValueError("Unsupported file type.")


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return render_template("index.html", error="No file uploaded.")

    file = request.files['file']

    if file.filename == '':
        return render_template("index.html", error="No file selected.")

    if not file.filename.endswith(('.txt', '.pdf', '.docx')):
        return render_template("index.html", error="Invalid file type. Please upload .txt, .pdf or .docx files.")

    # File size check
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    if file_length > MAX_FILE_SIZE:
        return render_template("index.html", error="File size exceeds 1MB limit.")

    try:
        content = extract_text(file)

        if not content.strip():
            return render_template("index.html", error="File is empty or unreadable.")

        # Prompt 1: Summarize
        prompt1 = f"Summarize the following content:\n\n{content}"
        summary = call_groq(prompt1)

        # Prompt 2: Turn summary into to-do list
        prompt2 = f"Convert this summary into a detailed to-do list:\n\n{summary}"
        todo_list = call_groq(prompt2)

        return render_template("index.html", output=todo_list)

    except Exception as e:
        return render_template("index.html", error=f"Error: {str(e)}")


@app.route('/download', methods=['POST'])
def download():
    text = request.form.get("text", "")
    response = make_response(text)
    response.headers['Content-Disposition'] = 'attachment; filename=todo_list.txt'
    response.mimetype = 'text/plain'
    return response


if __name__ == '__main__':
    app.run(debug=True)
