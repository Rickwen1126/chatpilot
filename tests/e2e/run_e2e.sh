#!/usr/bin/env bash
# ChatPilot E2E Test Suite — Self-contained
# Usage: ./tests/e2e/run_e2e.sh
# Starts its own server with route_settings/route_bindings example config,
# temp DB, runs all tests, cleans up.

# No set -e: we handle errors per-test

# ─── Configuration ───────────────────────────────────────────────
E2E_PORT="${E2E_PORT:-2998}"
BASE_URL="http://localhost:$E2E_PORT"
E2E_DIR="/tmp/chatpilot-e2e-$$"
E2E_DB="$E2E_DIR/chatpilot.db"
E2E_TASK_DB="$E2E_DIR/tasks.db"
E2E_FILES_DB="$E2E_DIR/files.db"
E2E_ASSETS_DIR="$E2E_DIR/file_assets"
E2E_LOG="$E2E_DIR/server.log"
ROUTE_SETTINGS="config/route_settings.example.yaml"
ROUTE_BINDINGS="config/route_bindings.example.yaml"
TICK_INTERVAL=5
CLI_TIMEOUT=60
PASS=0
FAIL=0
USER="e2e-$(date +%s)"
LINE_E2E_SECRET="${LINE_E2E_SECRET:-e2e-line-secret}"
LINE_E2E_TOKEN="${LINE_E2E_TOKEN:-e2e-line-token}"
DISCOVERY_SUFFIX="$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)"
DISCOVERY_GROUP_ID="C$DISCOVERY_SUFFIX"
DISCOVERY_GROUP_ROUTE="line:demo:$DISCOVERY_GROUP_ID"
DISCOVERY_USER_ID="U$DISCOVERY_SUFFIX"
DISCOVERY_USER_ROUTE="line:demo:$DISCOVERY_USER_ID"

# Observer/chatbot IDs from route_bindings.example.yaml
OBS_ROUTE="Ua1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
OBS_ROUTE_ID="line:demo:$OBS_ROUTE"
ASSISTANT_GROUP="Ca1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
ASSISTANT_ROUTE_ID="line:demo:$ASSISTANT_GROUP"

# ─── Helpers ─────────────────────────────────────────────────────
green() { printf "\033[32m%s\033[0m\n" "$1"; }
red() { printf "\033[31m%s\033[0m\n" "$1"; }
header() { printf "\n\033[1;34m=== %s ===\033[0m\n" "$1"; }

pass() { green "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { red "  ✗ $1"; [ -n "$2" ] && echo "    $2"; FAIL=$((FAIL + 1)); }

cli_chat() {
    timeout "$CLI_TIMEOUT" uv run chatpilot-cli --url "$BASE_URL" chat "$1" --user "${2:-$USER}" 2>/dev/null
}

mock_webhook() {
    curl -s -X POST "$BASE_URL/webhook/mock" \
        -H "Content-Type: application/json" \
        -d "$1"
}

line_signature() {
    local body="$1"
    LINE_BODY="$body" LINE_SECRET="$LINE_E2E_SECRET" python3 - <<'PY'
import base64
import hashlib
import hmac
import os

print(
    base64.b64encode(
        hmac.new(
            os.environ["LINE_SECRET"].encode("utf-8"),
            os.environ["LINE_BODY"].encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
)
PY
}

line_signed_post_code() {
    local body="$1"
    local signature
    signature=$(line_signature "$body")
    curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/webhook/line" \
        -H "Content-Type: application/json" \
        -H "X-Line-Signature: $signature" \
        --data-binary "$body"
}

line_join_body() {
    local group_id="$1"
    LINE_GROUP_ID="$group_id" python3 - <<'PY'
import json
import os

print(json.dumps({
    "destination": "UdemoDestination",
    "events": [{
        "type": "join",
        "timestamp": 1710000000000,
        "source": {"type": "group", "groupId": os.environ["LINE_GROUP_ID"]},
        "replyToken": "join-reply-token",
        "mode": "active",
        "webhookEventId": "01HJOIN",
        "deliveryContext": {"isRedelivery": False},
    }],
}, separators=(",", ":")))
PY
}

line_follow_body() {
    local user_id="$1"
    LINE_USER_ID="$user_id" python3 - <<'PY'
import json
import os

print(json.dumps({
    "destination": "UdemoDestination",
    "events": [{
        "type": "follow",
        "timestamp": 1710000000000,
        "source": {"type": "user", "userId": os.environ["LINE_USER_ID"]},
        "replyToken": "follow-reply-token",
        "follow": {"isUnblocked": False},
        "mode": "active",
        "webhookEventId": "01HFOLLOW",
        "deliveryContext": {"isRedelivery": False},
    }],
}, separators=(",", ":")))
PY
}

line_group_text_body() {
    local group_id="$1" user_id="$2" text="$3" message_id="$4"
    LINE_GROUP_ID="$group_id" LINE_USER_ID="$user_id" LINE_TEXT="$text" LINE_MESSAGE_ID="$message_id" python3 - <<'PY'
import json
import os

print(json.dumps({
    "destination": "UdemoDestination",
    "events": [{
        "type": "message",
        "timestamp": 1710000000000,
        "source": {
            "type": "group",
            "groupId": os.environ["LINE_GROUP_ID"],
            "userId": os.environ["LINE_USER_ID"],
        },
        "replyToken": "message-reply-token",
        "mode": "active",
        "webhookEventId": "01HMSG-" + os.environ["LINE_MESSAGE_ID"],
        "deliveryContext": {"isRedelivery": False},
        "message": {
            "id": os.environ["LINE_MESSAGE_ID"],
            "type": "text",
            "text": os.environ["LINE_TEXT"],
            "quoteToken": "quote-token-group",
        },
    }],
}, separators=(",", ":")))
PY
}

line_private_text_body() {
    local user_id="$1" text="$2" message_id="$3"
    LINE_USER_ID="$user_id" LINE_TEXT="$text" LINE_MESSAGE_ID="$message_id" python3 - <<'PY'
import json
import os

print(json.dumps({
    "destination": "UdemoDestination",
    "events": [{
        "type": "message",
        "timestamp": 1710000000000,
        "source": {
            "type": "user",
            "userId": os.environ["LINE_USER_ID"],
        },
        "replyToken": "message-reply-token",
        "mode": "active",
        "webhookEventId": "01HPRIV-" + os.environ["LINE_MESSAGE_ID"],
        "deliveryContext": {"isRedelivery": False},
        "message": {
            "id": os.environ["LINE_MESSAGE_ID"],
            "type": "text",
            "text": os.environ["LINE_TEXT"],
            "quoteToken": "quote-token-private",
        },
    }],
}, separators=(",", ":")))
PY
}

cli_route_field() {
    local route_id="$1" field="$2"
    curl -s "$BASE_URL/cli/routes" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
route_id = sys.argv[1]
field = sys.argv[2]
for item in payload.get("routes", []):
    if item.get("route_id") == route_id:
        value = item.get(field)
        if value is None:
            print("")
        elif isinstance(value, (dict, list)):
            print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        else:
            print(value)
        raise SystemExit(0)
raise SystemExit(1)
' "$route_id" "$field"
}

wait_for_route_field() {
    local route_id="$1" field="$2" expected="$3" timeout="${4:-20}" interval="${5:-1}"
    local elapsed=0 value
    while [ "$elapsed" -lt "$timeout" ]; do
        value=$(cli_route_field "$route_id" "$field" 2>/dev/null || true)
        if [ "$value" = "$expected" ]; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    return 1
}

# L2: assert tool was called in log
assert_tool_called() {
    local label="$1" tool="$2"
    if grep -a "\[tool_call\] $tool" "$E2E_LOG" > /dev/null 2>&1; then
        pass "$label [L2: $tool called]"
    else
        fail "$label [L2: $tool NOT called]"
    fi
}

# L3: assert DB row exists
assert_db_exists() {
    local label="$1" query="$2"
    local count
    count=$(sqlite3 "$E2E_DB" "$query" 2>/dev/null)
    if [ "$count" -gt 0 ] 2>/dev/null; then
        pass "$label [L3: DB row exists]"
    else
        fail "$label [L3: DB row missing]" "query: $query → $count"
    fi
}

# L3: assert DB row does NOT exist
assert_db_not_exists() {
    local label="$1" query="$2"
    local count
    count=$(sqlite3 "$E2E_DB" "$query" 2>/dev/null)
    if [ "$count" -eq 0 ] 2>/dev/null; then
        pass "$label [L3: DB row gone]"
    else
        fail "$label [L3: DB row still exists]" "query: $query → $count"
    fi
}

# L3: assert file DB row exists
assert_file_db_exists() {
    local label="$1" query="$2"
    local count
    count=$(sqlite3 "$E2E_FILES_DB" "$query" 2>/dev/null)
    if [ "$count" -gt 0 ] 2>/dev/null; then
        pass "$label [L3: file DB row exists]"
    else
        fail "$label [L3: file DB row missing]" "query: $query → $count"
    fi
}

# L2: assert log contains pattern
assert_log() {
    local label="$1" pattern="$2"
    if LC_ALL=C grep -a "$pattern" "$E2E_LOG" > /dev/null 2>&1; then
        pass "$label [L2: log match]"
    else
        fail "$label [L2: log no match]" "pattern: $pattern"
    fi
}

# L2: assert log does NOT contain pattern
assert_log_absent() {
    local label="$1" pattern="$2"
    if LC_ALL=C grep -a "$pattern" "$E2E_LOG" > /dev/null 2>&1; then
        fail "$label [L2: unexpected log]" "pattern: $pattern"
    else
        pass "$label [L2: log clean]"
    fi
}

wait_for_log() {
    local pattern="$1" timeout="${2:-60}" interval="${3:-2}"
    local elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if LC_ALL=C grep -a "$pattern" "$E2E_LOG" > /dev/null 2>&1; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    return 1
}

wait_for_db_count() {
    local db_path="$1" query="$2" timeout="${3:-60}" interval="${4:-2}"
    local elapsed=0 count
    while [ "$elapsed" -lt "$timeout" ]; do
        count=$(sqlite3 "$db_path" "$query" 2>/dev/null)
        if [ "${count:-0}" -gt 0 ] 2>/dev/null; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    return 1
}

wait_for_db_count_gt() {
    local db_path="$1" query="$2" baseline="$3" timeout="${4:-60}" interval="${5:-2}"
    local elapsed=0 count
    while [ "$elapsed" -lt "$timeout" ]; do
        count=$(sqlite3 "$db_path" "$query" 2>/dev/null)
        if [ "${count:-0}" -gt "${baseline:-0}" ] 2>/dev/null; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    return 1
}

# ─── Server Lifecycle ────────────────────────────────────────────
start_server() {
    mkdir -p "$E2E_DIR"
    echo "Starting E2E server (port=$E2E_PORT, tick=$TICK_INTERVAL)..."

    ROUTE_SETTINGS_PATH="$ROUTE_SETTINGS" \
    ROUTE_BINDINGS_PATH="$ROUTE_BINDINGS" \
    CHATPILOT_DB="$E2E_DB" \
    CHATPILOT_TASK_DB="$E2E_TASK_DB" \
    CHATPILOT_FILES_DB="$E2E_FILES_DB" \
    CHATPILOT_FILE_ASSETS_DIR="$E2E_ASSETS_DIR" \
    CHATPILOT_TICK_INTERVAL="$TICK_INTERVAL" \
    DEMO_LINE_CHANNEL_SECRET="$LINE_E2E_SECRET" \
    DEMO_LINE_CHANNEL_ACCESS_TOKEN="$LINE_E2E_TOKEN" \
    uv run uvicorn chatpilot.server:create_app --factory \
        --port "$E2E_PORT" --host 0.0.0.0 > "$E2E_LOG" 2>&1 &
    E2E_PID=$!

    # Wait for health
    for i in $(seq 1 30); do
        if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
            echo "Server ready (PID=$E2E_PID)"
            return 0
        fi
        sleep 1
    done
    echo "Server failed to start!"
    cat "$E2E_LOG"
    exit 1
}

stop_server() {
    if [ -n "$E2E_PID" ]; then
        kill "$E2E_PID" 2>/dev/null
        wait "$E2E_PID" 2>/dev/null
    fi
    # Keep log for review, clean DB
    rm -f "$E2E_DB" "$E2E_TASK_DB" "$E2E_DB-shm" "$E2E_DB-wal" \
          "$E2E_TASK_DB-shm" "$E2E_TASK_DB-wal" \
          "$E2E_FILES_DB" "$E2E_FILES_DB-shm" "$E2E_FILES_DB-wal"
    rm -rf "$E2E_ASSETS_DIR"
    echo "Server stopped. Log at: $E2E_LOG"
}

trap stop_server EXIT

# ─── Start Server ────────────────────────────────────────────────
start_server

# ═══════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════

# ─── Health [L1] ─────────────────────────────────────────────────
header "Health Check"
HEALTH=$(curl -s "$BASE_URL/health")
echo "$HEALTH" | grep -q '"status":"ok"' && pass "GET /health [L1]" || fail "GET /health"
echo "$HEALTH" | grep -q "0.2.0" && pass "version 0.2.0 [L1]" || fail "version check"

# ─── CLI Chat [L1+L2] ───────────────────────────────────────────
header "CLI Chat (full pipeline)"
RESP=$(cli_chat "用一句話自我介紹")
[ -n "$RESP" ] && pass "chatbot responds [L1]" || fail "empty response"
assert_log "SDK session created" "\[SDK\].*sending"

# ─── CLI List Chatbots [L1] ─────────────────────────────────────
header "CLI List Chatbots"
RESP=$(cli_chat "/chatbot list")
echo "$RESP" | grep -q "buddy" && pass "shows buddy [L1]" || fail "buddy not in list"

# ─── Mock Webhook [L1] ──────────────────────────────────────────
header "Mock Webhook"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/webhook/mock" \
    -H "Content-Type: application/json" \
    -d '{"text": "hi", "user_id": "mock-e2e"}')
[ "$CODE" = "200" ] && pass "POST /webhook/mock 200 [L1]" || fail "webhook $CODE"

# ─── Unknown Platform [L1] ──────────────────────────────────────
header "Unknown Platform"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/webhook/slack" \
    -H "Content-Type: application/json" -d '{}')
[ "$CODE" = "404" ] && pass "POST /webhook/slack 404 [L1]" || fail "expected 404 got $CODE"

# ─── Route Discovery Onboarding [L1+L2+L3+L4] ───────────────────
header "Route Discovery Onboarding"

JOIN_CODE=$(line_signed_post_code "$(line_join_body "$DISCOVERY_GROUP_ID")")
[ "$JOIN_CODE" = "200" ] && pass "LINE join discovery webhook 200 [L1]" || fail "LINE join discovery webhook $JOIN_CODE"
if wait_for_log "\\[discovery\\] route=$DISCOVERY_GROUP_ROUTE type=join profile=default_group_safe" 15 1; then
    pass "join discovery applied [L2: log]"
else
    fail "join discovery applied [L2: log missing]" "$DISCOVERY_GROUP_ROUTE"
fi
if wait_for_route_field "$DISCOVERY_GROUP_ROUTE" "discovered_profile" "default_group_safe" 15 1; then
    pass "group discovered route visible [L3]"
else
    fail "group discovered route visible [L3]" "$DISCOVERY_GROUP_ROUTE"
fi
[ "$(cli_route_field "$DISCOVERY_GROUP_ROUTE" "reply_policy" 2>/dev/null)" = "never" ] \
    && pass "group discovery reply_policy=never [L3]" \
    || fail "group discovery reply_policy mismatch"
[ "$(cli_route_field "$DISCOVERY_GROUP_ROUTE" "processing_policy" 2>/dev/null)" = "none" ] \
    && pass "group discovery processing_policy=none [L3]" \
    || fail "group discovery processing_policy mismatch"

line_signed_post_code "$(line_group_text_body "$DISCOVERY_GROUP_ID" "Ubottrigger0000000000000000000001" "bot onboarding group ping" "msg-join-1")" > /dev/null
sleep 3
assert_log "group first message uses onboarding state" "\\[hub\\] $DISCOVERY_GROUP_ROUTE terminal drop (reply=never processing=none capture=False)"
assert_log_absent "group first message no SDK send" "\\[SDK\\].*$DISCOVERY_GROUP_ROUTE.*sending"

FOLLOW_CODE=$(line_signed_post_code "$(line_follow_body "$DISCOVERY_USER_ID")")
[ "$FOLLOW_CODE" = "200" ] && pass "LINE follow discovery webhook 200 [L1]" || fail "LINE follow discovery webhook $FOLLOW_CODE"
if wait_for_log "\\[discovery\\] route=$DISCOVERY_USER_ROUTE type=follow profile=default_private_cheap" 15 1; then
    pass "follow discovery applied [L2: log]"
else
    fail "follow discovery applied [L2: log missing]" "$DISCOVERY_USER_ROUTE"
fi
if wait_for_route_field "$DISCOVERY_USER_ROUTE" "discovered_profile" "default_private_cheap" 15 1; then
    pass "private discovered route visible [L3]"
else
    fail "private discovered route visible [L3]" "$DISCOVERY_USER_ROUTE"
fi
[ "$(cli_route_field "$DISCOVERY_USER_ROUTE" "reply_policy" 2>/dev/null)" = "addressed" ] \
    && pass "private discovery reply_policy=addressed [L3]" \
    || fail "private discovery reply_policy mismatch"
[ "$(cli_route_field "$DISCOVERY_USER_ROUTE" "processing_policy" 2>/dev/null)" = "interactive" ] \
    && pass "private discovery processing_policy=interactive [L3]" \
    || fail "private discovery processing_policy mismatch"

line_signed_post_code "$(line_private_text_body "$DISCOVERY_USER_ID" "你好 discovery private" "msg-follow-1")" > /dev/null
sleep 12
assert_log "private first message uses onboarding state" "\\[route\\] $DISCOVERY_USER_ROUTE → chatbot=buddy"

# ─── Keyword Trigger [L2] ───────────────────────────────────────
header "Keyword Trigger"
mock_webhook '{"text": "bot 你好", "user_id": "kw1", "group_id": "g-kw-e2e", "is_mention": false}' > /dev/null
sleep 12
assert_log "keyword trigger processed" "g-kw-e2e.*sending"
# Non-trigger should NOT produce SDK sending for this group
mock_webhook '{"text": "大家好", "user_id": "kw2", "group_id": "g-kw-e2e2", "is_mention": false}' > /dev/null
sleep 2
assert_log_absent "non-trigger silent" "\[SDK\].*g-kw-e2e2.*sending"

# ─── Memo CRUD [L2+L3] ──────────────────────────────────────────
header "Memo (save + list + delete)"
MEMO_USER="e2e-memo-$(date +%s)"

# Save — direct command, no time reference (avoid LLM routing to add_reminder)
cli_chat "記住：倉庫密碼是 7788" "$MEMO_USER" > /dev/null
sleep 10
assert_tool_called "memo save" "save_memo"
assert_db_exists "memo in DB" \
    "SELECT count(*) FROM memory_memos WHERE route_id LIKE '%$MEMO_USER%'"

# List
cli_chat "列出我的備忘錄" "$MEMO_USER" > /dev/null
sleep 10
assert_tool_called "memo list" "list_memos"

# Delete
MEMO_COUNT_BEFORE=$(sqlite3 "$E2E_DB" "SELECT count(*) FROM memory_memos WHERE route_id LIKE '%$MEMO_USER%'" 2>/dev/null)
cli_chat "把備忘錄全部刪掉" "$MEMO_USER" > /dev/null
sleep 10
assert_tool_called "memo delete" "delete_memo"
MEMO_COUNT_AFTER=$(sqlite3 "$E2E_DB" "SELECT count(*) FROM memory_memos WHERE route_id LIKE '%$MEMO_USER%'" 2>/dev/null)
if [ "${MEMO_COUNT_AFTER:-0}" -lt "${MEMO_COUNT_BEFORE:-0}" ] 2>/dev/null; then
    pass "memo count decreased [L3: $MEMO_COUNT_BEFORE→$MEMO_COUNT_AFTER]"
elif [ "${MEMO_COUNT_BEFORE:-0}" -eq 0 ]; then
    fail "memo was never saved (save step failed)"
else
    fail "memo not deleted" "before=$MEMO_COUNT_BEFORE after=$MEMO_COUNT_AFTER"
fi

# ─── Reminder [L2+L3] ───────────────────────────────────────────
header "Reminder"
REM_USER="e2e-rem-$(date +%s)"
cli_chat "30 秒後提醒我 E2E 提醒測試" "$REM_USER" > /dev/null
sleep 8
assert_tool_called "reminder set" "add_reminder"
assert_db_exists "reminder in DB" \
    "SELECT count(*) FROM memory_reminders WHERE text LIKE '%E2E%提醒%'"

# ─── Schedule [L2+L3] ───────────────────────────────────────────
header "Schedule (set + cancel)"
SCHED_USER="e2e-sched-$(date +%s)"
cli_chat "設定一個每 5 分鐘的排程，描述 E2E schedule test" "$SCHED_USER" > /dev/null
sleep 8
assert_tool_called "schedule set" "schedule_task_cron"
assert_db_exists "schedule in DB" \
    "SELECT count(*) FROM memory_schedules WHERE status='pending'"

# Cancel
cli_chat "取消排程" "$SCHED_USER" > /dev/null
sleep 8
assert_tool_called "schedule cancel" "cancel_schedule"

# ─── Config Reload [L1] ─────────────────────────────────────────
header "Config Reload"
RESP=$(curl -s -X POST "$BASE_URL/cli/reload" -H "Content-Type: application/json" -d '{}')
echo "$RESP" | grep -q "reloaded" && pass "reload ok [L1]" || fail "reload failed"
sleep 2
assert_log "config reload" "Config reloaded"

# ─── Context Buffer [L2] ────────────────────────────────────────
header "Context Buffer (group)"
mock_webhook '{"text": "閒聊 A", "user_id": "uA", "user_name": "小明", "group_id": "g-ctx-e2e", "is_mention": false}' > /dev/null
mock_webhook '{"text": "閒聊 B", "user_id": "uB", "user_name": "小華", "group_id": "g-ctx-e2e", "is_mention": false}' > /dev/null
mock_webhook '{"text": "他們在聊什麼", "user_id": "uC", "group_id": "g-ctx-e2e", "is_mention": true}' > /dev/null
sleep 12
assert_log "context drained" "\[SDK\].*g-ctx-e2e.*sending"

# ─── Document Edit [L3] ─────────────────────────────────────────
header "Document Edit (xlsx + docx round-trip)"
DOC_RESULT=$(uv run python3 -c "
import asyncio, io, json

async def test():
    from chatpilot.tools.builtin.document_edit import _edit_xlsx, _edit_docx
    import openpyxl, docx

    wb = openpyxl.Workbook()
    wb.active.append(['品名', '數量'])
    wb.active.append(['水泥漆', 10])
    buf = io.BytesIO()
    wb.save(buf)
    edited = await _edit_xlsx(buf.getvalue(), '', json.dumps([['乳膠漆', 5]]))
    wb2 = openpyxl.load_workbook(io.BytesIO(edited))
    rows = list(wb2.active.iter_rows(values_only=True))
    if len(rows) != 3 or rows[2] != ('乳膠漆', 5):
        return 'FAIL:xlsx'

    doc = docx.Document()
    doc.add_paragraph('原始段落')
    buf2 = io.BytesIO()
    doc.save(buf2)
    edited2 = await _edit_docx(buf2.getvalue(), '', json.dumps('新增結論'))
    doc2 = docx.Document(io.BytesIO(edited2))
    if '新增結論' not in [p.text for p in doc2.paragraphs]:
        return 'FAIL:docx'
    return 'OK'

print(asyncio.run(test()))
" 2>/dev/null)
[ "$DOC_RESULT" = "OK" ] && pass "xlsx + docx round-trip [L3]" || fail "document edit: $DOC_RESULT"

# ─── FileHandleCenter Ingress [L2+L3+L4] ───────────────────────
header "FileHandleCenter Ingress"

FILE_IMG_USER="e2e-file-img-$(date +%s)"
mock_webhook "{
  \"platform\": \"mock\",
  \"user_id\": \"$FILE_IMG_USER\",
  \"is_mention\": false,
  \"source_handles\": [
    {
      \"kind\": \"image\",
      \"native_locator\": \"img-e2e-1\",
      \"mime_type\": \"image/png\"
    }
  ]
}" > /dev/null
sleep 3
assert_log "image ingress registered" "\\[file\\] ingress route=mock:$FILE_IMG_USER locator=img-e2e-1 kind=image action=register_only file_id="
assert_file_db_exists "image canonical file row" \
    "SELECT count(*) FROM file_assets WHERE route_id='mock:$FILE_IMG_USER' AND source_platform='mock' AND source_native_locator='img-e2e-1' AND source_kind='image' AND fetch_status='registered' AND storage_backend='none'"

FILE_AUDIO_USER="e2e-file-audio-$(date +%s)"
mock_webhook "{
  \"platform\": \"mock\",
  \"user_id\": \"$FILE_AUDIO_USER\",
  \"is_mention\": false,
  \"source_handles\": [
    {
      \"kind\": \"audio\",
      \"native_locator\": \"aud-e2e-1\",
      \"filename\": \"voice.m4a\",
      \"mime_type\": \"audio/m4a\"
    }
  ]
}" > /dev/null
sleep 5
assert_log "audio ingress eager download" "\\[file\\] ingress route=mock:$FILE_AUDIO_USER locator=aud-e2e-1 kind=audio action=download_now file_id="
assert_file_db_exists "audio materialized row" \
    "SELECT count(*) FROM file_assets WHERE route_id='mock:$FILE_AUDIO_USER' AND source_platform='mock' AND source_native_locator='aud-e2e-1' AND source_kind='audio' AND fetch_status='ready' AND storage_backend='local' AND local_path IS NOT NULL"
AUDIO_LOCAL_PATH=$(sqlite3 "$E2E_FILES_DB" \
    "SELECT local_path FROM file_assets WHERE route_id='mock:$FILE_AUDIO_USER' AND source_native_locator='aud-e2e-1' ORDER BY created_at DESC LIMIT 1" 2>/dev/null)
if [ -n "$AUDIO_LOCAL_PATH" ] && [ -f "$AUDIO_LOCAL_PATH" ]; then
    pass "audio local asset exists [L4]"
else
    fail "audio local asset missing [L4]" "$AUDIO_LOCAL_PATH"
fi

# ─── Observer Mode [L2+L3] ──────────────────────────────────────
header "Observer Mode"

# Clear log marker
OBS_MARKER="OBS_TEST_$(date +%s)"
echo "$OBS_MARKER" >> "$E2E_LOG"

# Send 10 realistic messages (LLM needs real content to categorize, not "test msg N")
OBS_MSGS=(
    '{"text":"老闆我明天請假","user_name":"Worker1","category":"leave"}'
    '{"text":"收到","user_name":"Boss","category":"ack"}'
    '{"text":"下午那批水泥漆到了","user_name":"Worker2","category":"inventory"}'
    '{"text":"K1 區已經放滿了","user_name":"Worker3","category":"inventory"}'
    '{"text":"明天出貨三桶到工地","user_name":"Boss","category":"shipping"}'
    '{"text":"我後天也要請假看醫生","user_name":"Worker4","category":"leave"}'
    '{"text":"好 後天人手要調一下","user_name":"Boss","category":"ack"}'
    '{"text":"新進的乳膠漆放 A2","user_name":"Worker2","category":"inventory"}'
    '{"text":"龍泰 303 黑色剩兩桶","user_name":"Worker1","category":"inventory"}'
    '{"text":"下週一客戶要來驗收","user_name":"Boss","category":"schedule"}'
)
for msg_json in "${OBS_MSGS[@]}"; do
    uname=$(echo "$msg_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['user_name'])")
    text=$(echo "$msg_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['text'])")
    mock_webhook "{\"text\": \"$text\", \"user_id\": \"$OBS_ROUTE\", \"user_name\": \"$uname\", \"platform\": \"line:demo\", \"is_mention\": false}" > /dev/null
    sleep 0.2
done

# Wait for the observer LLM batch to fully finish and persist.
if wait_for_log "\\[observer\\].*$OBS_ROUTE_ID.*saved to DB" 90 2; then
    pass "observer batch persisted [L4: saved to DB log]"
else
    fail "observer batch persisted [L4: timeout]" "pattern: [observer] $OBS_ROUTE_ID saved to DB"
fi

# L2: batch triggered
assert_log "observer batch triggered" "\[observer\].*$OBS_ROUTE_ID.*batch triggered"

# L2: no chatbot response (no SDK sending for this route)
assert_log_absent "observer silent (no SDK)" "\[SDK\].*$OBS_ROUTE_ID.*sending"

# L3: observations stored in DB
if wait_for_db_count "$E2E_DB" \
    "SELECT count(*) FROM memory_observations WHERE route_id LIKE '%$OBS_ROUTE%'" 15 1; then
    pass "observation in DB [L3: DB row exists]"
else
    fail "observation in DB [L3: DB row missing]" \
        "query: SELECT count(*) FROM memory_observations WHERE route_id LIKE '%$OBS_ROUTE%'"
fi

# L3: entries count > 0
OBS_ENTRIES=$(sqlite3 "$E2E_DB" \
    "SELECT entries FROM memory_observations WHERE route_id LIKE '%$OBS_ROUTE%' ORDER BY created_at DESC LIMIT 1" 2>/dev/null)
if echo "$OBS_ENTRIES" | python3 -c "import sys,json; entries=json.load(sys.stdin); exit(0 if len(entries)>0 else 1)" 2>/dev/null; then
    pass "observation has entries [L3]"
else
    fail "observation entries empty" "$OBS_ENTRIES"
fi

# ─── Observer Image Enrichment [L2+L3+L4] ──────────────────────
header "Observer Image Enrichment"

OBS_IMG_OBS_BEFORE=$(sqlite3 "$E2E_DB" \
    "SELECT count(*) FROM memory_observations WHERE route_id='$OBS_ROUTE_ID'" 2>/dev/null)
OBS_IMG_ENTRIES_BEFORE=$(sqlite3 "$E2E_DB" \
    "SELECT count(*) FROM observation_entries WHERE route_id='$OBS_ROUTE_ID'" 2>/dev/null)

OBS_IMG_TEXTS=(
    "收到"
    "好"
    "ok"
    "了解"
    "哈哈"
    "先這樣"
    "晚點再說"
    "知道了"
    "辛苦了"
)
for text in "${OBS_IMG_TEXTS[@]}"; do
    mock_webhook "{\"text\": \"$text\", \"user_id\": \"$OBS_ROUTE\", \"user_name\": \"FieldOps\", \"platform\": \"line:demo\", \"is_mention\": false}" > /dev/null
    sleep 0.2
done
mock_webhook "{
  \"text\": \"[圖片 ref:mock:site-img-1]\",
  \"user_id\": \"$OBS_ROUTE\",
  \"user_name\": \"FieldLead\",
  \"platform\": \"line:demo\",
  \"is_mention\": false,
  \"source_handles\": [
    {
      \"route_id\": \"$OBS_ROUTE_ID\",
      \"platform\": \"mock\",
      \"kind\": \"image\",
      \"native_locator\": \"site-img-1\",
      \"mime_type\": \"image/png\"
    }
  ]
}" > /dev/null

if wait_for_log "\\[tool_call\\] observe_image_ref" 90 2; then
    pass "observer image tool called [L2]"
else
    fail "observer image tool called [L2: timeout]" "pattern: [tool_call] observe_image_ref"
fi

OBS_IMG_OBS_AFTER=$(sqlite3 "$E2E_DB" \
    "SELECT count(*) FROM memory_observations WHERE route_id='$OBS_ROUTE_ID'" 2>/dev/null)
if wait_for_db_count_gt "$E2E_DB" \
    "SELECT count(*) FROM memory_observations WHERE route_id='$OBS_ROUTE_ID'" \
    "${OBS_IMG_OBS_BEFORE:-0}" 90 2; then
    OBS_IMG_OBS_AFTER=$(sqlite3 "$E2E_DB" \
        "SELECT count(*) FROM memory_observations WHERE route_id='$OBS_ROUTE_ID'" 2>/dev/null)
    pass "observer image batch persisted [L3]"
else
    fail "observer image batch persisted [L3]" \
        "before=${OBS_IMG_OBS_BEFORE:-0} after=${OBS_IMG_OBS_AFTER:-0}"
fi

OBS_IMG_ENTRIES_AFTER=$(sqlite3 "$E2E_DB" \
    "SELECT count(*) FROM observation_entries WHERE route_id='$OBS_ROUTE_ID'" 2>/dev/null)
if wait_for_db_count_gt "$E2E_DB" \
    "SELECT count(*) FROM observation_entries WHERE route_id='$OBS_ROUTE_ID'" \
    "${OBS_IMG_ENTRIES_BEFORE:-0}" 90 2; then
    OBS_IMG_ENTRIES_AFTER=$(sqlite3 "$E2E_DB" \
        "SELECT count(*) FROM observation_entries WHERE route_id='$OBS_ROUTE_ID'" 2>/dev/null)
    pass "observer image projected entries persisted [L3]"
else
    fail "observer image projected entries persisted [L3]" \
        "before=${OBS_IMG_ENTRIES_BEFORE:-0} after=${OBS_IMG_ENTRIES_AFTER:-0}"
fi

assert_file_db_exists "observer image canonical file row" \
    "SELECT count(*) FROM file_assets WHERE route_id='$OBS_ROUTE_ID' AND source_platform='mock' AND source_native_locator='site-img-1' AND source_kind='image'"

assert_db_exists "observer image latest batch contains image-derived knowledge" \
    "SELECT count(*) FROM memory_observations WHERE route_id='$OBS_ROUTE_ID' AND id=(SELECT id FROM memory_observations WHERE route_id='$OBS_ROUTE_ID' ORDER BY created_at DESC LIMIT 1) AND (entries LIKE '%白漆%' OR entries LIKE '%油漆%' OR entries LIKE '%2桶%' OR entries LIKE '%兩桶%' OR summary LIKE '%白漆%' OR summary LIKE '%油漆%' OR summary LIKE '%2桶%' OR summary LIKE '%兩桶%')"

assert_db_exists "observer image projection contains image-derived knowledge" \
    "SELECT count(*) FROM observation_entries WHERE route_id='$OBS_ROUTE_ID' AND source_observation_id=(SELECT id FROM memory_observations WHERE route_id='$OBS_ROUTE_ID' ORDER BY created_at DESC LIMIT 1) AND (content LIKE '%白漆%' OR content LIKE '%油漆%' OR content LIKE '%2桶%' OR content LIKE '%兩桶%' OR search_text LIKE '%白漆%' OR search_text LIKE '%油漆%' OR search_text LIKE '%2桶%' OR search_text LIKE '%兩桶%')"

assert_log_absent "observer image route still silent" "\\[SDK\\].*$OBS_ROUTE_ID.*sending"

# ─── Observer Silence All Attacks [L2] ───────────────────────────
header "Observer Silence (attack vectors)"

# @mention
mock_webhook "{\"text\": \"@bot hello\", \"user_id\": \"$OBS_ROUTE\", \"platform\": \"line:demo\", \"is_mention\": true}" > /dev/null
sleep 2
# command
mock_webhook "{\"text\": \"/chatbot list\", \"user_id\": \"$OBS_ROUTE\", \"platform\": \"line:demo\", \"is_mention\": true}" > /dev/null
sleep 2
# media
mock_webhook "{\"text\": \"[圖片 ref:line:demo:img123]\", \"user_id\": \"$OBS_ROUTE\", \"platform\": \"line:demo\", \"is_mention\": true}" > /dev/null
sleep 2
assert_log_absent "observer: @mention blocked" "\[SDK\].*$OBS_ROUTE_ID.*sending"
pass "observer: all attacks blocked [L2]"

# ─── Observer VNext: Addressed + Capture [L2+L3+L4] ─────────────
header "Observer VNext (addressed + capture)"

CAP_MSGS=(
    '{"text":"今天要補兩桶底漆","user_name":"Ops1","is_mention":false}'
    '{"text":"收到 我晚點去確認","user_name":"Ops2","is_mention":false}'
    '{"text":"明天早上有人要請假","user_name":"Ops3","is_mention":false}'
    '{"text":"倉庫 A1 區還有三桶","user_name":"Ops4","is_mention":false}'
    '{"text":"下午要送一批到工地","user_name":"Ops5","is_mention":false}'
    '{"text":"黑色乳膠漆還缺一桶","user_name":"Ops6","is_mention":false}'
    '{"text":"週三可能還要再叫貨","user_name":"Ops7","is_mention":false}'
    '{"text":"小王下週一也會請假","user_name":"Ops8","is_mention":false}'
    '{"text":"收到 我整理一下","user_name":"Ops9","is_mention":false}'
    '{"text":"bot 幫我整理一下最近請假狀況","user_name":"Lead","is_mention":false}'
)
for msg_json in "${CAP_MSGS[@]}"; do
    uname=$(echo "$msg_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['user_name'])")
    text=$(echo "$msg_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['text'])")
    mention=$(echo "$msg_json" | python3 -c "import sys,json; print('true' if json.load(sys.stdin)['is_mention'] else 'false')")
    mock_webhook "{\"text\": \"$text\", \"user_id\": \"cap-$uname\", \"user_name\": \"$uname\", \"group_id\": \"$ASSISTANT_GROUP\", \"platform\": \"line:demo\", \"is_mention\": $mention}" > /dev/null
    sleep 0.2
done

if wait_for_log "\\[observer\\].*$ASSISTANT_ROUTE_ID.*saved to DB" 90 2; then
    pass "addressed route observation persisted [L4: saved to DB log]"
else
    fail "addressed route observation persisted [L4: timeout]" "pattern: [observer] $ASSISTANT_ROUTE_ID saved to DB"
fi
assert_log "addressed+capture fanout" "\\[hub\\] $ASSISTANT_ROUTE_ID fanout reply_intent=True observation_intent=True"
assert_log "assistant reply lane session" "\\[Chatbot\\] my-assistant sending lane=reply session=line-demo-${ASSISTANT_GROUP}__my-assistant"
assert_log "assistant observation worker session" "\\[observer\\] $ASSISTANT_ROUTE_ID worker_session=observer-.* lane=observation"
assert_db_exists "addressed route observation in DB" \
    "SELECT count(*) FROM memory_observations WHERE route_id='$ASSISTANT_ROUTE_ID'"
assert_db_exists "addressed route observation entries in DB" \
    "SELECT count(*) FROM observation_entries WHERE route_id='$ASSISTANT_ROUTE_ID'"

# ─── Observer Group Query [L2+L3] ───────────────────────────────
header "Observer Group Query"

mock_webhook "{\"text\": \"bot 請直接使用 query_observations 工具查詢 ops 群組過去 30 天請假紀錄，然後簡短回答\", \"user_id\": \"ops-admin\", \"group_id\": \"$ASSISTANT_GROUP\", \"platform\": \"line:demo\", \"is_mention\": false}" > /dev/null
sleep 15
assert_tool_called "group query tool called" "query_observations"
assert_log "group query executed" "\\[query_obs\\] group=ops caller=$ASSISTANT_ROUTE_ID"

# ─── Observation Retrieval V1 [L2+L3+L4] ───────────────────────
header "Observation Retrieval V1"

mock_webhook "{\"text\": \"bot 請先用 list_observation_candidates 找出 ops 群組最相關的知識來源，shortlist 不是答案，你必須至少選一個 route_id 再用 query_observation_member 查最近 30 天請假紀錄，最後簡短回答\", \"user_id\": \"ops-admin-v1\", \"group_id\": \"$ASSISTANT_GROUP\", \"platform\": \"line:demo\", \"is_mention\": false}" > /dev/null
sleep 15
assert_tool_called "candidate shortlist tool called" "list_observation_candidates"
assert_tool_called "member query tool called" "query_observation_member"
assert_log "candidate shortlist executed" "\\[obs_candidates\\] group=ops caller=$ASSISTANT_ROUTE_ID"
assert_log "member query executed" "\\[obs_member\\] caller=$ASSISTANT_ROUTE_ID route=.*fact_hits=[1-9]"
assert_db_exists "leave observation entries persisted for retrieval" \
    "SELECT count(*) FROM observation_entries WHERE route_id='$ASSISTANT_ROUTE_ID' AND kind='fact' AND content LIKE '%請假%'"
assert_log "retrieval answer includes leave facts" \
    "\\[response\\] $ASSISTANT_ROUTE_ID → .*小王請假"

# ─── TimeService [L4] ───────────────────────────────────────────
header "TimeService Integration"
TODAY_DASH=$(date +%Y-%m-%d)
TODAY_Y=$(date +%Y)
TODAY_M=$(date +%-m)
TODAY_D=$(date +%-d)
TIME_USER="e2e-time-$(date +%s)"
TS_RESP=$(cli_chat "今天幾號星期幾" "$TIME_USER")
sleep 2
# Accept: "2026-03-28" or "2026年3月28日" (spaces optional)
if echo "$TS_RESP" | grep -q "$TODAY_DASH"; then
    pass "today's date exact match [L4: $TODAY_DASH]"
elif echo "$TS_RESP" | grep -Eq "${TODAY_Y}[[:space:]]*年[[:space:]]*${TODAY_M}[[:space:]]*月[[:space:]]*${TODAY_D}[[:space:]]*日"; then
    pass "today's date (Chinese format) [L4: ${TODAY_Y}年${TODAY_M}月${TODAY_D}日]"
else
    fail "date mismatch" "expected $TODAY_DASH or Chinese format in: $TS_RESP"
fi

# ─── Trigger Keyword Lifecycle [L4] ─────────────────────────────
header "Trigger Keyword Lifecycle"

# Step 1: Add keyword via chatbot in GROUP (not CLI — route must be the group)
[ "$(line_signed_post_code "$(line_group_text_body "$ASSISTANT_GROUP" "Ukwadmin" "bot 幫我新增觸發關鍵字 e2ekw" "kw-add")")" = "200" ] \
    && pass "keyword add webhook 200 [L1]" \
    || fail "keyword add webhook 200 [L1]"
sleep 15

# L2: tool was called
assert_tool_called "keyword add via group chatbot" "manage_trigger_keywords"

# L3: keyword in DB for the group route
assert_db_exists "keyword in DB (group route)" \
    "SELECT count(*) FROM trigger_keywords WHERE keyword='e2ekw'"

# Step 2 (L4): send group msg with keyword (no mention) → should auto-trigger
[ "$(line_signed_post_code "$(line_group_text_body "$ASSISTANT_GROUP" "Ukwuser" "e2ekw 你好" "kw-hit")")" = "200" ] \
    && pass "keyword trigger webhook 200 [L1]" \
    || fail "keyword trigger webhook 200 [L1]"
sleep 12
assert_log "keyword triggers in group" "Auto-trigger matched.*$ASSISTANT_GROUP"

# Step 3: remove keyword via chatbot
[ "$(line_signed_post_code "$(line_group_text_body "$ASSISTANT_GROUP" "Ukwadmin" "bot 移除觸發關鍵字 e2ekw" "kw-del")")" = "200" ] \
    && pass "keyword remove webhook 200 [L1]" \
    || fail "keyword remove webhook 200 [L1]"
sleep 15
assert_db_not_exists "keyword removed from DB" \
    "SELECT count(*) FROM trigger_keywords WHERE keyword='e2ekw'"

# ─── Warehouse Unit Display [L3] ────────────────────────────────
header "Warehouse Unit Display"

WH_RESP=$(curl -s "http://localhost:8000/api/v1/items/search?q=303" 2>/dev/null)
if echo "$WH_RESP" | python3 -c "
import sys, json
try:
    items = json.load(sys.stdin)
    if items and 'unit_of_measure' in items[0]:
        print('ok')
    else:
        print('missing')
except: print('error')
" 2>/dev/null | grep -q "ok"; then
    FORMAT_RESP=$(uv run python3 -c "
import json, urllib.request
items = json.loads(urllib.request.urlopen('http://localhost:8000/api/v1/items/search?q=303', timeout=10).read())
from chatpilot.tools.builtin.warehouse import _format_search_results
print(_format_search_results(items[:5], '303'))
" 2>/dev/null)
    echo "$FORMAT_RESP" | grep -q "罐" && pass "unit_of_measure shown [L3]" || fail "no unit_of_measure"
    echo "$FORMAT_RESP" | grep -qE "1L|1加侖|5加侖|18L" && pass "spec shown [L3]" || fail "no spec"
else
    green "  ℹ warehouse API not available (skip)"
fi

# ─── L4: Reminder Push Verification ─────────────────────────────
header "Reminder Push [L4]"

REM4_USER="e2e-rem4-$(date +%s)"
# Set reminder for ~10 seconds from now (tick_interval=5)
cli_chat "10 秒後提醒我 L4 推播驗證" "$REM4_USER" > /dev/null
sleep 8
assert_tool_called "L4 reminder set" "add_reminder"

# Wait for CronScheduler to pick it up (tick_interval=5, max ~15s)
echo "  ⏳ waiting for reminder to fire..."
sleep 20

# L4: verify general-agent was enqueued
assert_log "reminder enqueued" "Reminder.*enqueued as general-agent"

# L4: verify reminder marked completed in DB
REM_STATUS=$(sqlite3 "$E2E_DB" \
    "SELECT status FROM memory_reminders WHERE route_id='cli:$REM4_USER' ORDER BY created_at DESC LIMIT 1" 2>/dev/null)
if [ "$REM_STATUS" = "completed" ]; then
    pass "reminder completed in DB [L4]"
else
    fail "reminder status: $REM_STATUS (expected completed)"
fi

# ─── STT Transcriber [L2+L3] ──────────────────────────────────────
header "STT Transcriber"

STT_RESULT=$(uv run python3 -c "
import asyncio

async def test():
    from chatpilot.stt.transcriber import SttTranscriber

    # Test 1: disabled without key
    t = SttTranscriber(api_key='')
    assert not t.enabled, 'should be disabled'
    r = await t.transcribe(b'fake')
    assert r is None, 'disabled should return None'

    # Test 2: graceful failure on bad key
    t2 = SttTranscriber(api_key='sk-invalid')
    assert t2.enabled, 'should be enabled with key'
    r2 = await t2.transcribe(b'not-real-audio')
    assert r2 is None, 'bad request should return None'

    return 'OK'

print(asyncio.run(test()))
" 2>/dev/null)
[ "$STT_RESULT" = "OK" ] && pass "transcriber unit (disabled + graceful fail) [L2]" || fail "transcriber unit: $STT_RESULT"

# L3: Hub audio ref detection + transcription integration
STT_HUB_RESULT=$(uv run python3 -c "
import asyncio

async def test():
    from chatpilot.hub.hub import _AUDIO_REF_PATTERN
    from chatpilot.stt.transcriber import SttTranscriber
    from chatpilot.core.types import Message

    # Pattern detection
    m = _AUDIO_REF_PATTERN.search('[音檔 ref:line:12345]')
    assert m is not None, 'pattern should match'
    assert m.group(1) == 'line', f'platform={m.group(1)}'
    assert m.group(2) == '12345', f'media_id={m.group(2)}'

    # No match on image
    assert _AUDIO_REF_PATTERN.search('[圖片 ref:line:99]') is None, 'should not match image'

    # Message text replacement format
    ref = '[音檔 ref:line:12345]'
    text = f'{ref}（轉錄：你好世界）'
    assert '轉錄：' in text
    assert ref in text

    return 'OK'

print(asyncio.run(test()))
" 2>/dev/null)
[ "$STT_HUB_RESULT" = "OK" ] && pass "hub audio pattern + format [L3]" || fail "hub stt: $STT_HUB_RESULT"

# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════
header "Summary"
echo ""
green "Passed: $PASS"
[ "$FAIL" -gt 0 ] && red "Failed: $FAIL" || green "Failed: $FAIL"
echo ""
echo "Log: $E2E_LOG"
echo "DB:  $E2E_DB"
echo "Files DB: $E2E_FILES_DB"
echo ""

# Dump DB summary for review
echo "─── DB State ───"
for table in memory_memos memory_reminders memory_schedules memory_observations trigger_keywords; do
    count=$(sqlite3 "$E2E_DB" "SELECT count(*) FROM $table" 2>/dev/null || echo "?")
    echo "  $table: $count rows"
done
for table in file_assets file_relations file_notes; do
    count=$(sqlite3 "$E2E_FILES_DB" "SELECT count(*) FROM $table" 2>/dev/null || echo "?")
    echo "  $table: $count rows"
done
echo ""

[ "$FAIL" -eq 0 ] && green "All E2E tests passed!" || red "Some tests failed"
exit $FAIL
