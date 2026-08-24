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
echo "=================================================="

# 1. Build and deploy container to Cloud Run
ALLOW_UNAUTH="--allow-unauthenticated"
if [ "$APP_ENV" = "production" ] || [ "$AUTH_MODE" = "iam-oidc" ]; then
    ALLOW_UNAUTH="--no-allow-unauthenticated"
fi

if [ "$USE_SECRET_MANAGER" = "true" ]; then
    echo "Configuring Cloud Run with Google Cloud Secret Manager secrets..."
    gcloud run deploy $SERVICE_NAME \
        --source . \
        --platform managed \
        --region $REGION \
        --project $PROJECT_ID \
        $ALLOW_UNAUTH \
        --set-env-vars APP_ENV=$APP_ENV,USE_FIRESTORE=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GEMINI_MODEL=$GEMINI_MODEL \
        --set-secrets GEMINI_API_KEY=gemini-api-key:latest,SCHEDULER_API_KEY=scheduler-api-key:latest
else
    echo "Configuring Cloud Run with environment variables..."
    ENV_VARS="APP_ENV=$APP_ENV,USE_FIRESTORE=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GEMINI_MODEL=$GEMINI_MODEL,SCHEDULER_API_KEY=$SCHEDULER_API_KEY"
    if [ -n "$GEMINI_API_KEY" ]; then
        ENV_VARS="$ENV_VARS,GEMINI_API_KEY=$GEMINI_API_KEY"
    fi

    gcloud run deploy $SERVICE_NAME \
        --source . \
        --platform managed \
        --region $REGION \
        --project $PROJECT_ID \
        $ALLOW_UNAUTH \
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

