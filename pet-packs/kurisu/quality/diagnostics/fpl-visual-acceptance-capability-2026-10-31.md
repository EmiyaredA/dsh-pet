# FPL 视觉验收能力只读核对

FPL 已有真正的 AI 辅助视觉验收实现，会调用视觉模型并返回逐项建议、证据 ID 与无法判断项。它不是只写 approved 标记。但当前官方 GET catalog 显示六种节点方案全部 unavailable：固定模型 API 未配置，五个 Agent 连接均未对当前账号授权。模型列表中的七个 chat+vision 候选不等于节点验收已经可用。

官方 SDK 入口为 `visual.acceptance_catalog`、`get_node_acceptance`、`select_node_acceptance`、`start_node_acceptance`、`get_acceptance_run` 等。启动需固定方案、节点/画布 revision、context_fingerprint、具体 output_id 与 request_id。旧项目级 `start_acceptance_runs`、自定义标准写入、模板创建虽仍有 SDK 方法，后端已410/只读，不能拿来绕过连接配置。AI 结论仅 suggestion，最终决定由单独 `decide_acceptance_run` 完成。

模型 API 实际接收：输出视频12张均匀抽帧、角色参考图片、参考动作视频的0/中点两帧，以及检查要求和覆盖范围。图片缩至1024以内并转 RGB/JPEG85；没有发送视频本体、音频或完整240帧。因此可做角色、动作关键姿态、明显多余突片和色偏的初筛，不能证明所有时刻无尾巴、闪烁或动作次序错误。内置“动作连贯与节奏”仍是 manual，要求完整播放。

Agent 方案也只提供 manifest/image/sample；每次最多12张、任务最多额外24张，有真实读取证据回执，明确禁止宣称看过未读帧、完整连续动作或音频。目前这些连接也全部未授权。视觉助手直接附 video/audio 仅提供元数据；独立 `inference.generate_text/stream_text` 支持 text+图片（每消息至多5张，每张8MiB），拒绝 video 资产。没有发现当前实现中的原生连续视频语义检查接口。

当前列出的视觉模型：

- SenseAudio VL 1.0：`f1000000-0000-4000-8000-000000000002` / `senseaudio-vl-1.0-260319`
- SenseAudio VL Lite 1.0：`f1000000-0000-4000-8000-000000000008` / `senseaudio-vl-lite-1.0-260319`
- Qwen3.6 35B-A3B：`f1000000-0000-4000-8000-000000000012` / `qwen3.6-35b-a3b`
- Kimi K2.6：`f1000000-0000-4000-8000-000000000013` / `kimi-k2.6`
- Doubao Seed 2.0 Pro：`f1000000-0000-4000-8000-000000000017` / `doubao-seed-2-0-pro-260215`
- Claude Haiku 4.5：`f1000000-0000-4000-8000-000000000004` / `claude-haiku-4-5-20251001`
- SenseNova 6.8 Flash-Lite：`f1000000-0000-4000-8000-000000000018` / `sensenova-6.8-flash-lite`

建议定位：未来配置好合法 reviewer 后，可用 AI 抽样初筛减少翻页，优先返回 failed/pending 和证据区间；保留逐帧数值门禁、独立原片解剖检查及完整播放验证。该能力不能替代真实 Alpha、发丝内部白岛或全时段闪烁的证明。

本次只做两个官方 GET 和本地只读源码检查，无模型调用、POST、配置/台账修改、FPL 文件变更或语义抠像。伴随 JSON 保存安全实际返回、接口限制与源码 SHA。
