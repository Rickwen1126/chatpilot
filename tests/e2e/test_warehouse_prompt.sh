#!/usr/bin/env bash
# Warehouse Prompt Quality Test — targets shinyipaint chatbot
# Usage: ./tests/e2e/test_warehouse_prompt.sh [port]
# Requires: chatpilot server running, warehouse backend on :8000

PORT="${1:-2999}"
BASE_URL="http://localhost:$PORT"
# shinyipaint group_id from routes.yaml
GROUP_ID="C0069917b022d280805149bf9a8709453"

green() { printf "\033[32m%s\033[0m\n" "$1"; }
cyan() { printf "\033[36m%s\033[0m\n" "$1"; }
dim() { printf "\033[90m%s\033[0m\n" "$1"; }
header() { printf "\n\033[1;34m━━━ %s ━━━\033[0m\n" "$1"; }

# Send query to shinyipaint chatbot via group_id routing
ask() {
    local query="$1"
    local user="${2:-prompt-test-$(date +%s)}"
    local resp
    resp=$(curl -s -X POST "$BASE_URL/cli/chat" \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"$query\", \"user_id\": \"$user\", \"group_id\": \"$GROUP_ID\", \"platform\": \"line\"}" \
        --max-time 120)
    echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','(no response)'))" 2>/dev/null
}

# Health check
if ! curl -s "$BASE_URL/health" > /dev/null 2>&1; then
    echo "Error: chatpilot server not running on port $PORT"
    exit 1
fi
if ! curl -s "http://localhost:8000/api/v1/items/search?q=303" > /dev/null 2>&1; then
    echo "Error: warehouse backend not running on :8000"
    exit 1
fi

green "Server OK. Testing shinyipaint chatbot warehouse prompts."
echo ""

# Test queries — cover different question types
QUERIES=(
    "303黑色還有嗎"
    "立邦的東西放在哪裡"
    "K1有什麼"
    "有沒有白色的乳膠漆"
    "虹牌水泥漆還有幾桶"
)

LABELS=(
    "搜尋特定物料+色號"
    "搜尋品牌+位置"
    "查位置內容"
    "搜尋+顏色篩選"
    "搜尋+數量問題"
)

for i in "${!QUERIES[@]}"; do
    header "${LABELS[$i]}"
    cyan "Q: ${QUERIES[$i]}"
    echo ""
    RESP=$(ask "${QUERIES[$i]}")
    echo "$RESP"
    echo ""
    dim "─────────────────────────────"
done

echo ""
green "Done. Review responses above for natural language quality."
