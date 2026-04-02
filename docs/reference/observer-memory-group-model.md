# Observer Memory / Group Model

## 為什麼這份重要

- 目前 `observer` 已經能用，但抽象不穩。
- 問題不在功能壞掉，而在：
  - observer 的註冊來源是 chatbot config
  - observation 的儲存單位是 `route_id`
  - chatbot 查詢時又是用 source label / chatbot 名稱
- 這三層 identity 沒有對齊，長期會讓跨對話管理與共享記憶變得難以推進。

這份文件的目的，是把「現在實際怎麼運作」與「下一步應該怎麼收斂」講清楚。

## 現況主結論

- 目前 persistent memory 的主單位是 `route_id`，不是 bot。
- 目前 observer 的「分享記憶」不是 bot-to-bot shared memory。
- 它實際上是：
  - observer source route 先把 observation 存在自己的 `route_id` 底下
  - 之後 consumer chatbot 再透過 `query_observations` 以 query-time 的方式讀這些 route-scoped observations

一句話：

**現在是 `route-local storage + source-map query sharing`，不是 `bot-level shared memory`。**

## 目前 observer dataflow

### 1. registration identity：誰被宣告成 observer

來源：
- `config.bindings`
- `config.chatbots.<name>.observer_mode`

在 startup / reload 時，系統會掃所有 binding：

- 如果某個 binding 指向的 chatbot config 開了 `observer_mode`
- 就把該 binding 對應的 `group_id` / `user_id` 組成 route
- 再呼叫 hub `register_observer(route_id, ...)`

這代表 observer 的啟動入口，目前是 **chatbot config**。

### 2. storage identity：observation 實際存在哪裡

observer route 收到訊息後，hub 的順序是：

1. file ingress
2. STT
3. observer check
4. append 到 context buffer
5. 達 batch size 後 drain
6. 呼叫 observer batch callback

batch callback 會：

- 用 LLM 把群組對話整理成 entries
- 最後執行：

```python
await memory_store.save(route_id, "observation", {...})
```

關鍵是這裡的 `route_id`：

- 就是 observer source route 本身
- 例如 `line:shinyipaint:C006...`

所以 observation row 會存在：

- `memory_observations.route_id = observer source route_id`

這代表目前真正的 persistent memory unit 是 **route**。

### 3. query identity：chatbot 查詢時拿什麼當來源

系統還會建立一份 in-memory 的 `observer_sources`：

```python
{
  "shinyipaint-observer": {
    "route_id": "line:C006...",
    "all_route_ids": ["line:shinyipaint:C006..."],
    "allowed_consumers": [...],
  }
}
```

當 chatbot 呼叫：

```text
query_observations(source="shinyipaint-observer")
```

真正流程是：

1. 用 `source` 去 `observer_sources` 找設定
2. 驗 `allowed_consumers`
3. 展開 `all_route_ids`
4. 對每個 route 執行：

```python
memory_store.query_observations(route_id=...)
```

所以 `source` 不是 storage key。

真正的 query dataflow 是：

```text
source label
-> observer_sources[source]
-> route_ids
-> memory_observations(route_id=...)
```

## 問題在哪裡

現在其實混了三種 identity：

### A. registration identity
- chatbot config / binding 決定誰是 observer

### B. storage identity
- observation 實際存在哪個 `route_id`

### C. query identity
- chatbot 查詢時用什麼 source label 找資料

這三者不是同一件事，但目前是半綁在一起的。

### 為什麼這會出事

因為現在 observer 看起來像一種 bot mode，但底層 DB 其實完全不是 bot memory。

所以一旦需求從：
- 單一 observer source

長到：
- 多個 route 想共用同一組背景記憶
- 同一個 bot 需要一直理解多個討論串
- 不同 bot 想共用某些背景觀察

就會開始遇到這些問題：

- source label 不穩
- chatbot name 被誤當成 memory source identity
- route-scoped storage 和 bot-scoped query 語意對不上
- observer registration 像是一種 bot type，但實際上不是

## 目前最好的下一層抽象：Group

### 核心收斂

- `route_id` 繼續做最小 storage unit
- `group_id` 做 sharing / query unit

也就是：

**route-local storage + group-level sharing**

這樣可以保留目前 DB 的簡單性，又把共享來源定穩。

## 用 Group 後的模型

### 1. route_id

角色：
- 最小記憶單位
- observation / memo / file / note 的實際持久化 owner

### 2. group_id

角色：
- 共享/查詢單位
- 代表「哪一組 route 的背景記憶被視為同一個來源」

### 3. group membership

角色：
- 定義哪些 route 屬於哪個 group
- 支援 late binding / dynamic registration

這點很重要，因為 route 往往不是 config 寫下去就全知道，而是：

- bot 真加入群組時才知道
- route 被發現後才 attach 到某個 group

### 4. consumer policy

角色：
- 誰可以查這個 group
- 不一定是 bot name，也可以是 route / role / policy set

## 用 Group 後的 dataflow

```text
訊息進某條 route
-> capture policy 判斷是否 ingest
-> observation 存在該 route_id 底下
-> route_id 被註冊到某個 group_id
-> chatbot 查詢時指定 group_id
-> group 展開成一組 route_ids
-> 再去查這些 route_ids 的 observations/files/notes
-> 回到目前 chatbot
```

這樣共享發生在：

- `group -> route_ids -> query`

而不是：

- chatbot name -> observer source label -> 臨時猜測來源

## 這跟三軸 policy 的關係

observer 不應該再是單一 bot type，而應該拆成三種能力：

### 1. memory sharing
- 記憶給誰共享
- 這一軸最終應該掛在 `group`

### 2. background context capture
- 是否持續在背後 ingest / summarize

### 3. reply policy
- 要不要回話，以及何時回話

目前 observer 是這三種能力的一個特定組合，而不是一種獨立物種。

## 對現況最務實的結論

### 現在先承認的事實

- 現在 DB 是 route-scoped memory
- observer source map 是 query/capture policy，不是另一套 memory store
- chatbot 本身目前沒有 bot-scoped persistent memory bucket

### 下一輪 refactor 的優先順序

1. 先定義 `group` 抽象
2. 明確分開：
   - registration identity
   - storage identity
   - query identity
3. 讓 `query_observations` 從 `source label` 過渡到更穩定的 `group_id`
4. 再討論三軸 policy 如何配置到 chatbot / route / group

## 不建議現在做的事

- 不要直接把 observer 再擴成更多 special case
- 不要先發明 bot-level persistent memory，而沒有先釐清 route/group 關係
- 不要再讓 `chatbot_name` 暗中兼任 query source identity

## 一句話

**observer 下一輪真正要解的，不是多一個 mode，而是把 `route-local storage` 與 `group-level sharing` 分開，讓共享記憶的身份穩定下來。**
