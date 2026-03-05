# Google Cloud Deployment Guide (Cloud Run)

This project is deployed as a **single Cloud Run service** running `server.js` (Node/Express), which serves:
- API routes (upload/auth/chat)
- built frontend files from `front-end/dist`

## 1) Prerequisites

- Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install
- Authenticate and select project:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

- Enable required services:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

## 2) Build frontend locally once (optional sanity check)

```bash
cd front-end
npm install
npm run build
cd ..
```

## 3) Set required environment variables

Your app requires:
- `MONGODB_URI`
- `GEMINI_API_KEY`

Recommended: store secrets in Secret Manager.

```bash
echo -n "YOUR_MONGODB_URI" | gcloud secrets create mongodb-uri --data-file=-
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
```

If the secrets already exist, add new versions:

```bash
echo -n "YOUR_MONGODB_URI" | gcloud secrets versions add mongodb-uri --data-file=-
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
```

## 4) Deploy from source (recommended)

From repo root:

```bash
gcloud run deploy capstone \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --set-secrets MONGODB_URI=mongodb-uri:latest,GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars GEMINI_MODEL=gemini-2.0-flash
```

## 5) Verify

```bash
gcloud run services describe capstone --region us-central1 --format="value(status.url)"
gcloud run logs read capstone --region us-central1 --limit 100
```

Then open the service URL and test:
- `/api/health`
- frontend pages served from `/`

## 6) Deploy with Cloud Build config (optional CI)

This repo includes `cloudbuild.yaml`. Create Artifact Registry repo once:

```bash
gcloud artifacts repositories create capstone \
  --repository-format=docker \
  --location=us-central1
```

Run build/deploy:

```bash
gcloud builds submit --config cloudbuild.yaml
```

## Notes

- `app.yaml` is for App Engine and is **not required** for this Cloud Run path.
- Cloud Run provides `PORT`; `server.js` already respects it.
- If you need private API access, redeploy with `--no-allow-unauthenticated`.
