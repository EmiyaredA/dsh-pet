# 红莉栖猫耳女仆 · 独立桌宠包

分支：`codex/kurisu-pet`。完整 106 条动画库正在制作，原先通过验收的两条样片继续可用。正式配置在全部必需素材验收前保持样片版本；不要把制作中节点当作完成素材。

## 106 条动画制作进度

- 持续制作中，实时数量及调用次数见 [library.json](library.json) 和预览页；未完成完整库。FPL 的“托腮推理”和“专注敲键盘”已沿用原供应商任务 ID 恢复、下载并验收，恢复没有增加模型调用。网络查询使用逐任务退避，提交阶段不明仍禁止自动重提。
- 移动方向已纠正为**向左侧身原地步态**，向右由运行时镜像；窗口只改变横坐标，前后各 2 秒转入/退出侧身。旧正面/斜正面素材已撤销验收并存档。留白版轻步行走、小跑已经通过；抱笔记本侧身挪步仍因裁耳未通过。
- 当前单条上限：轻步行走、被提起悬空、被戳脸鼓腮各 3 次，小跑 4 次，其他动作 2 次。鼓腮第三版仍变成开心贴脸，未计为合格；拖拽第三版已通过。所有历史失败和撤回尝试仍计入总额度。
- 完整清单与任务记录：[ACTIONS.md](ACTIONS.md)、[library.json](library.json)。新一轮 104 条首轮 + 最多 26 次返修，共不超过 130 次；备用模型两次额度已用完，后续统一 H3 影视画质。单条例外须有明确用户批准。
- `preview.html` 展示实时生产进度，支持 13 类筛选、搜索和单条按需播放。未通过条目不能播放为正式结果。
- `kurisu-config.full.json` 是 106 条槽位草稿，**不是当前安装配置**。全部通过后才提升到 `pet/kurisu-config.json`，开启漫游、余额、工作状态，自动 AI 碎碎念始终关闭。
- 唯一角色参考为定稿正面图；三视图仅存档。获批的 [留白构图](references/kurisu-front-safe.png) 由 FFmpeg 等比缩小原图并加绿幕生成，未改造型、未另行生图。每次提交保存输入素材 ID、哈希及 H3 六段提示词快照。下载、转码失败只恢复已有结果，不重新调用模型。
- 若模型返回近白底，使用边缘连通抠像保留封闭轮廓中的白色蕾丝，再逐帧检查和人工验收，不因成功转码自动通过。可通过 `KURISU_MATTE_PYTHON` 指定含 OpenCV、numpy、Pillow 的独立 Python 环境。小跑与轻步行走的灰色多余尾部使用限定区域清理，记录在对应尝试的 `local_edit`；其他动作不自动清理角色部件。
- 余额、碎碎念等双脚原地站立、道具位于头部下方的固定动作，可用整幅等比缩放与平移修正模型的尺寸漂移；不改变身体比例。该处理不用于跳跃、拖拽、行走、伸展、转身或女仆礼，避免消除真实动作。所有本地修正仍须重新解码与视觉验收。
- 工作状态第三档“整理实验记录”已改用小型灰色笔记本电脑及折叠支架，包含查看数据、少量触控板归档、点头确认和收回道具；旧纸质版本已撤销。
- 该电脑动作随后发现外壳显示界面的朝向错误，错误版已撤回；以同一源视频中正确的灰色外壳为表面基准，对 140 帧背盖做局部跟踪修复，并重新通过透明度及三背景检查，未新增模型调用。电脑屏幕和键盘朝角色，观众只见灰色背盖；原始错误结果与修复后透明交付分别保留。所有含“抱笔记本/接住笔记本”的动作均指小型笔记本电脑。
- `source/library/` 保存原视频和未通过候选，不进入 Git/安装包；正式动画保持平铺在专属目录中。

生产命令需安装 numpy/Pillow，且通过已配对的 FPL 官方 SDK 访问桌面 App。先 `status` 核对，再 `tick` 恢复已有任务；同一时间最多两个模型任务。视觉检查后才通过 `review` 录入验收。禁止重新执行 `init` 或删除台账来绕过预算。

```sh
python scripts/kurisu_library.py status
python scripts/kurisu_library.py tick --no-submit  # 仅恢复，不新生成
python scripts/kurisu_library.py tick              # 按额度补到最多两个任务
python scripts/kurisu_library.py review --action a002 --verdict pass --reason "具体验收依据"
python scripts/publish_kurisu_library.py            # 仅归档通过的透明视频
python scripts/finalize_kurisu_library.py           # 只写完整配置草稿
python scripts/finalize_kurisu_library.py --promote # 全部 106 条通过后才允许
```

以下安装说明描述当前可用样片；更新时可以使用 `node install.mjs --dsh-home "数据目录" --update`，旧包自动备份，并保留实例 ID、名称、尺寸、位置和显示设置。默认打包会拒绝未完成的完整库；仅交付明确标记的可用子集时才使用 `--allow-partial`。

## 安装与使用

解压安装包后，在本目录运行：

```sh
node install.mjs --dsh-home "/你的/DSH数据根目录"
```

`--dsh-home` 是 DSH 数据根目录，可从设置页“卸载与存储”核对；不是插件所在的 `node_modules` 目录。安装脚本只新增 `dsh-pet/pet/kurisu-config.json` 和 `kurisu-animation/`，保留肥鱼配置；若已有同名包会停止，避免覆盖。

也可手动将本包 `pet/` 下的两个项目复制到 `<DSH_HOME>/dsh-pet/pet/`。刷新 DSH 网页，或在桌宠右键菜单选择“重载配置”以重建桌面窗口。

```text
pet/
├── kurisu-config.json
└── kurisu-animation/
    ├── 待机呼吸.webm
    ├── 点击回应-傲娇.webm
    └── *.report.json
```

动画文件直接平铺在 `kurisu-animation/` 中；现有 pet pack 素材路由不读取其 `webm/` 子目录。报告文件不是运行必需文件。

- 待机默认循环；点击播放傲娇，可通过右键“动作”菜单点播。
- 拖拽暂沿用待机画面，复用原项目的拖拽、抛掷与弹性反馈。
- 关闭自动漫游、余额、工作状态动画及自动碎碎念；默认网页和桌面均显示。
- 两条视频均为 10 秒、640×360、24fps、VP9 Alpha WebM，无音轨。面向 Electron 与支持 VP9 Alpha 的 Chromium 浏览器；本包没有另做 Safari 的 HEVC Alpha MOV。
- 宠物实例 ID 为 `kurisu1`，默认名称“红莉栖”，大小 462。需要多只或调整位置时编辑配置。

## 人设与生成记录

[定稿正面图](references/kurisu-front.png)是唯一身形比例基准：栗红长发、蓝紫色眼睛、大头短圆身体、黑白女仆装、白色蕾丝发箍、黑外粉内双猫耳与粉色蝴蝶结，**无银色发夹**。

[三视图](references/character-sheet.png)出现了身体略偏高的差异，仅作服装结构与设计过程记录，未用于最终视频返修。

人设由 Codex 内置 `image_gen` 生成；最终视频通过 Future Props Lab 官方 SDK 提交，模型为 `H3多图多音频生视频(影视画质)` / `minimax_h3_zm_nono`。提示词使用 `h3-prompt-writing` 的 Ref2VA 六段结构，保留在 `prompts/idle.txt`、`prompts/tsundere.txt`。

首轮两条视频同时参考正面构图图和三视图，模型添加了彩色光斑，未通过画质验收。用户批准各返修一次后，第二轮只使用定稿正面图，明确固定调色板、均匀白光、数字绿幕和无光斑约束，得到当前交付版本。首轮提示词以 `*-round-1.txt` 留档，原始视频保存在被 Git 忽略的 `source/` 下。

原两条样片阶段共调用 **4 次**，单独保留于 `production.json`；完整库新增调用另记于 `library.json`，不混淆两阶段额度。完整库备用模型两次额度已用完。

FPL 位置：**视觉创作工坊 → 红莉栖 Q版桌宠 · 样片**，项目 ID `585ee45b-48a2-4f85-a6d6-3e7ae1002ea9`。其中保留原始生成的两个版本，另有“透明交付”节点。生产状态、输入参数、任务与素材 ID、SHA256 和转码报告见 `production.json`。

## 预览与复现

打开 `preview.html` 可切换动作和浅色、深色、棋盘背景；若浏览器限制本地媒体，可在本目录运行 `python3 -m http.server 8768 --bind 127.0.0.1` 后访问 `http://127.0.0.1:8768/preview.html`。

在仓库根目录使用 Python 3、numpy 和带 `libvpx-vp9` 的 FFmpeg 重建：

```sh
python3 scripts/build_pet_pack.py \
  --input "pet-packs/kurisu/source/round-2/待机呼吸.mp4" \
  --input "pet-packs/kurisu/source/round-2/点击回应-傲娇.mp4" \
  --output pet-packs/kurisu/pet/kurisu-animation \
  --work-dir temp/kurisu/render --overwrite

python3 scripts/package_pet_pack.py \
  --pack pet-packs/kurisu \
  --output temp/kurisu/kurisu-pet-pack.zip
```

FFmpeg/FFprobe 默认从 PATH 查找，也可通过 `--ffmpeg`、`--ffprobe` 显式指定。没有原始视频时，可从 FPL 项目下载第二版，再按上述路径放入。打包脚本不会打入原始视频、临时文件或个人配置。

## 验收结果

- 分别抽查两条视频的多个时间点，第二轮无首轮彩色光斑；原图短身比例保留，猫耳、发箍、手脚完整，无切镜。
- 所有 480 帧均解码验证真实 Alpha、非透明内容边界与尺寸；两条均 240 帧、10 秒，且无音轨。
- 站立高度统一为 270px、脚底目标为画布 y=330；首尾脚底偏差不超过 1px。生成动画仍有少量自然线条变化，未宣称像素完全相同。
- 已检查浅色、深色和灰色背景下的头饰、发梢、裙边和鞋底，预览支持透明棋盘。
- 真实配置加载器识别独立动画池，未回退到肥鱼素材；隔离 DSH 数据与 Electron profile 中两条动画均取得桌面实际“播放中”回执。
- 原项目配置与动画选择的 137 项测试，以及新转码脚本的 4 项回归测试通过。点击与拖拽沿用既有组件；未修改渲染、物理或菜单代码。
