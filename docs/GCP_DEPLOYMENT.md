# GCP Deployment Guide for GreekNN Risk System

This guide covers deploying the GreekNN Risk System on Google Cloud Platform.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Google Cloud Platform                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Cloud Run (API Service)                     │   │
│  │              greeknn-api:8000                           │   │
│  │                                                          │   │
│  │              Standalone - No External Dependencies       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Key Change**: The application now runs as a standalone container without PostgreSQL or Redis. All caching is done in-memory.

## Prerequisites

1. Google Cloud SDK installed and authenticated:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```

2. Project configured:
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```

3. Required APIs enabled:
   ```bash
   gcloud services enable cloudbuild.googleapis.com \
       run.googleapis.com \
       artifactregistry.googleapis.com
   ```

---

## Option 1: Cloud Run (Recommended)

Cloud Run is ideal for this FastAPI application - serverless, auto-scaling, pay-per-use.

### Step 1: Create Artifact Registry

```bash
# Create artifact registry repository
gcloud artifacts repositories create greeknn-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="GreekNN Risk System container images"

# Configure Docker authentication
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### Step 2: Build and Push Container

```bash
# Build the container
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/greeknn-repo/greeknn-api:latest .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/greeknn-repo/greeknn-api:latest
```

### Step 3: Deploy to Cloud Run

```bash
# Deploy to Cloud Run (standalone - no external dependencies)
gcloud run deploy greeknn-api \
    --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/greeknn-repo/greeknn-api:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --port=8000 \
    --min-instances=1 \
    --max-instances=10 \
    --cpu=2 \
    --memory=4Gi \
    --concurrency=80 \
    --timeout=300 \
    --set-env-vars="ENVIRONMENT=production" \
    --set-env-vars="LOG_LEVEL=INFO" \
    --set-env-vars="ENABLE_NEWS=false" \
    --set-env-vars="ENABLE_NLP=false"
```

### Step 4: Verify Deployment

```bash
# Check service status
gcloud run services describe greeknn-api --region=us-central1

# Get service URL
gcloud run services describe greeknn-api --region=us-central1 --format="value(status.url)"

# Test health endpoint
curl https://YOUR_SERVICE_URL/api/health
```

---

## Option 2: Google Kubernetes Engine (GKE)

For production-grade deployment with advanced orchestration.

### Step 1: Create GKE Cluster

```bash
# Create regional GKE cluster
gcloud container clusters create greeknn-cluster \
    --region=us-central1 \
    --node-pool-name=default-pool \
    --num-nodes=2 \
    --machine-type=n2-standard-4 \
    --disk-type=pd-ssd \
    --enable-autoscaling \
    --min-nodes=1 \
    --max-nodes=5
```

### Step 2: Build and Push Container

```bash
# Tag for GKE
docker tag greeknn-api:latest us-central1-docker.pkg.dev/YOUR_PROJECT_ID/greeknn-repo/greeknn-api:latest

# Push image
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/greeknn-repo/greeknn-api:latest
```

### Step 3: Deploy to GKE

```bash
# Apply Kubernetes deployment
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: greeknn-api
  labels:
    app: greeknn-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: greeknn-api
  template:
    metadata:
      labels:
        app: greeknn-api
    spec:
      containers:
      - name: greeknn-api
        image: us-central1-docker.pkg.dev/YOUR_PROJECT_ID/greeknn-repo/greeknn-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 60
EOF

# Create service
kubectl expose deployment greeknn-api --port 8000 --target-port 8000 --type LoadBalancer
```

### Step 4: Create Ingress

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: greeknn-ingress
  annotations:
    kubernetes.io/ingress.class: "gce"
spec:
  rules:
  - host: greeknn.YOUR_DOMAIN.com
    http:
      paths:
      - path: /*
        pathType: Prefix
        backend:
          service:
            name: greeknn-api
            port:
              number: 8000
EOF
```

---

## Option 3: Cloud Build CI/CD

Automated deployment pipeline.

### Create cloudbuild.yaml

```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:$COMMIT_SHA'
      - '.'
    env:
      - 'DOCKER_BUILDKIT=1'

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:$COMMIT_SHA'

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    args:
      - 'run'
      - 'deploy'
      - 'greeknn-api'
      - '--image'
      - 'us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:$COMMIT_SHA'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
    env:
      - 'PROJECT_ID=$PROJECT_ID'

images:
  - 'us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:$COMMIT_SHA'
```

### Trigger Build

```bash
# Submit build
gcloud builds submit --config=cloudbuild.yaml --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
```

---

## Monitoring & Observability

### Enable Cloud Monitoring

```bash
# Create notification channel
gcloud alpha monitoring channels create \
    --display-name="GreekNN Alerts" \
    --type=email

# View logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50
```

---

## Security Configuration

### Cloud Armor (WAF)

```bash
# Create security policy
gcloud compute security-policies create greeknn-waf-policy \
    --description="GreekNN WAF policy"

# Add rules for common attacks
gcloud compute security-policies rules create 1000 \
    --security-policy=greeknn-waf-policy \
    --expression="evaluatePreconfiguredExpr('xss-stable')" \
    --action=deny-403

# Attach to Cloud Run
gcloud run services update greeknn-api \
    --security-policy=greeknn-waf-policy \
    --region=us-central1
```

### Secret Manager

```bash
# Store API key in Secret Manager
echo -n "YOUR_NEWSAPI_KEY" | gcloud secrets create NEWSAPI_KEY --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding NEWSAPI_KEY \
    --member="serviceAccount:YOUR_SA@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

---

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Deployment environment | `production` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENABLE_NEWS` | Enable news ingestion | `false` |
| `ENABLE_NLP` | Enable NLP processing | `false` |
| `NEWSAPI_KEY` | NewsAPI key (optional) | *(use Secret Manager)* |

---

## Rollback Strategy

```bash
# Rollback Cloud Run to previous revision
gcloud run revisions list --service=greeknn-api --region=us-central1

# Deploy specific revision
gcloud run deploy greeknn-api \
    --revision=greeknn-api-XXXX \
    --region=us-central1

# GKE rollback
kubectl rollout undo deployment/greeknn-api
```

---

## Cost Optimization Tips

1. **Cloud Run**: Set appropriate `--min-instances` and `--max-instances`
2. **Memory**: The app uses in-memory caching, so no external Redis needed
3. **GKE**: Enable autoscaling with appropriate node limits

---

## Local Docker Testing

```bash
# Build and run locally
docker build -t greeknn-api:latest .
docker run -p 8000:8000 greeknn-api:latest

# Test health endpoint
curl http://localhost:8000/api/health
```

## Quick Start Commands

```bash
# Full deployment to Cloud Run
PROJECT_ID=project-c54accd5-10da-4b50-a34
REGION=us-central1

# 1. Build and push
docker build -t us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:latest .
docker push us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:latest

# 2. Deploy
gcloud run deploy greeknn-api \
    --image=us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:latest \
    --platform=managed \
    --region=$REGION \
    --allow-unauthenticated \
    --port=8000 \
    --min-instances=1 \
    --max-instances=10 \
    --cpu=2 \
    --memory=4Gi \
    --concurrency=80 \
    --timeout=300 \
    --set-env-vars="ENVIRONMENT=production" \
    --set-env-vars="LOG_LEVEL=INFO"

# 3. Verify
curl $(gcloud run services describe greeknn-api --region=$REGION --format="value(status.url)")/api/health
```

---

## Starting and Stopping Cloud (Cost Control)

### Cloud Run

**Stop (to stop incurring charges):**

```bash
# Option 1: Delete the service completely (irreversible, need to redeploy)
gcloud run services delete greeknn-api --region=us-central1

# Option 2: Set min-instances to 0 (service remains, billing is minimal)
gcloud run services update greeknn-api \
    --region=us-central1 \
    --min-instances=0

# Option 3: Limit max-instances to reduce maximum spending
gcloud run services update greeknn-api \
    --region=us-central1 \
    --max-instances=2
```

**Start (resume the service):**

```bash
# Deploy/redeploy to start fresh
gcloud run deploy greeknn-api \
    --image=us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --port=8000 \
    --min-instances=1 \
    --max-instances=10 \
    --cpu=2 \
    --memory=4Gi \
    --concurrency=80 \
    --timeout=300 \
    --set-env-vars="ENVIRONMENT=production" \
    --set-env-vars="LOG_LEVEL=INFO"

# Verify it's running
curl $(gcloud run services describe greeknn-api --region=us-central1 --format="value(status.url)")/api/health
```

### GKE

**Stop (to stop incurring charges):**

```bash
# Option 1: Delete the entire cluster (irreversible, need to recreate)
gcloud container clusters delete greeknn-cluster --region=us-central1

# Option 2: Resize to zero nodes (cluster remains, no nodes running)
gcloud container clusters resize greeknn-cluster \
    --region=us-central1 \
    --num-nodes=0

# Option 3: Delete just the deployment (keeps cluster running)
kubectl delete deployment greeknn-api

# Option 4: Delete service (releases LoadBalancer IP, keeps cluster)
kubectl delete service greeknn-api
```

**Start (resume the service):**

```bash
# Recreate cluster if deleted
gcloud container clusters create greeknn-cluster \
    --region=us-central1 \
    --node-pool-name=default-pool \
    --num-nodes=2 \
    --machine-type=n2-standard-4

# Redeploy the application
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: greeknn-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: greeknn-api
  template:
    metadata:
      labels:
        app: greeknn-api
    spec:
      containers:
      - name: greeknn-api
        image: us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:latest
        ports:
        - containerPort: 8000
EOF

# Expose service
kubectl expose deployment greeknn-api --port 8000 --target-port 8000 --type LoadBalancer
```

### Artifact Registry (Storage Costs)

**Remove to stop storage charges:**

```bash
# Delete repository (removes all container images - cannot be undone)
gcloud artifacts repositories delete greeknn-repo --location=us-central1
```

**Recreate when needed:**

```bash
# Recreate repository
gcloud artifacts repositories create greeknn-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="GreekNN Risk System container images"

# Push image again
docker push us-central1-docker.pkg.dev/$PROJECT_ID/greeknn-repo/greeknn-api:latest
```

### Verification Commands

```bash
# Check Cloud Run services status
gcloud run services list --region=us-central1

# Check GKE clusters status
gcloud container clusters list --region=us-central1

# Check Artifact Registry repositories
gcloud artifacts repositories list

# Check no running containers locally
docker ps
```

---

## Troubleshooting

### Repository Not Found Errors

If you receive "Repository not found" errors, verify the repository exists:

```bash
# List all Artifact Registry repositories
gcloud artifacts repositories list

# Create repository if it doesn't exist
gcloud artifacts repositories create greeknn-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="GreekNN Risk System container images"
```

### Image Path Reference

The image path format is:
```
[LOCATION]-docker.pkg.dev/[PROJECT_ID]/[REPOSITORY_NAME]/[IMAGE_NAME]
```

Example with your project:
```
us-central1-docker.pkg.dev/greek-nn-496508/greeknn-repo/greeknn-api:latest
```