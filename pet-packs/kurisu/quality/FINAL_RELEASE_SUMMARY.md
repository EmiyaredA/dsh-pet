# 独立动画验收 · 本轮最终放行记录

记录时间（UTC）：2026-10-30T16:16:56.659043+00:00。仅覆盖最新的 a003、a010、a012、a026–a030。

该范围本轮新增合格素材：**0 条**。生产台账快照调用数：61。此 QA agent 未提交模型任务、未改正式配置或台账。

| ID | 动作 | 最新任务放行结果 | 原因 |
|---|---|---|---|
| a003 | 被提起悬空 | 不放行 | Localized moving green lights cross irises/forehead/clothing; source hardreject. |
| a010 | 原地小跑 | 不放行 | Unapproved animal tail beneath rear skirt in the otherwisecorrectleft run; source hardreject. |
| a012 | 伸懒腰 | 不放行 | Source motion anatomicallyacceptable with diffusewash, but fixedcanonicalpalette recipe exceeds matrix/offsetbounds; no eligible finalcandidate. |
| a026 | 晨间刷牙 | 不放行 | Source motion anatomicallyacceptable; old self-anchor candidate passesmotion/Alpha/scale but retains olivehairrim/cyanlace. One canonical+boundededge reprocess exceeds40RGBbound; no eligible finalcandidate. |
| a027 | 给桌面除尘 | 不放行 | Featherduster covers lefteye near2.6s; strictfacevisibility hardreject. Groundhalo separately may bekeyable. |
| a028 | 捧脸发呆 | 不放行 | Localized moving green bubbles cross face/irises; source hardreject. |
| a029 | 认真记笔记 | 不放行 | Palegreen/white bubblebackground; all240frames failmandatoryflat saturatedchroma. |
| a030 | 翻阅论文 | 不放行 | Radial halo/gradientbackground;237frames failmandatorychroma. Oversizedbookobscureslowerface. |

a026 的动作、真实 Alpha 与比例检查通过；颜色仍未通过。a012/a026 的源片允许尝试受限处理不等于成片合格，处理超限后保留失败记录。

两条最终提示词试验仍生成了气泡或光晕背景，按已批准的关键画风问题停止条件结束付费生成。其余既有合格素材不受该记录影响。
