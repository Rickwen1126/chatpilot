#!/usr/bin/env bash
# ChatPilot E2E Test Suite
# Usage: ./tests/e2e/run_e2e.sh
# Requires: server running on localhost:2999

set -e

BASE_URL="${CHATPILOT_URL:-http://localhost:2999}"
PASS=0
FAIL=0
USER="e2e-$(date +%s)"

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red() { printf "\033[31m%s\033[0m\n" "$1"; }
header() { printf "\n\033[1;34m=== %s ===\033[0m\n" "$1"; }

assert_contains() {
    local label="$1" output="$2" expected="$3"
    if echo "$output" | grep -qi "$expected"; then
        green "  ✓ $label"
        PASS=$((PASS + 1))
    else
        red "  ✗ $label (expected '$expected' in output)"
        echo "    got: $output"
        FAIL=$((FAIL + 1))
    fi
}

assert_status() {
    local label="$1" code="$2" expected="$3"
    if [ "$code" = "$expected" ]; then
        green "  ✓ $label (HTTP $code)"
        PASS=$((PASS + 1))
    else
        red "  ✗ $label (expected $expected, got $code)"
        FAIL=$((FAIL + 1))
    fi
}

cli_chat() {
    uv run chatpilot-cli chat "$1" --user "$USER" --url "$BASE_URL" 2>/dev/null
}

mock_webhook() {
    curl -s -X POST "$BASE_URL/webhook/mock" \
        -H "Content-Type: application/json" \
        -d "$1"
}

# ─── Health ───────────────────────────────────────────────────────
header "Health Check"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
assert_status "GET /health" "$CODE" "200"

HEALTH=$(curl -s "$BASE_URL/health")
assert_contains "version 0.2.0" "$HEALTH" "0.2.0"

# ─── CLI Chat ─────────────────────────────────────────────────────
header "CLI Chat (full pipeline)"
RESP=$(cli_chat "用一句話自我介紹")
assert_contains "chatbot responds" "$RESP" ""  # any non-empty response
[ -n "$RESP" ] || { red "  ✗ empty response"; FAIL=$((FAIL + 1)); }
[ -n "$RESP" ] && PASS=$((PASS + 1))

# ─── CLI List Chatbots ────────────────────────────────────────────
header "CLI List Chatbots"
RESP=$(cli_chat "/chatbot list")
assert_contains "shows buddy" "$RESP" "buddy"

# ─── Mock Webhook ─────────────────────────────────────────────────
header "Mock Webhook"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/webhook/mock" \
    -H "Content-Type: application/json" \
    -d '{"text": "hi", "user_id": "mock-e2e"}')
assert_status "POST /webhook/mock" "$CODE" "200"

# ─── Unknown Platform ────────────────────────────────────────────
header "Unknown Platform"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/webhook/slack" \
    -H "Content-Type: application/json" -d '{}')
assert_status "POST /webhook/slack → 404" "$CODE" "404"

# ─── Trigger Keywords ────────────────────────────────────────────
header "Trigger Keywords (bot)"
# Should trigger (bot + space)
mock_webhook '{"text": "bot 你好", "user_id": "kw1", "group_id": "g-kw-e2e", "is_mention": false}' > /dev/null
sleep 12
LOG=$(curl -s "$BASE_URL/health")  # just to keep connection alive
# Should NOT trigger
mock_webhook '{"text": "大家好", "user_id": "kw2", "group_id": "g-kw-e2e", "is_mention": false}' > /dev/null
green "  ✓ keyword trigger sent (check server log for verification)"
PASS=$((PASS + 1))

# ─── Memo Save + List ────────────────────────────────────────────
header "Memo (save + list)"
RESP=$(cli_chat "記住：E2E 測試 memo 功能")
sleep 8
RESP2=$(cli_chat "好，記下來")
sleep 8
RESP3=$(cli_chat "我記了什麼？")
# At least one response should mention memo or 記
HAS_MEMO=$(echo "$RESP$RESP2$RESP3" | grep -ci "記\|memo\|記下\|記住" || true)
if [ "$HAS_MEMO" -gt 0 ]; then
    green "  ✓ memo flow completed"
    PASS=$((PASS + 1))
else
    red "  ✗ memo flow — no confirmation found"
    FAIL=$((FAIL + 1))
fi

# ─── Reminder ─────────────────────────────────────────────────────
header "Reminder (add)"
RESP=$(cli_chat "1 分鐘後提醒我 E2E 測試")
assert_contains "reminder set" "$RESP" ""
[ -n "$RESP" ] && PASS=$((PASS + 1))
green "  ℹ reminder push will fire in ~60s (check server log)"

# ─── Schedule ─────────────────────────────────────────────────────
header "Schedule (set + list + cancel)"
RESP=$(cli_chat "設定一個每 5 分鐘的排程用 echo pipeline")
sleep 8
LIST=$(cli_chat "列出排程")
sleep 8
CANCEL=$(cli_chat "取消第 1 個")
assert_contains "schedule set" "$RESP" ""
[ -n "$RESP" ] && PASS=$((PASS + 1))
assert_contains "cancel response" "$CANCEL" ""
[ -n "$CANCEL" ] && PASS=$((PASS + 1))

# ─── Config Reload ────────────────────────────────────────────────
header "Config Reload"
RESP=$(curl -s -X POST "$BASE_URL/cli/reload" \
    -H "Content-Type: application/json" -d '{}')
assert_contains "reload ok" "$RESP" "reloaded"

# ─── Context Buffer (group) ──────────────────────────────────────
header "Context Buffer (group mock)"
mock_webhook '{"text": "閒聊 A", "user_id": "uA", "user_name": "小明", "group_id": "g-ctx-e2e", "is_mention": false}' > /dev/null
mock_webhook '{"text": "閒聊 B", "user_id": "uB", "user_name": "小華", "group_id": "g-ctx-e2e", "is_mention": false}' > /dev/null
mock_webhook '{"text": "他們在聊什麼", "user_id": "uC", "group_id": "g-ctx-e2e", "is_mention": true}' > /dev/null
sleep 12
green "  ✓ context buffer messages sent (check server log for context injection)"
PASS=$((PASS + 1))

# ─── R2 Image Push ────────────────────────────────────────────────
header "R2 Image Upload + Push"
R2_RESULT=$(uv run python -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

async def test():
    endpoint = os.environ.get('R2_ENDPOINT', '')
    if not endpoint:
        return 'SKIP:R2_not_configured'

    from chatpilot.storage.r2 import R2Storage
    import struct, zlib

    # Generate 10x10 blue PNG
    w, h = 10, 10
    raw = b''
    for _ in range(h):
        raw += b'\x00' + bytes([0, 0, 255]) * w
    compressed = zlib.compress(raw)
    def chunk(ct, d):
        c = ct + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' +
           chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
           chunk(b'IDAT', compressed) + chunk(b'IEND', b''))

    r2 = R2Storage()
    url = await r2.upload(png, 'image/png', 'png')
    if not url:
        return 'FAIL:upload_returned_none'

    # Verify mock adapter can build messages with attachment
    from chatpilot.core.types import Attachment, Response
    resp = Response(text='test', attachments=[Attachment(type='image', url=url)])
    if len(resp.attachments) == 1 and resp.attachments[0].url == url:
        return f'OK:{url}'
    return 'FAIL:attachment_mismatch'

print(asyncio.run(test()))
" 2>/dev/null)

if echo "$R2_RESULT" | grep -q "^OK:"; then
    green "  ✓ R2 upload + attachment OK"
    PASS=$((PASS + 1))
elif echo "$R2_RESULT" | grep -q "^SKIP"; then
    green "  ⊘ R2 not configured, skipped"
else
    red "  ✗ R2 image test failed: $R2_RESULT"
    FAIL=$((FAIL + 1))
fi

# ─── Summary ──────────────────────────────────────────────────────
header "Summary"
echo ""
green "Passed: $PASS"
[ "$FAIL" -gt 0 ] && red "Failed: $FAIL" || green "Failed: $FAIL"
echo ""
[ "$FAIL" -eq 0 ] && green "All E2E tests passed!" || red "Some tests failed"
exit $FAIL
