# Thistelles 官网实施计划（site/index.html 单文件 SPA）

## 决策记录
- 中英双语切换 · 蓟紫 #9D8FF0 强调色 · 单文件零构建静态页 · CTA 仅 install 命令 + GitHub
- 部署：仓库 `site/` 目录，Vercel Root Directory 指向即可

## 核心创意：「声音长出荆棘」
品牌 DNA 来自代码库既有资产：`waveform.py` 的荆棘藤蔓波形、镂空麦克风字形、
corrections.md 的「越用越准」。页面即那根藤——一切元素都是长出来的，不是淡入的。

## 文件与分段写入策略
`site/index.html` 单文件（约 1000 行，内联 CSS/JS）。
单次 Write 超长会截断 → 分三段写 `site/.p1/.p2/.p3` 后 cat 合并，删除分片。

### P1 head + CSS（约 380 行）
- tokens: --bg #08090A --ink #EDEDEF --dim #8A8F98 --accent #9D8FF0 --line rgba(237,237,239,.08)
- 字体：Space Grotesk(Google) + 系统栈 + ui-monospace
- 组件样式：固定导航(blur)、左脊线(.spine 桌面可见)、hero、.panel 画布面板(holding/decay 态)、
  .caption 打字行、.chip 安装块、三态 .statecard(on 脉冲)、词典 .dic-grid(.mdbox+.live 纠正动画)、
  .facts 三联、.term 终端块、footer、.reveal 生长入场(clip-path)、reduced-motion 降级

### P2 body 结构（约 210 行）
- nav：字形 logo(SVG) + Thistelles + 语言切换(EN/中 pill) + GitHub 图标
- hero：kicker(MACOS·菜单栏·本地推理) → h1 两词错峰生长(按住说话/文字即达) → sub →
  canvas 演示面板(.hint/.timer) → .caption 转写行 → chip(bash guide.sh install 复制) + GitHub ghost
- section 01 三态按钮：三卡片 开始录音/停止录音/转写中…点击取消，on 态轮播脉冲
- section 02 自定义词典：左 corrections.md mono 片段(- 隐形千疑 → 引擎迁移 等)，右 .live 句子
  「今天的隐形千疑评审会改到周四」纠正动画(from 划除→to 蓟紫飞入)+重播按钮；EN 用 reciever→receiver
- section 03 本地宣言：三联 facts 推理在本地 Metal GPU / 断网照常工作 / 语音零上传
- section 04 安装终端块：$ bash guide.sh install + 注释行；req uv · macOS 12+ · Apple Silicon
- footer：MIT · GitHub · 以荆棘之名 / In the name of thorns
- 全部文案节点带 data-i18n 键

### P3 JS（约 420 行）
1. I18N 字典(zh/en 各 ~35 键) + applyLang()：data-i18n 替换、html.lang、localStorage 持久化、
   默认 navigator.language 前缀 zh→zh 否则 en；切换按钮显示目标语言
2. Thorn 引擎：移植 _ThornView(32 刺、平滑振幅、贝塞尔刺形、藤蔓基线、辉光层)；
   y 轴翻转适配 canvas；DPR 缩放；idle 呼吸噪声 / recording(指针速度+合成语音包络) / decay
3. Hero 控制器：panel pointerdown/up + Space 键(非输入焦点)；holding 计时 m:ss；
   松开→衰减→scramble 打字转写到 caption(含光标闪烁)；打完回 idle
4. 三态轮播：2.2s 循环高亮 statecard
5. 词典序列：IntersectionObserver 进入视口播放一次(from 划除 450ms→to 飞入)+重播按钮
6. 脊线进度：scroll 监听 → .spine i scaleY = 滚动百分比
7. Reveal：IntersectionObserver 加 .grown
8. 复制 chip：clipboard API + ok 态反馈 1.2s
9. prefers-reduced-motion：canvas 静帧、reveal 即现

### Meta
favicon 内联 SVG(黑底圆角+白荆棘笔画)；og:title/description；无第三方 JS 依赖
（仅 Google Fonts link，离线时优雅降级系统字体）

## 验证门禁
[ ] python http.server 起本地服务 curl 200
[ ] node --check 抽出内联 JS 语法通过（无 node 则人工复核）
[ ] 中英切换全键覆盖（grep data-i18n 数量 == 双语字典键数）
[ ] prefers-reduced-motion 分支存在
[ ] 文件 <120KB，无外部 JS 依赖
## 非目标
无定价/证言/订阅框/博客；不做多页路由；不生成 og 图（仅 meta 文字）

## 部署说明（交付时附）
Vercel Dashboard → New Project → 选仓库 → Root Directory 填 `site` → Deploy。
或 CLI：`vercel --cwd site`。
