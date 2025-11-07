# AI-Driven System for Classifying Skin Diseases from Images

**One-liner:** An AI-powered intake assistant that asks patient-friendly questions about a skin concern and returns a risk-oriented summary. (Research prototype — not a diagnostic tool.)

> **Medical disclaimer**  
> This project is for educational/research use. It does **not** provide medical advice and is **not** a diagnostic tool. Always consult a clinician.

---

## ✨ Features
- **Intake Chat (Gemini)** — collects ABCDE, symptoms, and change info using simple questions.
- **Rule-based triage signal** — summarizes risk indicators and suggests next key questions.
- **Lightweight Flask server** — runs locally; simple demo page included.

---

## 🧱 Project Structure
```
.
├─ data/
│  ├─ HAM10000_images_part_1/      # (optional) dataset folder you created
│  ├─ HAM10000_images_part_2/      # (optional) dataset folder you created
│  └─ index/                        # (unused for now)
│
├─ expertSystem/
│  ├─ app.py                        # Flask app (entry point)
│  ├─ chat.py                       # Gemini chat + tool-calls + rule logic
│  └─ indexdemo.html                # Minimal chat UI
│
├─ front-end/                       # Optional static pages (not required to run)
│  ├─ index.html, chat.html, ...    # (unused for now)
│
├─ src/
│  └─ query.py                      # Image search helpers (unused for now)
│
├─ .env                             # your API keys live here
└─ venv/                            # your virtual environment (local only)
```

---

## 🔧 Requirements
- **Python:** 3.13.5
- **Packages (chat only):**
  - `flask`
  - `python-dotenv`
  - `google-generativeai`
  - `pillow`
  - `numpy`
  - `pandas`

### Quick install
```bat
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install flask python-dotenv google-generativeai pillow numpy pandas
```

---

## 🔐 Environment
Create a `.env` file in the **repo root** with:
```env
GEMINI_API_KEY=YOUR_KEY_HERE
GEMINI_MODEL=gemini-2.0-flash
```

On startup you should see something like:
```
[dotenv] file: C:\Capstone\.env
[Gemini] Using model: gemini-2.0-flash
```

---

## ▶️ Run
From the repo root:
```bat
venv\Scripts\activate
python -m expertSystem.app
```

Open the demo UI:
```
http://127.0.0.1:3720/
```

---

## 🛣️ API (minimal)

### `POST /chat`
Send user text to the intake assistant.

- **Form field**: `text` (string)

**Example**
```bash
curl -X POST http://127.0.0.1:3720/chat -F "text=Hi, new spot on my chest"
```

**Response (example)**
```json
{
  "text": "assistant reply...",
  "findings": [
    {"label":"melanoma_risk","score":0.12},
    {"label":"benign_likelihood","score":0.88}
  ],
  "next_questions": ["..."],
  "safety_flags": ["not_a_diagnosis"]
}
```

### `GET /`
Serves `expertSystem/indexdemo.html` (simple chat page).

---

## 🧠 How it Works (short)
- The assistant uses Gemini to conduct an intake dialogue.
- When enough info is gathered, a local rule set computes a simple risk signal and suggests next questions.
- This build focuses on **chat only**. (Image retrieval and FAISS index are not included in this minimal setup.)

---

## 🧪 Troubleshooting
- **`ModuleNotFoundError: No module named 'dotenv'`** → `pip install python-dotenv`
- **`No API key found` or blank replies** → verify `.env` has `GEMINI_API_KEY` and restart the server
- **Port in use** → set `PORT` in `.env` (optional) or stop the other process using 3720

---

## 📜 License
_Add a license here (e.g., MIT)._

## 👥 Credits
_Add author names, course, and advisor (e.g., PFW CS 46000 — Dr. Hajiarbabi)._
