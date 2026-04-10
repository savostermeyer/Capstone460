# SkinAI Project - Quick Start

You need **3 terminals** running at the same time.

---

## TERMINAL 1️⃣ - Backend

```bash
cd back-end\src
python -m expertSystem.app
```

Wait for: `Running on http://localhost:3720`

---

## TERMINAL 2️⃣ - Frontend

```bash
cd front-end
npm run dev
```

Wait for: `Local: http://localhost:5173/` (or 5174)

---

## TERMINAL 3️⃣ - Server

```bash
npm i
node server.js
```

Wait for: `Server running on port 3000`

---

## Open in Browser

Once all 3 terminals show "running":

**http://localhost:5173/**

---

## To Stop

Press **Ctrl+C** in each terminal

Hardcoded doctor login:
user : doctor@skinai.com
password : doctor123

## Deplyoed Website

https://skinai-node-877350604703.us-central1.run.app/