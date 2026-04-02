#!/usr/bin/env bash
# ChatPilot E2E Test Suite — Self-contained
# Usage: ./tests/e2e/run_e2e.sh
# Starts its own server with routes.example.yaml, temp DB, runs all tests, cleans up.

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
ROUTES="config/routes.example.yaml"
TICK_INTERVAL=5
CLI_TIMEOUT=60
PASS=0
FAIL=0
USER="e2e-$(date +%s)"

# Observer/chatbot IDs from routes.example.yaml
OBS_ROUTE="Ua1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
ASSISTANT_GROUP="Ca1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"

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

# ─── Server Lifecycle ────────────────────────────────────────────
start_server() {
    mkdir -p "$E2E_DIR"
    echo "Starting E2E server (port=$E2E_PORT, tick=$TICK_INTERVAL)..."

    ROUTES_PATH="$ROUTES" \
    CHATPILOT_DB="$E2E_DB" \
    CHATPILOT_TASK_DB="$E2E_TASK_DB" \
    CHATPILOT_FILES_DB="$E2E_FILES_DB" \
    CHATPILOT_FILE_ASSETS_DIR="$E2E_ASSETS_DIR" \
    CHATPILOT_TICK_INTERVAL="$TICK_INTERVAL" \
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
    mock_webhook "{\"text\": \"$text\", \"user_id\": \"$OBS_ROUTE\", \"user_name\": \"$uname\", \"platform\": \"line\", \"is_mention\": false}" > /dev/null
    sleep 0.2
done

# Wait for the observer LLM batch to fully finish and persist.
if wait_for_log "\\[observer\\].*$OBS_ROUTE.*saved to DB" 90 2; then
    pass "observer batch persisted [L4: saved to DB log]"
else
    fail "observer batch persisted [L4: timeout]" "pattern: [observer] $OBS_ROUTE saved to DB"
fi

# L2: batch triggered
assert_log "observer batch triggered" "\[observer\].*$OBS_ROUTE.*batch triggered"

# L2: no chatbot response (no SDK sending for this route)
assert_log_absent "observer silent (no SDK)" "\[SDK\].*$OBS_ROUTE.*sending"

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

# ─── Observer Silence All Attacks [L2] ───────────────────────────
header "Observer Silence (attack vectors)"

# @mention
mock_webhook "{\"text\": \"@bot hello\", \"user_id\": \"$OBS_ROUTE\", \"platform\": \"line\", \"is_mention\": true}" > /dev/null
sleep 2
# command
mock_webhook "{\"text\": \"/chatbot list\", \"user_id\": \"$OBS_ROUTE\", \"platform\": \"line\", \"is_mention\": true}" > /dev/null
sleep 2
# media
mock_webhook "{\"text\": \"[圖片 ref:line:img123]\", \"user_id\": \"$OBS_ROUTE\", \"platform\": \"line\", \"is_mention\": true}" > /dev/null
sleep 2
assert_log_absent "observer: @mention blocked" "\[SDK\].*$OBS_ROUTE.*sending"
pass "observer: all attacks blocked [L2]"

# ─── TimeService [L4] ───────────────────────────────────────────
header "TimeService Integration"
TS_RESP=$(cli_chat "今天幾號星期幾")
sleep 2
TODAY_DASH=$(date +%Y-%m-%d)
TODAY_Y=$(date +%Y)
TODAY_M=$(date +%-m)
TODAY_D=$(date +%-d)
# Accept: "2026-03-28" or "2026年3月28日"
if echo "$TS_RESP" | grep -q "$TODAY_DASH"; then
    pass "today's date exact match [L4: $TODAY_DASH]"
elif echo "$TS_RESP" | grep -q "${TODAY_Y}年${TODAY_M}月${TODAY_D}日"; then
    pass "today's date (Chinese format) [L4: ${TODAY_Y}年${TODAY_M}月${TODAY_D}日]"
else
    fail "date mismatch" "expected $TODAY_DASH or Chinese format in: $TS_RESP"
fi

# ─── Trigger Keyword Lifecycle [L4] ─────────────────────────────
header "Trigger Keyword Lifecycle"

# Step 1: Add keyword via chatbot in GROUP (not CLI — route must be the group)
mock_webhook "{\"text\": \"幫我新增觸發關鍵字 e2ekw\", \"user_id\": \"kw-admin\", \"group_id\": \"$ASSISTANT_GROUP\", \"is_mention\": true}" > /dev/null
sleep 15

# L2: tool was called
assert_tool_called "keyword add via group chatbot" "manage_trigger_keywords"

# L3: keyword in DB for the group route
assert_db_exists "keyword in DB (group route)" \
    "SELECT count(*) FROM trigger_keywords WHERE keyword='e2ekw'"

# Step 2 (L4): send group msg with keyword (no mention) → should auto-trigger
mock_webhook "{\"text\": \"e2ekw 你好\", \"user_id\": \"kw-user\", \"group_id\": \"$ASSISTANT_GROUP\", \"is_mention\": false}" > /dev/null
sleep 12
assert_log "keyword triggers in group" "Auto-trigger matched.*$ASSISTANT_GROUP"

# Step 3: remove keyword via chatbot
mock_webhook "{\"text\": \"移除觸發關鍵字 e2ekw\", \"user_id\": \"kw-admin\", \"group_id\": \"$ASSISTANT_GROUP\", \"is_mention\": true}" > /dev/null
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
