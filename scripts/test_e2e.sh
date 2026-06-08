#!/usr/bin/env bash
# End-to-end test script for the GPU Job Scheduler.
# Usage: bash scripts/test_e2e.sh
#
# Prerequisites:
#   - docker compose up -d  (Postgres + Redis running)
#   - source .venv/bin/activate

set -euo pipefail

API="http://localhost:8000"
SAMPLE_FILE="scripts/sample_train.py"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GPU Job Scheduler — End-to-End Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# ── 1. Health check ────────────────────────────────────
echo "1. Health check..."
curl -sf "$API/health" | python3 -m json.tool
echo

# ── 2. Register ────────────────────────────────────────
echo "2. Registering test user..."
REGISTER_RESP=$(curl -sf -X POST "$API/auth/register" \
    -H "Content-Type: application/json" \
    -d '{
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123"
    }')
echo "$REGISTER_RESP" | python3 -m json.tool

TOKEN=$(echo "$REGISTER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_token'])")
echo "   Token: ${TOKEN:0:20}..."
echo

# ── 3. Login (verify it works) ─────────────────────────
echo "3. Logging in..."
LOGIN_RESP=$(curl -sf -X POST "$API/auth/login" \
    -H "Content-Type: application/json" \
    -d '{
        "username": "testuser",
        "password": "testpass123"
    }')
echo "$LOGIN_RESP" | python3 -m json.tool
echo

# ── 4. Submit Python file job ──────────────────────────
echo "4. Submitting sample_train.py..."
JOB_RESP=$(curl -sf -X POST "$API/jobs/python-file" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$SAMPLE_FILE" \
    -F 'metadata={"title":"E2E Test Training","description":"Sample training job for testing","requested_gpu_count":1,"requested_cpu_cores":2,"requested_memory_mb":512,"max_runtime_seconds":1200,"priority":3,"env_vars":[{"var_name":"EPOCHS","var_value":"3"},{"var_name":"LEARNING_RATE","var_value":"0.001"}]}')
echo "$JOB_RESP" | python3 -m json.tool

JOB_ID=$(echo "$JOB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   Job ID: $JOB_ID"
echo

# ── 5. List jobs ───────────────────────────────────────
echo "5. Listing jobs..."
curl -sf "$API/jobs" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

# ── 6. Get job details ─────────────────────────────────
echo "6. Job details..."
curl -sf "$API/jobs/$JOB_ID" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

# ── 7. Get job events ──────────────────────────────────
echo "7. Job events..."
curl -sf "$API/jobs/$JOB_ID/events" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

# ── 8. Wait for scheduler + worker ─────────────────────
echo "8. Waiting 10 seconds for scheduler + worker to process..."
echo "   (Make sure scheduler and worker are running in separate terminals)"
sleep 10
echo

# ── 9. Check job status after processing ───────────────
echo "9. Job status after processing..."
curl -sf "$API/jobs/$JOB_ID" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

# ── 10. Check events after processing ──────────────────
echo "10. Events after processing..."
curl -sf "$API/jobs/$JOB_ID/events" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

# ── 11. Check artifacts ────────────────────────────────
echo "11. Artifacts..."
curl -sf "$API/jobs/$JOB_ID/artifacts" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

# ── 12. Logout ─────────────────────────────────────────
echo "12. Logging out..."
curl -sf -X POST "$API/auth/logout" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Test complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
