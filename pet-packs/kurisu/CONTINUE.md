# 持续制作入口

## 用户指定三条完整抠像（最新，2026-10-31）

a024原地转圈展示、a025惊讶后整理仪态、a027给桌面除尘已按用户当前选定原片抠像，上传同一主节点并设最终输出。保留原片全部243帧/24fps/10.125秒，640×360无声VP9Alpha；不剪段、不循环、不倒放，不新增模型调用。a027保留原片轻微绿染及扬尘效果。三条均awaiting_review且不打通过勾。

用户随后取消a026晨间刷牙；本次未上传、未修改a026节点、最终输出、输出版本列表或台账。所有原片/历史保留，其它制作与自动发布仍暂停。回执在Future-Props-Lab/.local/kurisu-key-four/publication.json。


## a009 循环接缝修订（最新）

用户指出约2/4/6/8秒甩手像回放，旧v8直接重复48帧不再作为最终。a009新v9在接缝使用原片下一帧，4帧同相位向前重叠接回，透明10秒，无倒放；SHA c53b28096d23d648995d30f18521d30c6d42eb668dfa39e3907d979740d581f1。a010仍为原v12，未采用有可见重影的实验修订。两条仍未通过，等待用户验收；其它制作继续暂停。

## a009/a010 用户指定循环剪辑（最高优先，2026-10-31）

- 用户明确允许这两条从已有原片抠像、截取完整步态并循环，覆盖旧的“禁止短步态循环”限制，仅限a009/a010此次本地剪辑；其它生成、处理和发布仍暂停。
- a009取原attempt5的93–140帧，a010取原attempt6的134–181帧，48帧完整步态各重复5次，640×360/24fps/10s/VP9Alpha/无音轨；无新模型调用。
- 两条新版本均已上传同一主节点并设最终输出，status=awaiting_review、approved=false，等待用户查看，不能自动打勾或计入已通过29条。
- a009原片有明显尾巴，本次保留并打标签；未擦除人物前景或重绘。a011/034/052及其它已通过文件未动。
- 报告及publication回执在 Future-Props-Lab/.local/kurisu-walk-loops/；正式候选也保留在各attempt的user-loop-selection-20261031目录。


## 动画库整理完成（2026-10-31，最高优先）

- 制作、返修、处理、自动发布均暂停；已提交原任务全部回收，0在途。制作heartbeat106仍PAUSED；不得从历史授权重启。
- FPL原项目保留，动画库统一文件夹「动画库 · 106 个动作」，13个动作分组，106个原有主节点；只29个已通过动作打勾。
- 其余77：待原片审核17、背景或处理失败24、未通过验收25、已撤回11；不新增验收结论。
- 303个独立媒体版本已归入动作输出历史，62个重复节点已移除、原文件保留；早期样片已包含在106中，不重复计数。
- a011仍锁定第二版，a034/a052原字节不变。获批节点默认透明成片；未通过节点默认当前规格最近原片。
- library.actions[].node_id保持稳定；获批delivery_node_id现指同一主节点，旧ID在canvas_organization与完整快照/版本映射中可查。勿运行会恢复旧名称、旧分类或拆交付节点的历史同步脚本。
- 累计模型调用218，本次新增0。验收通过仅29/106，完整库仍未完成，不发布完整正式安装包。
- 整理备份、逐版本来源映射和验收记录在 Future-Props-Lab/.local/kurisu-library整理/；library.canvas_organization保存入口。


## 用户暂停与动画库整理（最高优先，2026-10-31）

用户已要求暂停新生成、返修、本地处理和自动发布。仅回收已提交的原任务，随后停止。不得依据下文历史授权恢复生产，也不得自动重启五轮或四分片制作。当前整理106个动作、一动作一个节点、按既有验收结论勾选。整理记录在 Future-Props-Lab/.local/kurisu-library整理/；完成后以 library.canvas_organization 为准。

## 当前生产入口（2026-10-31T14:37:37.682047+00:00；其后旧章节均为历史）

- 人类最新累计调用上限 **240** 已写library limits，实际218/240，剩22；新总额内不再问批准，所有历史保留。普通纠正与真实Paid/repair分别记账；精确46失败快照各唯一额外Paid券，已用46/46；已消费不再自动补提/额外本地修补，恢复原任务/初次必要转码不多收费。
- **第二波27已真实启动**，scope `user240-retry-wave02`、manifest SHA99f92c45180bba016b1e27fab2220a8699045ce1be29ebdfda97e5fb4e8de66c，controller PID87812；scope有限191→218、global240、6模型/2本地，先补空位再回收，不等人类验收停生成。通过0、失败10、生成处理1、待验收16、未提交0、新原片26/27。先读该scope launch/controller.log/actual-task-ids-status及media/handoff、独立source/final记录，不重复启动。首波19已全部回收/owner82562与media82857/integration83045均正常结束，0通过19失败；14原背景fail、5额外耳机等道具语义reject，不重开19或复活旧controller。
- 本波新假设：单张opaque80角色参考/U24/H3六段，删首波共用句中无关耳机/外套/饮料例子，只保留每条必要道具；没有偷偷改名字/direction/props/spec或旧paid提示词。24GREEN；a072/a078/a081 BLUE保护绿色道具，真实chroma frozen，蓝源绝不绿key。单参考前删除全部旧next_*，SDK真实payload/SHA一致，授权完整digest+CAS固定、原19全部回收退出才激活。prompt skill h3-prompt-writing照用；仍排除Seedance2.0/U17/U06。此为有限新试，不声称稳定路线。
- 全库合格29/106，当前spec源106/106，历史源106/106；本波基线29，新增0：暂无。源覆盖不等于合格，小时automation-2按原频率/双粉底视频，报新名称、spec覆盖、实际/240、当波通过失败与新增SHA。
- BLUE仅固定原生240边框sourceSHA profile、64/110普通RGB距离key、soft边缘B去溢色；原绿worker未改。source ALLOW+全240真实背景通过才初次处理，人物错误/白岛/杂物拒收，不用白RGB挖色/语义扩用/绘五官/擦前景/短步态loop。10秒640×36024fps240帧VP9Alpha无音轨，等比站高270脚330；独立全240技术和原640高对比底/脸发放大、实际连续播放及idle切换，技术Alpha不代替视觉。仅独立PASS原字节热更，保留用户位置名称尺寸朝向显示固定，不重启其它宠物。
- **a011人类已确认第2版既有透明WebM** SHA758938975742b90ab855b49c8cecfba43e5aeb8fd8c2021929373684899f0c6b，immutable_selected_media禁止新生成/重修/换版/再问，允许同SHA发布播放；a034 e7a63c9ca2bddb6f6ef39779569a0bc2ffed0894637a34a2693b2ca02a1a99fc、a052 4a364ce1a3fa107730a85aad0a70050cc330dda8a06b7a165ec2190770acdc77原样不动，052已接受原遮挡仅对该SHA。电脑屏朝角色、镜头见背盖，所有真实移动左侧原地步态/右镜像/窗口仅X。
- 27券全部用完后不得同条再自动Paid/local；240剩额只用于尚合法普通一次纠正的其它项，以新有限scope审阅后续做，不伪造新spec或重置历史。本27全部保留可批看，不等人审拖住生成。全106合格+槽位/运行/安装--update验证前，保持部分库，不提升完整正式配置/最终全包。新进展/完成/外部阻塞通知，无变化不重复；到240保留成果列缺口，不自动241。

## 最新用户授权（2026-10-31，Asia/Shanghai）

> 继续保持推进，定时检查，如果没有完成就继续推进（调用额度用完的话可以继续加，直到全部完成为止）

当前聊天已创建 ACTIVE heartbeat，automationId `106`，每15分钟检查并继续。该自动化与另一个聊天的“晚安大小姐”自动化无关，不能修改后者。

旧130次总额、26次返修、单条次数及替代模型测试次数不再是永久停止条件。使用有记录、可测试、幂等的额度扩展入口按需要增加；保留全部历史任务和实际调用，不重置计数。未经新授权不要使用 Seedance 2.0、U17、U06。预算不限制并不代表重复相同失败配方：每次质量停线都要提出具体新假设、改变可控输入/工作流/模型并小规模验证，再恢复最多6路生产。

## 当前状态（以 library.json 更新为准）

- 分支 `codex/kurisu-pet`，FPL项目 `585ee45b-48a2-4f85-a6d6-3e7ae1002ea9`（红莉栖 Q版桌宠 · 样片）。
- 当前1/106条保留（a103）；7条追加前景已撤回、a002复核暂挂。累计71次总调用、27次动作返修、9次其他模型调用。旧9/11条ZIP均隔离，当前无可安装发布包；桌面默认是原图静态预览，不计106。a016第3次80%新构图探针已完整回收并因人物绿染拒收，当前无远端待回收任务。人类已允许一条a105语义小样，240帧推理已完成，正在边界处理及独立验收；当前桌面已恢复a103动态默认，历史页可查看45已生成动作，见文末最新交接。
- a092预算充足、a105实验成功庆祝已撤回：旧原片近白导致发丝白岛，第2次用户指定返修仍240/240帧背景失败。不得用旧白岛版本占数，也不得因单条2次已满永远跳过；在新假设验证时可有记录增加次数。
- 当前保留ID仅a103；a002为未定性小突点保守暂挂，不能叫作已证尾巴或无瑕默认。原正式两样片均撤回，配置文件作为旧快照保留但打包必须失败；完整106槽位草稿未提升。
- 原9条包与11条包已在temp/kurisu/withdrawn-deliveries/隔离，当前无发布ZIP。当前105条缺口见GAPS.md，最新报告quality/LATEST_QUALITY_STATUS.json/.md；旧FINAL_*报告标记superseded，不得作为当前放行。

## 本次正在推进的下一步

1. 先查本聊天对【仅1条a105旧原片的本地语义抠像小样】是否已有真正人类回复。当前尚无，不能下载模型或推理，不重复发同一问题。若许可只做该有记录的小样，先检查原RGB/Alpha/边缘，不抹额外前景或重绘五官，不把静态占位计动画。
2. 所有75个远端项目任务已完成（71campaign含1诊断＋4早期样片），source-only monitor4952已正常退出。a016 attempt3原task0705116a-ce63-4181-9d60-b27168351133已回收，raw80541a…e0a3f：native240背景PASS但人物粉耳→米黄/橄榄、发箍/描线染绿并变动，独立reject。不要重提或再盲试相同80%配方；这是质量/方法边界，不是额度用完。
3. 继续保留静态原图preview和当前a103，只有新版本通过独立源/成片验收才热更新。a002小点仍未定，不能当已证尾巴或无瑕默认。7条已证追加前景不得擦除修补。旧9/11 ZIP禁止分发，当前无可安装包。
4. 额度可按standing授权有记录扩展；若发现具体尚未验证、仍属于原green流程的新假设可受控小试，不能靠换措辞重放同一失败配方，或把模型测试额度当永久停工理由。当前没有已验证的量产路线，不能直接恢复六路。任何semantic方法变化需要已有问题的明确答复。
5. 若未来新green源片ALLOW，a016 attempt3已绑定 approved-original 静态palette descriptor c5d51c…f4d6；其它新片也需显式描述符，禁止找被撤idle配色fallback。仅解除指定范围local处理hold，独立成片通过才发布。定时任务保持ACTIVE，未变化不重复通知。

## 恢复与质量约束

- 先查询原任务/下载落盘状态；提交结果不明只对账，不盲重提。最多6个模型任务、2个本地转码，CAS和短锁沿用现有队列。官方FPL SDK；不新增公共REST API。
- 独立媒体Python：`temp/kurisu/video-matte-env/bin/python`；SDK源路径 `/Users/tonghao/Projects/Future-Props-Lab/sdk/python/src`。FPL项目现有未提交改动必须保留，不修改其虚拟环境。
- H3提示词使用 h3-prompt-writing；定稿正面图为唯一角色参考，safe绿幕图SHA `f3be325cb0fa1f5afdab90d5615487a3a92401eed054fc3d465f32cebd79ea22`。三视图只存档，不另生人设。猫耳女仆、无银色发夹、无动物尾巴。
- 新原片先核对全部帧背景与人物颜色/动作，再绿幕处理；仅普通绿幕抠像和有界轻微色偏修正。禁止旧白底阈值挖色、拼补五官、抹掉多余肢体/尾巴或短循环掩盖步态。
- 技术Alpha不等于视觉通过：原640帧合成高对比蓝底，头发/脸部原尺寸裁切再放大；严禁仅看100px角色缩略图就放行。区分人工抽样、逐帧指标、连续播放和真实桌面切换验证的覆盖。
- 最终640×360/24fps/10秒/240帧/VP9 Alpha/无音轨；标准站姿约270px、脚底约330px。移动为左向严格侧身，右向镜像，窗口仅横移。笔记本均指电脑，屏幕朝角色。

## 实时服务与最终交付

- 预览 http://127.0.0.1:8768/preview.html；桌宠服务8770。`temp/kurisu/live-preview.json` 是监控/服务定位。认证信息在私有runtime文件，不要输出token或settingsUrl。
- 热更新监控支持 `node scripts/kurisu_live_preview.mjs --attach --port 8770`，仅接管监控，不重启已有服务。避免同时启动多个监控；先核对记录和进程。
- 撤回最后余额动作时，实时配置使用已合格idle作为禁用的契约占位，balanceEnabled=false；这不增加独立动画数量。不保留失败素材作占位。
- 新通过版本才热更新，保留位置/名称/尺寸/朝向。无合格移动则漫游仍关闭。不要触碰用户另一个肥鱼实例。
- 完成条件：106条独立合格文件、所有分类与事件槽位/顺序正确、无肥鱼回退、完整动态/切换与安装更新验证。全部完成后才提升完整配置（漫游/余额/工作状态开启，自动AI碎碎念关闭），封最终ZIP并停用heartbeat106。

## 已落实的额度接口与下一验证

- `scripts/kurisu_quotas.py` 已实现并有83项相关测试覆盖；`quota-ensure` 按下一小批缺口增加，`quota-extend` 显式追加。必须持生产锁、fresh load/save，稳定request_id幂等。
- 示例（只有具体新路线确认后才用）：
  `PYTHONPATH=scripts temp/kurisu/video-matte-env/bin/python scripts/kurisu_library.py quota-ensure --request-id heartbeat106-fl2va-a092-v1 --reason '真实首尾帧条件验证' --calls-needed 1 --repairs-needed 1 --quota-action a092 --other-model-calls-needed 1`
- 新用户standing授权允许主agent批准具体、有记录、有限scope的验证任务，无需每次再向用户要额度许可；这仍不等于无审阅地清掉所有质量hold。
- 下一实质差异是 FL2VA 首尾帧条件：模型 `5a785fa2-385f-45a0-a62b-d955b6dd72af` / `minimax_h3_lightx2v`，10s/16:9/768p。schema要求不同正式assetID；同一safe图相同字节分别作为首尾正常合法，供应商wire为first_frame/last_frame。
- green_gate准备已有safe首帧 + 同字节正式上传尾帧副本，记录 `temp/kurisu/fl2va-pilot-01/manifest.json`；写 `prompts/library/a092-fl2va-pilot-01.txt`，按H3 skill base-en的FL2VA三段格式。production_queue正扩队列内部frames分支；交接前勿用旧reference分支冒充frames。
- 拟先做a092第3次一次验证，新增模型test与单条机会由quota-ensure合法扩展，计入累计；root限定pilot范围和call ceiling，其他队列不补提。仅模型/模式条件发生变化，不修改角色图或用白底挖色。
- 只读历史诊断在 `temp/kurisu/agent-qa/H3_DIAGNOSIS.md`：12份实际request未发现本地参数错；成功旧参考是透明RGBA/角色约93%高，当前safe是RGB不透明绿/角色65%高。同safe既有近白失败也有纯绿控制，不能把透明通道或短prompt写成已证实根因。改参考占比可作为后续受控探针，但紧构图存在裁切风险。

## 当前已提交原任务（本轮实际进展）

- 已通过 `quota-ensure` 请求 `heartbeat106-fl2va-a092-v1`，仅将a092单条上限2→3、other模型测试4→5；总130/返修26仍有余量。实际累计现64次调用、21次返修。
- a092 attempt3 真正frames任务：`102e598c-5065-4482-ba68-0f03d53582bf`，模型 `minimax_h3_lightx2v`。首帧 `c8e65934-8da3-4756-bfb4-ec41f8dde710`，尾帧 `50152800-55d4-4226-a6a3-52014843fcad`，两个正式asset同字节SHA f3be…ea22。该次授权提交后已closed，防止重复；后续新假设可在standing授权下另开有记录的有限scope。
- root已审阅FL2VA三段prompt，去掉纸质notebook歧义，动作仅“满金币钱袋→安心确认→收回→相同空手站姿”。真实队列不覆盖seed，不要把manifest dry-run seed314159写成实际生成seed。
- 恢复监控定位 `temp/kurisu/fl2va-pilot-01/watch.json`、`watch.log`；green_gate为唯一恢复/媒体owner，animation_qa负责独立源片及成片验收。每轮先查当前agents及PID，禁止重提或重复建立监控。
- 首个watch启动失败因为root对venv/python做了Path.resolve()，symlink被解析成basepython而丢失venv prefix。已交green_gate用原始venv路径恢复同任务。启动解释器必须使用 `/Users/tonghao/Projects/dsh-pet/temp/kurisu/video-matte-env/bin/python` 本身，不要resolve该symlink；SDK PYTHONPATH仍指src。
- 新任务结果当前尚未验收，9条保留数量不变。原9条部分ZIP是此前快照；有新通过素材再更新包，不把在生成或失败结果计入完成。

- 监控已实际修复：旧PID71946不存在，新watch PID72157以原venv解释器运行，原任务从queued进入processing，调用仍64/21。下轮以watch.json实时内容为准。


## Heartbeat106续做交接（2026-10-31，当前最新）

- 当前9条保留不变；总调用66 = 动作attempt65 + 独立Wan诊断1，repair22，other7。额度经standing policy逐次审计扩展，不能把诊断漏算或混进动作数量。
- a092 attempt3 `102e598c-5065-4482-ba68-0f03d53582bf`已完整回收：SHA `0d5f267c1cd0db3c415586af57f84f154cf71fd0d0b69e1463b6c1c78463d928`，原片243帧/10.125s；240生产采样中217帧（f22–238）为绿色圆聚光+黑外围。独立报告新增明确不属于双手/原发梢的耳尾样粉紫突起。原片仍HARD REJECT，禁止局部擦掉该前景结构。旧watch已退出。
- 本地几何诊断 `temp/kurisu/agent-qa/a092-garbage-feasibility/DIAGNOSIS.md`：固定圆(672,380,r307)在全243帧内包住人物+钱袋，余量至少7.07源像素，4px边界环全帧绿。仅证明【背景-only固定空间garbage matte】几何可行，绝不等于人物或原片放行。若用于后续片，需重新测全帧安全；不能照搬圆坐标、不能碰人物像素、不能把原raw背景失败改写成passed。任何新增派生处理必须保留raw SHA/原拒收/recipe hash与独立许可，再验Alpha/颜色/动作/连续播放。
- 实验A：a105 attempt3真实frames task `791f2f42-8d0c-4f5e-96e1-6daebb3f4930`，模型minimax_h3_lightx2v。无道具、轻握拳成功庆祝，测试简化前景与背景-only空间matte可行性。单次许可已关闭。原任务恢复PID81642，`temp/kurisu/fl2va-a105-pilot-01/watch.json`、watch.log、RECOVERY_HANDOFF.json。green_gate恢复/处理，animation_qa独立验收；若纯绿且源QA允许可正常处理，若仅外围背景不合格先证明安全，不能自动绕过原gate。
- 实验B：独立Wan待机诊断 task `3bf821b0-dbd5-4887-a059-197137e79418`，diagnostic_id `wan-motion-pilot-01`，node `kurisu-diagnostic-wan-motion-pilot-01`。model wan2.2animate-v4-motion_retargeting，safe image+严格纯绿原待机driver，832x464，seed314159；不支持prompt/ratio/duration，不添加假参数。此诊断不能记为新动画，不改a001/a092状态。恢复PID78373，`temp/kurisu/wan-motion-pilot-01/recovery.log`、recovery.pid、RECOVERY_HANDOFF.json；仅recover，不再次submit。
- Wan独立入口已实现 `scripts/kurisu_wan_diagnostic.py prepare/submit/recover --diagnostic-id ...`；`library.diagnostic_attempts`计入总/other调用，repair仅动作。原任务未知只对账，复用独立node/许可防重复；脚本已测试，不伪装成H3请求。
- 两项实验均已真实提交、许可均closed防重复，当前最多2模型任务，不是等待用户审批。下轮先查现有agent/PID和两原task状态，回收/验收已有结果，不盲提交替代。
- a105源审阅输出 `quality/source-reviews/a105-attempt-3.json`；Wan输出 `quality/diagnostics/wan-motion-pilot-01-source.json`（diagnostic_only），便携图入quality。源片前景硬伤绝不因空间背景几何可行而通过。
- 预览已把diagnostic_attempts计入总调用与活跃生成，静态106动作数不增加。完整配置未提升、实时桌宠仍9条、漫游关闭，未重启其它桌宠。

## Heartbeat后续交接（2026-10-31，最新，覆盖上节进行中状态）

- a105 attempt3 H3-FL原任务已完成并独立拒收：SHA5460…13aac，236/240背景失败（f4–239）；白色进入发丝负空间，固定空间garbage matte不可行，原source报告已保存。
- Wan独立诊断已完成：raw `source/diagnostics/wan-motion-pilot-01/original.mp4`，SHA `7f282cb54d6fbf6703cd2695883732e99908914d2483ad109a58464f4ef7d241`；832x464/30fps/303帧/10.1s。旧proxy31/240（原303帧旧41）失败是缩图边框混入鞋造成的假阳性，不是真正白/黑背景。已修共享 `scripts/kurisu_background.py` 原生1px边界扫描，颜色/空间35/时间24阈值未放宽，新native240/240 PASS，报告quality/diagnostics/wan-motion-pilot-01-native-border-v2.json；内部白岛/前景仍独立审查。
- Wan诊断不计106、不替换a001：右裙黑矩形布片与抬脚/张口偏离基准待机；普通green key诊断又因feet-4px/height-9px未过端点验收，失败partial未发布。真native末f302与截断f299均缩小，保留完整尾部不能修复；旧driver真实body约93.49%画面高，与safe65%不匹配。证据NATIVE_ENDPOINT_GEOMETRY.json/DRIVER_ENDPOINT_GEOMETRY.json。禁止循环、硬拉伸或声称此诊断已是可用新动作。
- a026 frozen旧矩阵+anchor、最终RGB限幅±40（不扩大界限、不新fit）的实验候选 f74514…仍被独立拒收：4底放大发丝有可见橄榄黄绿细环。quality/final-reviews/a026-experimental-bounded-edge-01-f74514c658e2.json。停止追加调色/抹边，不发布。
- 下一实际路线是两条【构图匹配、动作匹配】Wan生产验证，而非复用idle诊断占数。a105 driver正式asset4d89f9c7-a53a-4462-adf2-4aa00902d02b（原FL3，白BG但姿态合格），a026 assete6198899-3f88-46c0-b8cb-d9fe349b989e（原刷牙，绿BG但原色边不合格）。二者与safe同约65%高、首末空手正面、真实鞋底不偏；a105 f239的+14px只是脚下绿椭圆被bbox误算，不需retime/proxy。
- 独立motion-only准入：quality/motion-drivers/a105-fl2va3.json、a026-original1.json。最终source/final拒收保持；仅允许作为新生成的运动条件，不能当成成品。新Wan reference生产分支及normal-green-no-palette媒体profile已实现、测试，实际payload不含不支持的prompt/duration/ratio；输入/审阅SHA不可变，原片不足10秒拒绝。
- 注意：root第一次a105 Wan生产create遇ApiError，出现a105 attempt4 **预留但task_id=null/submission_uncertain**。当前显示67包括这1个未证实的预留；已确认项目70个远端任务全completed且a105仅旧3任务，无新任务。
- production_queue是当前【唯一恢复/状态/画布/提交owner】。已定位确定性 `self_asset_reference`：原a105 node.asset_id正是拟motion driver4d89…，a026同理，官方DAG校验在enqueue前拒绝本节点引用自身。不是可以盲重提的网络失败；不要清旧asset或改FPL源码绕过。原响应细节当时未记录，报告明确依据离线官方resolver复现+node/project任务对账，不伪称捕获HTTP响应code。
- root已授权production_queue完成：安全记录ApiError状态/code/message（不存auth），精确无任务证据后将该整条未enqueue预留归档preflight_rejections/请求JSON（不删历史）并释放其非付费额度；为两动作另建派生source variant nodes，保留旧节点与稳定动作ID/node_history；随后在原仅2次范围内为a105/a026各提交真正Wan一次，遇新unknown立即停下对账。库目前67只是保守预留，最终实际应以完成对账后数据为准，不能直接手写减数。
- 其他agent/根当前禁止并行create或更改相关ledger，直到production_queue交接。root暂停全部相关SDK writes；仅文档不占生产锁。成功两条或新unknown时关闭pilot，原任务recover-only监控/PID日志必须记录。未通过任何素材、未重启live、完整配置仍未提升。

## 2026-10-31 最新续做：self-reference已解决，真实Wan生产2条在跑

- production_queue已用官方resolver离线复现+SDK两次无新任务证据，确认先前a105 attempt4第一次create是enqueue前self_asset_reference拒绝；原响应没保存所以没有伪称观察到HTTP code。旧预留/原request/证据整条移入preflight_rejections审计后释放非付费预留，真实累计恢复66，再真正提交2条到**68次调用、24次repair、9次other、独立诊断1条**。所有真实历史保留，没有reset。
- 两条实际新task：a105 attempt4 `6ef2258b-5e4f-49a6-8129-420f88ec9e83`，source node `kurisu-a105-wan-production-01`；a026 attempt2 `17928a55-b940-4695-a393-937fcb6b2384`，source node `kurisu-a026-wan-production-01`。旧nodes及其asset/output全部保留，动作稳定IDs仍a105/a026，node_history记录派生关系。不可再把旧a105 null-task预留当成未知付费任务重提。
- 两者是固定Wan production profile、canonical safe image、匹配构图且动作语义正确的driver，seed314159；真实请求无不支持的prompt/ratio/duration。动作输出仍需source/fullmedia独立验收，不等于已完成；9条保留仍不变。
- prod正在/已启动仅两原任务source-only恢复监控，最新PID/log/命令以 `temp/kurisu/wan-production-pilot-01/` handoff和library.recovery_monitors为准；不要重复建立或重复create。提交许可均已关闭，已有taskID只recover。
- green_gate为媒体owner，animation_qa为独立源/成片审阅owner，新原片优先于motion-bank初筛。仅native-border/sourceQA通过后走Wan普通green key无palette profile；短片不循环补10秒、geometry/Alpha/边缘不放宽。有牙刷/杯并收回才算刷牙，不接受无关手势；庆祝轻握拳，额外耳尾/布条/眼脸形变/绿光不能因为alpha技术通过而默认放行。
- 只读备用motion bank准备中：QA筛a003/a009/a010/a012/a014/a015旧原MP4，green筛原肥鱼Alpha素材中可用动作输入。所有source仅motion输入，不复制素材占数，不做新Paid或上传；若新Wan结果不匹配动作/造型，仍拒收并据证据改线。
- 原生边框bug已修共享scanner；相关新测试通过，默认颜色/空间/时间阈值未变，不把内部白岛检测交给边框。当前完整配置仍禁止提升，live仍9且漫游关闭，未重启其它桌宠。

- 已收到最终源回收监控交接：唯一source-only PID96295，session24692；temp/kurisu/wan-production-pilot-01/recovery.log、recovery.pid、recover_sources_only.py，library.production_source_recovery_monitors[wan-motion-pilot-01]含精确两原task。prod已释放ledger/SDK提交所有权，后台只做原结果回收；后续root协调、green媒体、QA独立验收。不能再新建同任务或重复worker。


## 最新：透明参考受控探针已回收；语义抠像问题待用户答复

- 两条Wan生产均独立拒收：a105 attempt4变成挥手/合掌/鞠躬而非握拳庆祝、深色连袜变露膝；a026 attempt2牙刷与杯消失，变成空手遮嘴合掌，同样改袜装。native绿背景不等于动作或造型合格。原source报告已保留，不能处理或上架。
- 新假设只改参考图片背景表示：从原定稿RGBA等比缩放到同一65%安全构图，透明留白；不新生图、不改造型、不改历史prompt、global参考不变。透明safe正式asset `31857508-4eca-4ef3-9d42-a8fd52c37cc3`，SHA `13c6f712b98a45637e2b5f34aad4dc6c506538229771ce9bc034b61611583340`，文件 references/kurisu-front-safe-transparent.png；manifest在temp/kurisu/h3-transparent-probe-01/。opaque前景与旧safe RGB一致。原人物core alpha基本252–254，新safe253–255，并非大幅半透明，不能宣称这已证明染绿根因。
- 原H3 reference模型e4940af9/minimax_h3_zm_nono，两次有限scope已关闭：a012 attempt3 task `d73b665f-bf92-4cf6-adde-9677602e4471`，rawSHA `356d74a739a0f9b5917b0ae1a8210c29c90c214b464d28cc521a698d0dfd9be9`，source/library/a012/attempt-3/伸懒腰.mp4；a016 attempt2 task `02b23232-08ba-488d-a72c-e098ed9881ef`，rawSHA `025f5164e76b1044bebe08d0d9437571bb1e723d959dfe1605fc2c984e22d078`，source/library/a016/attempt-2/整理围裙.mp4。实际累计70/repair26/other9，保持完整历史。
- 唯一source-only恢复monitor PID98694已在20:47:35 UTC正常退出，原因originals_ready_for_independent_QA，两个原任务均完整下载；不重提、不重复起watch。handoff/log在temp/kurisu/h3-transparent-probe-01/，ledger monitor状态stopped。旧Wan PID96295亦已退出。
- a012 native240/240绿边界PASS，但contact f48附近可见人物绿色光斑，独立QA正检查，不能因为边界合格就抠像。a016 native240/240 FAIL（淡绿渐变，空间83/时间47.5），不允许处理。green媒体owner仅准备，尚未转码；QA负责SHA绑定source审阅JSON，root随后CAS拒收或限定处理。
- 本轮已用异步问题询问用户是否允许【仅1条a105旧原片本地语义抠像试验】。依据是此前计划明确“仅允许绿幕抠像及经过验证的轻微色偏校正”；语义分割超出该方法范围。尚未收到答复，不能把standing额度授权当作方法变更批准。未下载模型、未推理、未修改9条合格素材。待答复记录quality/diagnostics/semantic-trial-permission-pending.json。
- 若用户允许，候选仅a105 H3-FL attempt3（SHA5460…13aac，庆祝动作/衣装正确但白BG），先少量原帧试验再至240；源RGB不重绘、仅人物Alpha，逐帧时序/发丝白残留/蓝底原尺寸放大/连续播放重新独立审查。不处理a092FL3的额外前景耳尾，不放宽造型或颜色，不在未有许可时安装语义模型。若用户坚持仅绿幕，继续具体新假设的受控生成路线。额度不构成永久停止条件。


### 两条透明探针已完成源拒收和FPL同步（覆盖上一节“正在审阅”）

- a012 attempt3：独立确认f48/f72在额头、脸颊、猫耳/蕾丝、头发及胸口/围裙出现明亮移动绿光，f0还呈橄榄绿染色。技术绿边界PASS不等于人物合格；普通key或语义背景mask都不能恢复被光斑覆盖的前景。已绑定SHA源报告并短锁CAS拒收，未转码。
- a016 attempt2：全240帧淡绿灰白背景失败，并有真实zoom：native虹膜距离105.51→141.16（+33.78%）、真深色鞋底y649→734（+85px），非背景bbox误计。已绑定SHA源报告并CAS拒收，未转码。
- 两份source-review文件顶层reason已补，inspection_scope诚实区分全部240帧边界指标与人工联系图/原尺寸2×抽查；source实时播放和透明成片播放未执行，硬伤已足够拒收。原像素portable证据在quality/evidence/对应transparent-probe文件。
- 台账目前a012/a016 exhausted只是当前审计单条/repair上限的状态，standing授权后续具体新路线可扩展，不等于用户停止任务。quality_route_trials记录h3-transparent-ref01-result两条拒收及不盲补六路。
- 官方enabled可执行workflow清点完毕：共15视频条目＝H3同底层11变体＋Wan动作迁移1＋已排除Seedance2.0/U17/U06三项。没有另一个可用且未排除的新架构；报告quality/diagnostics/non-h3-video-workflow-catalog-2026-10-31.json。管理catalog Forbidden后未绕权限；可执行generation_options为本次证据。
- FPL原画布通过官方SDK按expected_revision同步到revision232，累计70/repair26/other9、9合格。状态说明改为动态额度与standing授权，不再写固定“用完停工”。同步网络调用在生产锁外，短锁只载入与提交metadata。没有创建模型、没有提升正式配置。gallery8768与live8770 health均HTTP200，未重启用户其它桌宠。
- 原9条ZIP保持既有快照，未因无新合格素材重打包。GAPS.md已刷新。当前仅【语义方法变更问题】等用户答复，不能把未回复当作许可；所有付费旧结果已回收，无待恢复任务。后续heartbeat应优先读取人类答复，不重复询问同一问题或重复提交失败配方。


## 当前heartbeat106（21:03 UTC触发）中途交接：追加全身审阅发现前景突片

- 截至本节实际台账是8 approved、70calls/26repairs/other9；仅a101已经有记录withdraw并归档。原9条ZIP已移到temp/kurisu/withdrawn-deliveries/kurisu-9-clips-not-for-release.zip，禁止交付。以下拟撤回不等于已经执行。
- 两agent追加9条共90个未看时刻的native640蓝底全身/头发脸2×抽样，发现此前27次主要头脸/边缘验收遗漏的【裙下追加前景】，不是新的白岛。a001/a004/a005/a006/a008/a101/a102共7条均已对照原RGB证实独立圆头/条状突起、正常双手双鞋同时存在；明确分类unapproved_foreground_appendage，不武断解剖叫尾巴。不能擦除前景修补占数。
- 7条报告逐一验证canonical或withdraw archive SHA、source SHA和报告SHA，统一只读清单temp/kurisu/additional-audit-withdrawals-01/EVIDENCE_PREFLIGHT.json：actual write targets仅6条a001/a004/a005/a006/a008/a102；a101为already_withdrawn_verify_only。a101独立报告quality/additional-audits/a101-appendage-trace-01/withdrawal-recommendation.json；a004/a005在quality/additional-audits/approved-four-new-times-01/；a001/a006/a008/a102在quality/additional-audits/a001-independent-lower-hem-01/。
- 自动审批审查拒绝了旧temp/kurisu/additional-audit-withdrawals-01/apply.py批量撤回+热更新草稿：证据列表漏已撤回a101却硬写7条/剩余a103，认为证据和结果不一致、剩余复核未完成。该脚本未执行，root已首行raise永久禁用原草稿；没有停止monitor或改6条状态。不得代执行/间接绕过拒绝。必须补齐真实6写+1历史验证清单、等a002/a103补审结论，再用新的manifest审阅操作请求自动审批。
- a002左右张望是候选临时default；QA正在完整243源帧左/中/右下裙区域逐帧亲看，已右+中未见同类，左区尚待最终报告。本节不能先把它“完全安全”写死。a103：green已全243源帧裙下ROI亲看，可见区域未发现追加片，支架有遮挡明确不保证遮挡区；quality/additional-audits/a103-full-source-lower-hem-01/a103-lower-hem-full-source-review.json。现a103灰色电脑背盖来自此前有记录的tracked plain rear-lid处理，不伪称原source没UI问题。
- live代码已实现显式preview_idle_override={action_id:'a002',sha256:'831d80bef0ff2dd03a35c6490fd67615f3ee99b152efcb00f448c84032f2ed15'}，只在无approved idle时借用已approved SHA匹配动作本名，不改成a001、不增加106数量。root尚未写真实field。signature含声明；filtered/partialConfiguration可生成安全部分配置。独立静态定稿placeholder入口也已测试但无产素材/未启用，明确不计106、不能入partial交付。
- 当前旧attached monitor PID61263/service23711仍原样运行。新mjs需要仅换attach monitor才能加载新逻辑，不能杀service或其它Electron。受拒旧草稿不得执行。service和gallery仍健康。所有actual实例设置和方向须保留。
- withdraw函数现支持0 campaign attempts的原复用样片：保留reused_origin_history指production.json，reused=false允许后续真正返修，不编造原任务或重置计数。quota counts已把未来首次复用样片替换计为repair（有origin_history且已有新attempt时），修复零attempt绕repair配额。相关78测试通过，当前实际仍70/26。
- sync_kurisu_status.py已改网络get/apply/readback在锁外，前后短锁freshload，fingerprint过期最多重试一次，失败不推进revision、保留并发字段；agent162回归通过，另JS/live+install20/partial包4通过。没有真实新SDK写。
- 可独立推进的绿色新假设：历史74项目任务只用93%或65%构图，无80%；只读报告quality/reference-framing-audit-2026-10-31.json。green正从原front等比缩放+透明pad准备80%占高/脚底90%参考（非语义，不另生图，最多上传一次并SHA核验，不Paid）。root已按H3 skill写prompts/library/a016-framing80-positive-human-01.txt，匹配耳10%/脚90%，仅human anatomy、fabric ornaments、稳定原色纯绿及小幅整理围裙。不宣称证明因果；这属于【构图+匹配简短人类造型prompt的联合验证】，不是透明通道再次重试。准备好后可在standing授权下只限a016一次，必须quota-ensure增加repair26→27及a0162→3、记录actual71，不盲补六路。当前尚未submit或改pilot。
- 语义方法问题仍无新human答复，不能下载模型/推理。等待方法答复不阻止有具体差异的原授权green流程验证，但不得重复同一失败配方。完整106配置禁止提升。


## 最新已执行结果（2026-10-31，覆盖上节中途“仍8条/未执行”）

- 自动审批原拒绝已通过补充证据和修正实际操作解决，未绕过原拒绝：旧apply.py首行raise仍禁用；新READY_PLAN.json核对全部7证据，明确actual6写、a101已撤verify-only、a002完整HOLD与a103完整可见ROI审阅；原图static有独立240帧许可。新的apply_verified_plan.py经再次审查实际完成，证明在temp/kurisu/additional-audit-withdrawals-01/APPLIED_VERIFIED_PLAN.json。
- 实际新撤回6条a001/a004/a005/a006/a008/a102，加此前a101共7条。a002因2–3像素未定米粉点，status=quality_recheck_hold，原媒体与report归档source/library/quality-recheck-hold/a002/；不武断叫尾巴。当前approved仅a103，**1/106，缺口105**。旧9/11 ZIP均隔离，当前无可安装ZIP，原旧两样片配置打包已实测fail closed（Missing 点击回应-傲娇），不纳入失败素材交付。
- 静态默认已真正热更新：原定稿RGBA等比scale516:-1:lanczos+透明pad62/54→640360，VP9 Alpha/noaudio/24fps/10s，全240帧RGBA相同，269px高脚330。SHA `fb91cd81f82eef4e7a8f97a245f98ad61b7f1a56f541983fd7b9f23f99836d31`，previews/static-preview/静态定稿占位_不计106.webm。独立许可quality/final-reviews/static-reference-preview-fb91cd81f82e.json，仅preview，不是新动画/不计106/不代表idle完成。library.preview_static_placeholder显式绑定，未启用idle_override。
- servicePID23711未变，未重启服务或其它Electron/肥鱼；只把attached monitor61263换成4605。实例ID/name/size/position/display/facing/fixed配置对比保留，balance/work/whisper off，static自动权重100，不自动播坏片。实际会话方向由既有热替换逻辑保留，未新增持久方向API。新log temp/kurisu/additional-audit-withdrawals-01/verified-attach-monitor.log。
- gallery已显示static不计106、quality_recheck_hold中文/筛选、standing下exhausted待返修，初始不加载被撤idle；只有approved可点播/下载，static不作为动作卡。修复了零approved时清旧播放器防旧素材残留。JS8轻测通过。真实FPL画布已以短锁/CAS新sync_status更新revision235，文案动态71/27、1条、静态临时默认。
- 当前新paid task已真实提交：**a016 attempt3 `0705116a-ce63-4181-9d60-b27168351133`**，主H3 e4940af9/minimax_h3_zm_nono/reference/10s/169/768p。80%透明reference正式asset19637694-92f8-4109-b08a-20a52d6850b6，SHA5bd754ab2df7c59fff6ebde7158781b3be8ce6670b1c48f16957dc6e05dc71c1。prompt prompts/library/a016-framing80-positive-human-01.txt，SHA4679c042c7f438c514053923188fc64cb08a188036b603b3dfe0f8af1df532e1。只改同原图构图+匹配简短human/布质头饰语义和坐标，属于联合working-recipe探针，不声称单变量因果；普通green流程，非语义。
- quota审计request heartbeat106-framing80-a016-v1：repair26→27、a0162→3，总130/other9未变。真实实际71calls/27repair/other9（含1独立诊断），旧4早期样片仍production.json，不重置。唯一1次pilot heartbeat106-h3-framing80-ref01已closed，不能自动再次submit；失败后仍可有新假设按standing扩展，不把上限作永久结束。
- 唯一source-only恢复monitor PID4952，KEY h3-framing80-probe-01，所有script/log/PID/handoff在temp/kurisu/h3-framing80-probe-01/。精准TASKS仅该a016新ID，source将落source/library/a016/attempt-3/整理围裙.mp4；global local_processing_hold保留，后台只poll/materialize/download/nativegate/contact，不key/approve/semantic/create。完成/失败即退出，下次先查PID和原任务。
- 新片配色基准入口已实现且28测试通过：scripts/kurisu_palette_anchor.py，只接受attempt.palette_anchor_descriptor固定目录SHA/proof链，显式坏值fail closed，不回退被撤idle，不增加p95≤20/max≤40界限。实际descriptor quality/palette-anchors/approved-original-static-01.json，SHA `c5d51ca0b8d0e9968ba99cace52a46693383f6b6fae30f11bf28b8f1ce28f4d6`，已绑定a016 attempt3.palette_anchor_descriptor及pipeline.new_h3_palette_anchor_descriptor；原图78e843…4725→静态assetfb91…6d31→技术报告和独立preview许可双SHA证明。只供palette_reference_only，不是新动画。source ALLOW前不处理，不能把local hold整个删掉后盲跑旧素材。
- a105FL3未来semantic候选已新追加全243下裙三分区+15全身+5脸部审阅：quality/additional-audits/a105-fl3-all-native-lower-body-01/all-native-lower-body-review.json/.md。未见新增同类肢片，但原白底/圆圈/背景碎条/细绿缘仍拒收，不算合格；语义问题人类仍未答复，未下载/推理。
- README、GAPS与quality/LATEST_QUALITY_STATUS均已纠正，旧FINAL_PARTIAL_AUDIT/FINAL_RELEASE_SUMMARY/archive-install-update仅保留历史机制/数值，明确superseded_do_not_release。当前不重打旧包；有有效默认和合格素材再发明确部分包，全106才提升完整配置和停heartbeat106。


### 本轮最终：80%探针已回收拒收，安全预览继续（覆盖“正在回收/生成”）

- a016 attempt3 `0705116a-ce63-4181-9d60-b27168351133`完整回收，raw SHA `80541adeae4a4404bbdf1062d2eb64580f47fcd3beba92f52efb999f453e0a3f`。native240背景PASS不改；独立source报告quality/source-reviews/a016-attempt-3.json REJECT foreground_color_contamination，参考粉耳材质中值约197/110/130，f48约175/174/120（选材比较，不是假称逐像素配准或已实际palette反演）。原全身/脸及同材质放大证据保留；强染色足以拒收，没有继续243裙下遍历、key、调色或语义。stage现awaiting_method_clarification_with_static_preview。
- root已短锁CAS绑定该报告并拒收，action exhausted仅表示当前登记上限，不是永久停工；quota71/27/other9没变。quality_route_trials记录一次联合新构图+human prompt验证失败，不能反复相同配方或直接补六路。唯一monitor4952在22:14:39 UTC正常退出originals_ready_for_independent_QA，metadata stopped，无重复任务。
- method_clarification字段明确已有问题等待人类答复，当前未下载/推理语义模型，standing额度持续授权仍有效，automation106不关闭。不是旧130/26阻塞任务。a105 FL3全243下裙附加审阅无新同类前景，但原white/circle/green-edge仍REJECT；将来若获得1条方法许可只处理这1个试验，不自动恢复批量或覆盖旧拒收。
- 当前服务实际合并配置已用现有认证GET端点只读验证（令牌未输出），HTTP200，idle为静态定稿占位_不计106__v_fb91cd81f82e，自动事件off，servicePID23711未变。证据temp/kurisu/additional-audit-withdrawals-01/MERGED_RUNTIME_VERIFIED.json；没有声称已经做完整桌面逐帧播放观察。Gallery新notice、approve-only点播/下载防旧clip残留均已接入。
- 当前只a103保留、105缺口，旧9/11ZIP均隔离，README/GAPS/LATEST_QUALITY_STATUS/ACTIONS已纠正。原复用a001/a004显示早期样片已撤回、任务见production.json；不会因0campaign attempts显示还在复用，原任务历史不重置。

- 最后对账22:38 UTC：FPL项目75/75远端tasks completed、0active（71campaign+4原样片），最终画布status sync revision236，预览8768与服务8770均HTTP200。temp/kurisu/heartbeat106-final-2103.json保存；没有未回收原任务、没有运行的source-only monitor。attached live monitor4605仍为静态预览监控，service23711不变。下次若无人类答复且无新外部变化，不重复状态通知/相同付费配方；先读method_clarification和CONTINUE再推进允许的不同工作。


## 最新免费验收与播放入口（本轮22:55 UTC触发）

- paid与保留数量不变：71calls/27repair/other9，a103为唯一approved，a002仍HOLD。无新语义许可、无下载或推理、无新付费提交。所有75个原远端任务已完成。
- a103全240最终640RGBA头脸/头饰2×审阅完成，无新增硬伤；正常眨眼有帧号说明，外侧发丝/全身不冒称同覆盖。quality/additional-audits/a103-all240-final-face-01/review.json/.md。a002第二个独立审阅看全240下裙点，暖色点约3×2像素依附荷叶边，无独立长柄/摆动，原因未定；继续HOLD，不叫已证尾巴，不擦除。quality/additional-audits/a002-rgba-small-point-independent-01/。
- scripts/kurisu_playback_collector.cjs 已实际运行：独立临时profile、隐藏离屏窗口、只GET/HEAD8768、单解码器、不改媒体/用户实例。第一次Electron43入口guard未进main只停QA PID8648；第二次182回调未满200保留false；第三次联合预缓冲、60fps离屏和回调外低频Canvas采样，原200门槛未变，真实10秒循环+暂停恢复通过，260回调、measured quality新增261帧/drop0/corrupt0、Alpha6采样真。两次有意义报告及首次启动失败、3张背景对照截图已固化quality/additional-audits/a103-browser-playback-01/。不是人工连续视频审阅/真实pet窗口性能；只有1合格，distinct动作切换未测。collector完成自退出，不能盲重跑。
- motion源复用门禁 scripts/kurisu_motion_reuse.py +Wan生产/diagnostic prepare/submit/CAS集成，38相关测试通过。真实withdraw两种schema均识别，校验固定证据SHA/源SHA/asset及明确谱系，坏证据fail closed；a001旧driver52354…4e183及其Wan诊断后代7f282…d241不能重新驱动。历史已完成任务恢复不受影响，background-only/soft报告不误杀。quality/diagnostics/motion-source-reuse-audit-2026-10-31.json、motion-source-reuse-schema-normalization-2026-10-31.json。
- a014/a015稳定化只读可行性审阅：原白底且历史243/243背景失败，均匀几何稳定不能变成green-only；未转码/拟合/返生成，temp/kurisu/motion-driver-bank-01/stabilization-feasibility-readonly-01/report.json。
- FPL AI验收能力只读确认：6schemes unavailable（API视觉模型未选，其余code-agent未授权）；会取12均匀帧，agent最多另查24帧，非整视频理解，不能代替240帧/连续检查。未配置全局模型、未推理。quality/diagnostics/fpl-visual-acceptance-capability-2026-10-31.json/.md。
- 方法问题仍等待原问题的人类答复，不能重复询问或把heartbeat当回复。没有新的具体green-only可行假设时不重放失败配方；定时任务保持ACTIVE，继续检查外部变化并保留已完成免费改进。


## 蓝幕历史已复核（heartbeat106，00:40 UTC）

- 用户此前“绿底或者蓝底都可以”已覆盖普通蓝幕；不是需要再次问额度/颜色许可。实际蓝幕早已生成过：a022 attempt1 task08a62f5e-26aa-477f-9675-7e428a689d62、a023 attempt1 taska93f1a48-6da4-4889-917d-c677b5d90bc9。报告quality/diagnostics/blue-background-history-2026-10-31.json。
- 两真实request均H3Film/reference/10s/16:9/768p，唯一reference962864a7-1782-4342-aa8a-85a9c08990ca；本地RGB参考1280×720、SHAced8fc6f188f6188a7d30af251cc9a19b433dfcf0507d24bfe02825d5d6aeb19匹配，原生1px边界全(0,0,255)。remote prompt SHA与归档strip后字节匹配，明确全程纯蓝及发丝空隙，不能把blue eyes文本误当已测蓝幕。
- 既有源背景扫描均239/240失败（首帧蓝、后近白），没有保蓝且正常前景的合格片；本轮只读核对，未重新解码/新生成。蓝chroma key尚未实际执行，因背景前置失败退出，不能把换key色当白源可修。80%蓝/FL蓝/Wan蓝未测只是不同组合，尚未形成可行量产路线，不盲试所有排列。
- 原远端75均completed、0active，服务/预览HTTP200、service23711/monitor4605保留。71calls/27repair/other9及1approved不变。方法问题仍等待原人类答复；heartbeat和时间经过不算许可。


## 最新人类许可与体验修复（覆盖前文等待状态）

- 人类已回复“允许先做1条小样”。library.method_clarification 已短锁记录 authorized_one_existing_clip_trial / authorization_received=true。唯一a105 FL3原片SHA5460f738fa8678600fc5d37fc4334e551deec03c013db41b0242c58059b13aac；允许本地语义Alpha，不改源RGB、不白阈值挖洞/重绘五官；只一条试验，先独立QA再决定能否扩大，不能重提远端原任务。green_gate实际装独立rembg/onnxruntime和官方anime模型，animation_qa独立审阅，production_queue预览/历史；先查agent和PID避免第二个推理。
- 用户指出桌面静止/只剩1动作，root已明确解释追加撤回导致，并承认未及时说明且定时轮询没有完成持续制作目标。当前仅a103保留不是106完成。完整库持续制作仍目标，不把试验当终点。
- 为恢复实际动态体验，root已把preview_static_placeholder归入preview_default_history并清除当前声明，设preview_idle_override={action_id:a103,sha256:615aa8f01c1fb16a5ecae0938a7d27a31caf7b409967f63bf9e4cb6377797072}。实际live-config idle已热更为工作状态-整理实验记录__v_615aa8f01c1f；service23711/monitor4605未重启，id/name/size/position/display/facing/fixed/confine/font保持，自动余额/work/whisper仍off，无合格移动漫游off。这是借用原名临时默认，不计缺失idle完成，不恢复有硬伤动画入运行池。temp/kurisu/dynamic-default-restoration-01/保存前后验证。
- 历史文件都在，不删除：production_queue新增history.html并在preview.html加醒目入口，用户可看已生成原片/归档版本及原因，不改变approved或正式播放池。semantic单样预览quality/diagnostics/semantic-a105-trial-01/preview.html，未验收不计106。当前71calls/27repair/other9不变。


### 同一a105小样实际进度（不再等待用户许可）

- isnet-anime本地240帧已完成，无远端生成调用。基线c96349…5320、语义+旧greenAlpha交集f30d57…9b4f均640360/24fps/10s/240/VP9Alpha/noaudio；独立QA确认仍有可见细绿，不能放行，不增加通过数。nativeRGB+modelAlpha原样留temp/kurisu/semantic-a105-trial-01。
- 原图sourceRGB/原mask及每个recipe都保留。官方ML前景估计和窄auburn轻去色6帧无充分改善、已停；直接全局缩窄green阈值会误删带绿白头饰/裙边，不采用。官方CF直接semantic种子会把可靠绿发缝重填绿，亦拒。当前green_gate在同一小样检查可靠饱和绿BG=0约束的CF融合，不是白RGB阈值/绘五官/手工抹尾，不扩其它动作。先查其agents/PID/最新report，不能重复另起推理。
- root已实际跑隔离Electron基线loop1/251回调、暂停恢复/Alpha采样通过，测量total261/drop10/corrupt0，故不得写零丢帧或视觉通过。temp/kurisu/semantic-a105-playback-01/report.json。QA也实际在IAB启动基线，详其最终审阅范围；有视觉硬伤时不继续做无收益旧版全面复核。
- history.html真实可看45个已生成动作/130个历史文件，有原/处理/归档与问题标签；未更改合格数或把坏历史放入运行池。下一批真正0次首轮生成已预备a031–a042，quality/diagnostics/next-first-generation-batch-2026-10-31.json/.md；完整106仍目标，不能把定时任务退化为永久只查状态。新路线通过前不六路盲刷，验证后按原全部生产目标继续。


## 最新人类策略：先铺开其它动作，每条最多一次纠正（最高优先，覆盖早期无限返修授权）

- 用户明确：“你先别一直返修了，先做其他动画，然后只迭代一次。失败了就先继续推进其他的动画，不要一直卡在同一条，除非我要求，你才继续迭代。”总调用额度持续授权仍在，但不再允许用其自动扩大同一条迭代。每条首轮标准制作+最多1次纠正（重生成或额外本地修补择一），失败记录后转其它未首轮。历史已多轮失败不自动再开，追加纠正必须未来人类点名。library.iteration_policy已记录；green正在最小执行guard，不能拿旧高cap绕过。
- a105语义已产choke8a4544…b1e，但独立QA于f37/1.542s发现正常640中醒目的孤立浅粉白弯条（约x190–204,y80–203），源背景被模型留下，REJECT。原0/24/120/239边缘改善不抵消该硬伤，保持1合格不凑数。该条本轮结束，禁止继续修任何参数/算法/色彩或模型，也不再扩derived批准helper。
- 两条其它新动作已真实提交：a031#1伏案敲代码 task5e0fb9eb-c689-4bfd-a59c-3d659334872f；a032#1检查试管 task1da86fb9-0a03-410a-a9b3-a107600516e1。mainH3/reference80%RGBA/正向人类布饰prompt-v2/BLUE/10s16:9768p。当前73calls/27repair/other9（无新增返修），2远端同时生成；scope exact2已closed防重复。source-only恢复watch PID24676 KEY h3-framing80-blue-probe-01，仅原ID poll/materialize/download/native BLUE scan，不key/semantic/approve。元数据、recovery-handoff/PID/log在temp/kurisu/h3-framing80-blue-probe-01。先查这些原task，不重提。
- production_queue正在准备下一4个未首轮a033–a036，拟追加至6模型并行；root核manifest/激活后提交，不能继续卡a105等处理。最新人类要求失败转其它，不把老同类背景pause当永久只检查/不制作理由；仍保留失败状态、不伪造通过或正式提升。
- 当前真实区分：45个动作已有原片、合格1、在途2，不是只生成过1。source文件和历史130个版本在history.html，不同完成口径不能混淆。主画廊stats加入已有原片数，合格数仍1；小时汇报聊天已只读核对，未获消息授权所以没有跨聊天发消息或修改其自动化。


## 协作聊天及持续首轮owner（用户已明确授权新聊天帮忙）

- 已创建本地dsh-pet协作聊天：01a18fe5-b0e8-7431-8930-21a83cebe0fe负责a069–a089时节21份首轮prompt（唯一文件aNNN-firstpass-seasonal-v1.txt），handoff quality/collaboration/seasonal-prompts/handoff.json。生产owner不要覆盖这些文件，依SHA消费；无模型生成或ledger写。
- 01a18fe5-d4ac-7b53-bb13-e731fb9e855f负责a033–a091新原片独立前景QA，消费quality/evidence/first-pass-native/aNNN/attempt-1/的原生PNG/manifest，报告quality/collaboration/source-qa/。该聊天无FFmpeg/生成/SDK写/globalledger改动，缺包写needs-evidence.json。主子agent animation_qa改做唯一原生证据provider（1本地decoder），production_queue全source回收降max1，合计≤2；模型max6。
- production_queue为唯一Paid owner，first_pass_campaign已授权固定55个a037–a091首次，每条本campaign只1次，绝对campaign calls ceiling132（授权时77），后续≤6模型持续补空位，无需逐波停等root。每波不可变skill prompt/SHA/fresh planned0/CAS仍必需；原任务恢复、source-only BLUE scan，不key/semantic/approve或开旧repair。总130最后若需2次可按standing quota-ensure审计加至132，不能扩同条修补/othermodel cap或重置历史。
- a037–a042已真实提交，当前83calls/27repair/other9，任务分别664dacad-8f59-471e-a3f5-2ac229c2dfe3、b7a45ff4-8456-4b09-8415-bd7e369072ee、6f3deadd-9638-43db-b557-debbd589037e、bf5a9811-956c-4a8b-9128-8e311cd28ac2、c8bcdbbe-f977-4fd2-85e3-220560aeb207、97e36fc5-0e2f-41ef-bac4-53bebc2a87f5。scope03已closed防重复，后台首轮controller正在由唯一owner部署；先查PID/handoff别重复起。原4watch25742与已退原2watch24676记录保留，不能重提它们。
- 最新policy同条首轮+最多一次纠正已经执行guard与必要测试；明确continue_other_actions_after_failure下，source质量失败留档拒收，但不再使其它未首轮有界任务自动halt，未知提交/供应商不可用仍真实阻塞不能盲重提。生产自动化106已通过官方tool更新成最新breadth-first/一次纠正规则，仍ACTIVE/15分钟；未改每小时汇报聊天的自动化。
