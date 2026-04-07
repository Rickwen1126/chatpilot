# Observation Retrieval V1

這個資料夾收斂 observer 後續的 **DB-first 自然語言查詢** 設計。

範圍包含：

- `route_group` / `observation_profile` 在 retrieval 時的責任切分
- observer capture prompt 如何真正吃到 `observation_profile.instructions`
- candidate source selection（top-k）
- chatbot 與 retrieval tools 的 call stack
- `memory_observations` 與 `observation_entries` 的資料角色

這輪不做：

- vector / embedding RAG
- 跨來源硬 merge engine
- runtime 自動變更 schema

canonical 文件：

- [spec.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/spec.md)
- [plan.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/plan.md)
