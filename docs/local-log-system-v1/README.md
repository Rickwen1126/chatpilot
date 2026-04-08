# Local Log System V1

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: completed

這個資料夾收斂 chatpilot 的 **local log system** 設計。

這輪重點是：

- 讓 logging 成為 app 內建能力，不再依賴 shell redirect
- 單一 current log file + rotation 控制檔案大小
- log 內容以 `route_id` 為主關聯鍵，能重建 dataflow 與 tool calling path
- 抽出 logging backend interface，V1 backend 先用 write-file，之後可替換 Elasticsearch / Loki / cloud logging

這輪已完成 V1 實作與驗證。

canonical 文件：

- [spec.md](/Users/rickwen/code/chatpilot/docs/local-log-system-v1/spec.md)
- [plan.md](/Users/rickwen/code/chatpilot/docs/local-log-system-v1/plan.md)
- [tasks.md](/Users/rickwen/code/chatpilot/docs/local-log-system-v1/tasks.md)
