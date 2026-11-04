#!/bin/bash
# ==============================================================================
# ApprovalLoop — Google Cloud Run & Cloud Scheduler Deployment Script
# ==============================================================================
set -e

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-""}
REGION=${REGION:-"us-central1"}
SERVICE_NAME="approval-loop"
GEMINI_MODEL=${GEMINI_MODEL:-"gemini-3.5-flash"}
APP_ENV=${APP_ENV:-"demo"} # "demo" | "production"
SCHEDULER_API_KEY=${SCHEDULER_API_KEY:-"dev-scheduler-secret-key"}
USE_SECRET_MANAGER=${USE_SECRET_MANAGER:-"false"}
AUTH_MODE=${AUTH_MODE:-"api-key"} # "api-key" (for web dashboard access) | "iam-oidc" (hardened private backend)
# PostgreSQL on Cloud SQL. CLOUD_SQL_INSTANCE is "project:region:instance". Over the Cloud Run socket, DATABASE_URL is e.g.
#   postgresql://USER:PASSWORD@/DBNAME?host=/cloudsql/project:region:instance
# With USE_SECRET_MANAGER=true the URL is read from the secret "database-url" instead.
CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE:-""}
DATABASE_URL=${DATABASE_URL:-""}

if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: GOOGLE_CLOUD_PROJECT environment variable is required."
    echo "Usage: GOOGLE_CLOUD_PROJECT=your-gcp-project-id [GEMINI_API_KEY=your-key] ./deploy.sh"
    exit 1
fi

echo "=================================================="
echo "Deploying ApprovalLoop to Google Cloud Run"
echo "Project:        $PROJECT_ID"
echo "Region:         $REGION"
echo "Service:        $SERVICE_NAME"
echo "Environment:    $APP_ENV"
echo "Gemini Model:   $GEMINI_MODEL"
echo "Auth Mode:      $AUTH_MODE"
echo "Secret Manager: $USE_SECRET_MANAGER"
echo "Cloud SQL:      ${CLOUD_SQL_INSTANCE:-none (in-memory storage)}"
echo "=================================================="

if [ "$APP_ENV" = "production" ] && [ -z "$CLOUD_SQL_INSTANCE" ]; then
    echo "ERROR: production needs PostgreSQL. Set CLOUD_SQL_INSTANCE, plus DATABASE_URL or the database-url secret."
    exit 1
fi
CLOUD_SQL_FLAG=""
if [ -n "$CLOUD_SQL_INSTANCE" ]; then
    CLOUD_SQL_FLAG="--add-cloudsql-instances $CLOUD_SQL_INSTANCE"
fi

# 1. Build and deploy container to Cloud Run
ALLOW_UNAUTH="--allow-unauthenticated"
if [ "$AUTH_MODE" = "iam-oidc" ] && [ "$APP_ENV" = "production" ]; then
    ALLOW_UNAUTH="--no-allow-unauthenticated"
fi

if [ "$USE_SECRET_MANAGER" = "true" ]; then
    echo "Configuring Cloud Run with Google Cloud Secret Manager secrets..."
    gcloud run deploy $SERVICE_NAME \
        --source . \
        --platform managed \
        --region $REGION \
        --project $PROJECT_ID \
        $ALLOW_UNAUTH $CLOUD_SQL_FLAG \
        --set-env-vars APP_ENV=$APP_ENV,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GEMINI_MODEL=$GEMINI_MODEL \
        --set-secrets GEMINI_API_KEY=gemini-api-key:latest,SCHEDULER_API_KEY=scheduler-api-key:latest,DATABASE_URL=database-url:latest
else
    echo "Configuring Cloud Run with environment variables..."
    ENV_VARS="APP_ENV=$APP_ENV,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GEMINI_MODEL=$GEMINI_MODEL,SCHEDULER_API_KEY=$SCHEDULER_API_KEY"
    if [ -n "$GEMINI_API_KEY" ]; then
        ENV_VARS="$ENV_VARS,GEMINI_API_KEY=$GEMINI_API_KEY"
    fi
    if [ -n "$DATABASE_URL" ]; then
        ENV_VARS="$ENV_VARS,DATABASE_URL=$DATABASE_URL"
    fi

    gcloud run deploy $SERVICE_NAME \
        --source . \
        --platform managed \
        --region $REGION \
        --project $PROJECT_ID \
        $ALLOW_UNAUTH $CLOUD_SQL_FLAG \
        --set-env-vars "$ENV_VARS"
fi

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --project $PROJECT_ID --format 'value(status.url)')
echo "Service deployed successfully at: $SERVICE_URL"

# 2. Configure Cloud Scheduler Job for autonomous ticks (1-minute standard cron schedule)
JOB_NAME="approval-loop-tick"
echo "Creating/updating Google Cloud Scheduler job: $JOB_NAME (Schedule: */1 * * * *)"

if [ "$AUTH_MODE" = "iam-oidc" ]; then
    SERVICE_ACCOUNT="approval-loop-invoker@$PROJECT_ID.iam.gserviceaccount.com"
    if gcloud scheduler jobs describe $JOB_NAME --location $REGION --project $PROJECT_ID &>/dev/null; then
        gcloud scheduler jobs update http $JOB_NAME \
            --location $REGION \
            --project $PROJECT_ID \
            --schedule "*/1 * * * *" \
            --uri "$SERVICE_URL/api/tick" \
            --http-method POST \
            --oidc-service-account-email "$SERVICE_ACCOUNT" \
            --headers "X-API-Key=$SCHEDULER_API_KEY"
    else
        gcloud scheduler jobs create http $JOB_NAME \
            --location $REGION \
            --project $PROJECT_ID \
            --schedule "*/1 * * * *" \
            --uri "$SERVICE_URL/api/tick" \
            --http-method POST \
            --oidc-service-account-email "$SERVICE_ACCOUNT" \
            --headers "X-API-Key=$SCHEDULER_API_KEY"
    fi
else
    if gcloud scheduler jobs describe $JOB_NAME --location $REGION --project $PROJECT_ID &>/dev/null; then
        gcloud scheduler jobs update http $JOB_NAME \
            --location $REGION \
            --project $PROJECT_ID \
            --schedule "*/1 * * * *" \
            --uri "$SERVICE_URL/api/tick" \
            --http-method POST \
            --headers "X-API-Key=$SCHEDULER_API_KEY"
    else
        gcloud scheduler jobs create http $JOB_NAME \
            --location $REGION \
            --project $PROJECT_ID \
            --schedule "*/1 * * * *" \
            --uri "$SERVICE_URL/api/tick" \
            --http-method POST \
            --headers "X-API-Key=$SCHEDULER_API_KEY"
    fi
fi

echo "=================================================="
echo "Deployment Complete!"
echo "Cloud Run Service:     $SERVICE_URL"
echo "Cloud Scheduler Job:   $JOB_NAME (* * * * *)"
echo "Autonomous Loop:       ACTIVE"
echo "=================================================="

