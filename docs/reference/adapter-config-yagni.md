# Adapter Config YAGNI 判斷

## 結論

目前 **不需要** 為了理論上的多平台 multi-channel 能力，提前把 adapter config schema 完全泛化。

現階段比較正確的做法是：

- 保留 `GatewayConfig.adapters` 這個外層容器結構
- 接受 `AdapterChannelConfig` 與 adapter bootstrap 目前偏向 LINE-shaped
- 只在必要時把 function 拆乾淨，不提早發明通用抽象

這是一個典型的 **YAGNI** 決策。

## 現況拆解

### 1. 外層容器其實已經偏泛化

在 [config.py](/Users/rickwen/code/chatpilot/.worktrees/multi-line-adapter/src/chatpilot/core/config.py)：

- `adapters: dict[str, list[AdapterChannelConfig]]`

這個形狀表達的是：

- 某個 adapter type
- 底下可以有多個具名 channel / account / bot instance

這個容器本身不只 LINE 能用。

### 2. 葉節點 schema 是 LINE-shaped

在 [types.py](/Users/rickwen/code/chatpilot/.worktrees/multi-line-adapter/src/chatpilot/core/types.py)：

- `AdapterChannelConfig.name`
- `AdapterChannelConfig.channel_secret_env`
- `AdapterChannelConfig.channel_token_env`

這兩個 credential 欄位明顯反映 LINE Official Account 的配置模型。

所以目前不是「完全泛化的 adapter channel schema」，
而是：

**generic container + LINE-specific credential leaf**

### 3. 更明顯的特化其實在 bootstrap

在 [server/__init__.py](/Users/rickwen/code/chatpilot/.worktrees/multi-line-adapter/src/chatpilot/server/__init__.py)：

- `_init_adapters()` 只會讀 `config.adapters["line"]`
- 只知道怎麼 instantiate `LineAdapter`
- 只知道 `channel_secret_env` / `channel_token_env`

所以真正的 LINE 特化不只在 schema 命名，也在初始化流程。

## 為什麼現在先不要泛化

### 1. 目前需求只有 multi-LINE

這次的 feature scope 很明確：

- 同一個 webhook 入口支援多個 LINE Official Account

還沒有第二個 multi-channel platform 真正進場。

### 2. 特化點集中在 infra edge

目前 LINE-shaped 的部分主要停留在：

- config leaf schema
- adapter bootstrap

它還沒有污染到核心 domain flow：

- `Message`
- `ChatRoute`
- `route_id`
- hub / scheduler / tools / session context

這表示技術債是 **局部且可控** 的。

### 3. 提前泛化很容易發明錯的抽象

如果現在硬抽成「跨平台通用 credential schema」，
大概率會碰到：

- Telegram 想要的欄位不一樣
- Discord 想要的欄位不一樣
- Slack 又是另一套

最後只會長出一個看起來 generic、實際上難用的 config abstraction。

## 現在可以做、但不必過度設計的整理

如果要讓這塊更乾淨，建議只做 **局部整形**，不要做 schema 泛化：

### 可做

- 把 `_init_adapters()` 裡的 LINE 初始化流程拆成 helper
  - 例如 `_init_line_adapters(config)`
  - 或 `_build_line_adapter(channel_cfg)`
- 把 env 讀取 / skip log / adapter instantiate 分段
- 把 LINE channel config 的註解寫清楚

### 先不要做

- 抽象成跨平台通用 `AdapterCredentialConfig`
- 讓所有 adapter 自帶一套 config DSL
- 為尚未存在的平台預先設計 auth schema

## 什麼時候才值得泛化

以下情況出現時，再來做 generic adapter config 會比較合理：

1. 第二個 multi-channel platform 真的出現
   - 例如 Telegram 多 bot
   - 或 Discord 多 application / workspace

2. 目前 schema 明顯開始長 platform-specific 分支
   - 例如 `if adapter == "line"` / `elif adapter == "telegram"` 到處出現

3. `_init_adapters()` 開始變成大型平台分派器
   - bootstrap 行為重複且難維護

4. 設定檔需要同時承載多種 credential shape
   - 單一 `AdapterChannelConfig` 已經無法自然表達

## 未來泛化時的正確方向

如果未來真的要抽象，應優先抽的是：

- adapter bootstrap contract
- credential loading boundary

而不是先碰後面的 core model。

換句話說，應該先改：

- `AdapterChannelConfig`
- `_init_adapters()`

不要去動：

- `Message`
- `ChatRoute`
- `route_id`
- session / tool / scheduler 的身份規則

因為後面這些抽象目前是健康的，不該為了 config 泛化被牽連。

## 一句話原則

**只要 platform-specific config 還被關在 adapter/config/bootstrap 邊界內，就可以先接受；真正要防守的是不要讓這種特化滲進 route、session、tool、scheduler 的核心抽象。**
