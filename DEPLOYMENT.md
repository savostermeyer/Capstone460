# Google Cloud Deployment Guide

## Prerequisites

1. **Google Cloud Project**
   - Create a project: https://console.cloud.google.com
   - Note your `PROJECT_ID`

2. **Google Cloud CLI**
   ```bash
   # Install from: https://cloud.google.com/sdk/docs/install
   # Verify installation
   gcloud --version
   ```

3. **Authentication**
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

4. **Enable APIs**
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   gcloud services enable secretmanager.googleapis.com
   ```

---

## Option 1: Deploy to Cloud Run (Recommended)

### Step 1: Store Gemini API Key as Secret
```bash
# Create secret
echo "YOUR_GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-

# Grant Cloud Run access to secret
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:YOUR_PROJECT_ID@appspot.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

### Step 2: Deploy from Source
```bash
cd C:\Capstone

gcloud run deploy capstone \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --set-env-vars "GEMINI_API_KEY=YOUR_GEMINI_API_KEY" \
  --max-instances 10
```

### Step 3: Verify Deployment
```bash
# Get the service URL
gcloud run services describe capstone --region us-central1

# Test the service
curl https://capstone-XXXXX.run.app/
```

---

## Option 2: Deploy with Container Registry (CI/CD)

### Step 1: Build and Push Image
```bash
# Configure Docker
gcloud auth configure-docker gcr.io

# Build image
docker build -t gcr.io/YOUR_PROJECT_ID/capstone:latest .

# Push to Container Registry
docker push gcr.io/YOUR_PROJECT_ID/capstone:latest
```

### Step 2: Deploy from Image
```bash
gcloud run deploy capstone \
  --image gcr.io/YOUR_PROJECT_ID/capstone:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --set-env-vars "GEMINI_API_KEY=YOUR_GEMINI_API_KEY" \
  --max-instances 10
```

---

## Option 3: Deploy with GitHub Actions (Automated)

### Step 1: Create Service Account
```bash
# Create service account
gcloud iam service-accounts create capstone-deploy \
  --display-name="Capstone Deployment"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:capstone-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/run.admin

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:capstone-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.admin

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member=serviceAccount:capstone-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/artifactregistry.admin
```

### Step 2: Create and Download Service Account Key
```bash
gcloud iam service-accounts keys create capstone-key.json \
  --iam-account=capstone-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### Step 3: Add to GitHub Secrets
1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Add these secrets:
   - `GCP_PROJECT_ID`: YOUR_PROJECT_ID
   - `GCP_SA_KEY`: (paste contents of capstone-key.json)
   - `GEMINI_API_KEY`: YOUR_GEMINI_API_KEY

### Step 4: Create `.github/workflows/deploy.yml`
```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [ main, dBranch ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v1
        with:
          project_id: ${{ secrets.GCP_PROJECT_ID }}
          service_account_key: ${{ secrets.GCP_SA_KEY }}
          export_default_credentials: true

      - name: Build and Push Docker image
        run: |
          gcloud builds submit \
            --tag gcr.io/${{ secrets.GCP_PROJECT_ID }}/capstone:latest

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy capstone \
            --image gcr.io/${{ secrets.GCP_PROJECT_ID }}/capstone:latest \
            --platform managed \
            --region us-central1 \
            --allow-unauthenticated \
            --memory 1Gi \
            --timeout 600 \
            --set-env-vars "GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}" \
            --max-instances 10
```

---

## Configuration Options

### Environment Variables
- `GEMINI_API_KEY` (required) - Your Google Gemini API key
- `GEMINI_MODEL` (optional) - Model name (default: `gemini-2.0-flash`)
- `PORT` (set by Cloud Run) - Server port (default: 8080)

### Resource Settings
- **Memory**: 1Gi (recommended for your app)
- **CPU**: Shared (sufficient for Flask app)
- **Timeout**: 600 seconds (for long-running chat requests)
- **Max instances**: 10 (auto-scales based on traffic)

### Scaling
Cloud Run automatically scales based on traffic. To adjust:
```bash
gcloud run deploy capstone \
  --min-instances 1 \
  --max-instances 20 \
  --region us-central1
```

---

## Monitoring and Logs

### View Logs
```bash
# Real-time logs
gcloud run logs read capstone --region us-central1 --follow

# Filter by date/time
gcloud run logs read capstone \
  --region us-central1 \
  --limit 100
```

### Monitor Performance
- Visit: https://console.cloud.google.com/run
- Check: Memory usage, request count, response times, error rates

---

## Troubleshooting

### Build Fails
```bash
# Check Docker file
docker build -t capstone:test .

# Test locally first
docker run -p 8080:8080 -e GEMINI_API_KEY=test capstone:test
```

### API Key Issues
```bash
# Verify secret is accessible
gcloud secrets describe gemini-api-key
gcloud secrets versions access latest --secret="gemini-api-key"
```

### Cold Start Issues
- Cloud Run instances shut down after 15 minutes of inactivity
- First request after shutdown takes ~5-10 seconds
- Use Cloud Tasks to keep warm if needed

---

## Costs

- **Free tier**: 2 million requests/month, 360k GB-seconds
- **Beyond free**: ~$0.40 per million requests + compute time
- **Estimate**: ~$5-10/month for typical usage

---

## Security Best Practices

1. ✅ Use Secret Manager for API keys
2. ✅ Enable authentication for sensitive endpoints if needed
3. ✅ Set `--no-allow-unauthenticated` for production APIs
4. ✅ Use VPC for database connections
5. ✅ Enable Cloud Audit Logs
6. ✅ Use service accounts instead of user credentials

---

## Next Steps

1. Deploy to Cloud Run using Option 1 (easiest)
2. Test endpoints: `https://capstone-XXXXX.run.app/`
3. Monitor logs and performance
4. Set up GitHub Actions for automatic deployments
5. Configure custom domain (optional)

---

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Python on Google Cloud](https://cloud.google.com/python/docs)
