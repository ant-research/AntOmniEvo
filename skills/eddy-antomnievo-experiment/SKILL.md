---
name: eddy-antomnievo-experiment
description: 主动沟通型的 AntOmniEvo 优化实验搭建助手的前置步骤集——帮用户把某个 eddy 业务 agent 接入 AntOmniEvo:对齐实验根目录(exp_root)与 candidate store 目录(两个概念分开)、创建 venv、装 AntOmniEvo、读 README 选 example;对齐数据格式并在 antomnievo/dataset 写 data_inst + data_loader;和用户对齐 agent module 在哪、启动入口、要优化哪些文件,照 example spec 写 AntOmniEvo spec;在业务项目 scripts 写 generate(做 load spec)和 evaluate;检查业务仓库代码 venv;冒烟测试并把产物路径给用户确认。当用户要"为某个 eddy 业务 agent 搭 AntOmniEvo 优化实验""接入 AntOmniEvo""写 generate/evaluate""先搞数据再写 gen/eval"、或想开始 AntOmniEvo 实验搭建时使用。
user-invocable: true
---

# eddy-AntOmniEvo-experiment

主动沟通型的 AntOmniEvo 优化实验搭建助手。本技能是一个会主动提问、边做边验证的编程助手,帮用户把某个 **eddy** 业务 agent 接入 AntOmniEvo。**流程分两段**:步骤 1–6 是 bootstrap(对齐实验根目录 + candidate store 目录 / 数据 / agent module / spec / generate-evaluate + 冒烟,用户确认无误);步骤 7 起接 AntOmniEvo 优化循环组件(System → Evaluator → Proposer/optimizer/入口 → `await optimizer.optimize()`),每接一个先自验再下一步。

### 用户需要提供什么 vs 执行者自己drive 什么

**执行者主动drive 的** — 不需要用户操心:
- 装 AntOmniEvo / 建 venv / 选 example(步骤 1)
- 写 AntOmniEvo 的 System / Evaluator / Optimizer 子类 / 入口脚本(步骤 7–10 代码)
- eddy 轨迹解析(`parse_eddy_trajectory`)
- 跑冒烟 / 验证 / 日志分析 / 看结果 / 总结

**需要用户提供/确认的** — 业务知识,只有用户知道:
- *(步骤 0)* **eddy 高代码系统的代码地址 + 评测代码地址**(git 代码地址或本地代码仓路径都行)—— 执行者要下载这些代码做后续所有事;评测代码可能与系统同仓库,也可能独立。**同时指定例子脚本**:系统运行参照脚本 + 系统评测参照脚本(步骤 4 写 generate/evaluate 的复用对象)。
- *(步骤 2)* 评测数据在哪?**gold schema 长什么样** — 你读 case sample + 跟用户复述确认。
- *(步骤 3)* agent module 包路径?入口?**哪些文件可编辑**?
- *(步骤 4)* 可参照的系统运行/评测**例子脚本**(步骤 0 已拿到就直接用,没给才在这步问)?打分标准是什么?
- *(步骤 5)* 业务项目 venv 是否就绪?model key 够吗?
- *(步骤 10)* proposer api_key / base_url / model; system 的 model key / MCP token;**train/val 数据怎么来 + 多少条**

### 上下文恢复:长跑优化 → 用户清上下文后
📖 详细 → `references/context-recovery-recipe.md`。SKILL.md 这里只记 trigger:
每次跑优化或跑完,在 `<exp_root>/NOTES.md` 追加实验状态(路径 + 配置 + credential 过期时间 + iteration/best candidate/遗留事项)。
下次新上下文只读 NOTES.md(`<exp_root>` 下)+ statistics.json(`<run_dir>/logs/` 下)+ tail log 即可恢复。resume = 同 `--config`(config 里 `<run_dir>` 不变 → AntOmniEvo 自动 resume from checkpoint)。
⚠ credential 过期后 batch score 从高跌到低 → 从用户拿新 credential → 更新 config YAML + run.env → resume。

## 实验记忆 NOTES.md(贯穿所有步骤 — 避免后续重探整个 repo / 网)

**实时记,不等步骤做完** —— 目标是"用户随时 clear 上下文,新会话也能无损恢复继续推进"。每个关键动作**发生后立刻**追加 `<exp_root>/NOTES.md`(累积 markdown,每段 `## 步骤 N — <标题>`;**放实验根目录,不放 candidate store 的 run 目录里**),续做 / 新会话**先读它再动手**,不重复翻 repo / 联网重检:
- **进行中状态(最易丢、最关键)**:正在跑什么(后台任务/冒烟/长命令 + 命令本体 + 产物目录 + 开始时间)、跑到哪个小步骤、下一步打算做什么。任务完成/失败后立刻用结果更新掉。clear 后读到最后一条"进行中",就能接着等/接着查产物。
- **路径/约定**:agent module 路径、入口 `<pkg>.<module>:<attr>`、可编辑条目(`--editable` 列表)、`INITIAL_SPEC_DIR`、`spec_def` 文件、`generate.py`/`evaluate.py` 路径、业务 venv 路径、model key 是否就绪、cases 路径。
- **决策/对齐**:跟用户对齐的"打分法"(哪几层 scorer;阈值)、用户给的对比例子、可编辑面边界。
- **雷达发现**:仓库里 grep/find 到的现有 eval 代码关键文件 + 行号(每项目不同,记你找到的 + 用户确认的)、踩过的坑(以实际为准,如重数据每 rollout 全量拷 → symlink/共享 之类)。
- **已验证状态**:exp_root / candidate store 根目录 / run 目录路径、AntOmniEvo import OK、各冒烟过的断言/命令。

**新会话恢复流程(clear 后第一条消息先看这个)**:读 `<exp_root>/NOTES.md` 尾部 → 定位中断点(哪个步骤、有没有"进行中"任务)→ 若记录里有后台任务/长命令,**先查其产物文件是否已生成**(inference.jsonl/predictions.jsonl/details.jsonl 等)判断跑完没有 → 补齐中断处继续,不重复已验证的工作。

## 行为准则(主动沟通)

1. **先问再动手,不要猜**:exp_root / candidate store 目录、数据、agent module、业务代码、字段长什么样——先问用户 + 读真实文件确认,再写。拿不准就停下问。
2. **验证后再往下**:每一个步骤产出后,自己先冒烟/自测验证正确性。
3. **确认门 = 阶段性同步门(每个步骤都有,直到步骤 6 最终确认都不可省)**:做完一步:① 把本步产物(路径 + 关键内容/数字 + 怎么看)告诉用户;② **把本步关键信息追加写入 `<exp_root>/NOTES.md`**(见"实验记忆 NOTES.md");③ 告诉用户**已完成哪些步骤 + 还剩哪些步骤**;④ **问"是否继续下一步"**(收到"继续" / 明确同意才进;要改/补就停下补)。
4. **数据先对齐**:数据格式不先对齐,后面 generate/evaluate 全是空中楼阁。
5. **写入记忆,省后续重探 + 实时可恢复**:每步把"后续会用到的关键事实"(路径/入口/约定/找到的代码/字段/决策/坑)写入 `<exp_root>/NOTES.md`(#3② 即此动作);**进行中状态(在跑什么/产物在哪/下一步做什么)发生即记、完成即更新** —— 用户随时可能 clear 上下文,NOTES.md 是唯一恢复凭据(见"实验记忆 NOTES.md"的恢复流程)。续做先读它,不重复翻 repo / 联网重检。
6. **不在中途擅自连跳**:每步只在"阶段同步 + 用户说继续"之后才推下一步;没收到继续就停。所有 6 步都完成、最终确认无误,才进 AntOmniEvo 后续(System/Evaluator/Proposer/`await optimizer.optimize()`)。
7. **禁止随意修改用户已有的文件**:业务仓库/评测仓库里的既有文件一律不改,除非用户当场点名要改;新增文件(generate.py/evaluate.py/venv/组件)只落在流程必需处,创建后在同步里显式列出路径。

整个流程:**步骤 0 拿代码 + 配各代码目录环境,步骤 1–6 是 bootstrap**(冒烟无误后进接线),**步骤 7 起接 AntOmniEvo 优化循环**;每一步都按"先问/读确认 → 做 → 自验 → 告知用户确认"四小动作为之:
**步骤 1 对齐实验根目录 + candidate store 目录 + 配置环境 → 步骤 2 对齐数据格式 + 写数据层 → 步骤 3 对齐 agent module + 写 AntOmniEvo spec → 步骤 4 写 generate/evaluate → 步骤 5 检查业务仓库代码 venv → 步骤 6 冒烟 + 用户确认 → 步骤 7 写 AntOmniEvo System 模块(候选 spec → 预测)→ 步骤 8 Evaluator → 步骤 9 Optimizer 子类 → 步骤 10 example 入口 + config + `optimize()`**。

---

## 两个目录概念(实验根目录 ≠ candidate store,先分清再动手)

"workspace" 一词在本技能拆成两个**不同**概念 —— 路径不同、内容不同、resume 语义只挂在第二个上,别混:

- **实验根目录(`<exp_root>`)**:整个优化实验的**非候选**产物都放这 —— **本实验组件目录(`<exp_root>/antomnievo/`,默认;不是源码 clone —— AntOmniEvo 一律 pip 装包,这里放本实验补充的 dataset/spec_def/System/Evaluator/Optimizer 组件 + 入口脚本 + 最小 pyproject;venv 也在里面:`<exp_root>/antomnievo/.venv/`,它是 AntOmniEvo 的环境)**、`NOTES.md`(实验记忆)、config YAML、`run.env`、`tests/<smoke_name>/`(冒烟产物)、`initial_spec/`。**每实验自包含**:组件目录 + venv 都在 exp_root 内(不共享外部 venv;组件只影响本实验);一个 exp_root 跨多次优化 run 复用。
- **candidate store 根目录(`<candidate_store_root>`)**:**单独开的一个目录,只放优化实验产生的候选数据**;里边**每次 run 一个以时间为后缀的子目录** `<run_dir> = <candidate_store_root>/run_YYYYMMDD_HHMMSS/`(= AntOmniEvo `LocalCandidateStore(workspace_dir=...)` 的落盘路径:`candidates/<id>/` spec 树/meta/changelog/best、`logs/statistics.json`、optim 日志)。**resume = 同一个 `<run_dir>`**(AntOmniEvo 查 `statistics.root_candidate_id`:有 → 续跑跳 root baseline;没 → 从头建);**新 run = 新开一个时间戳子目录**(内置行为,不需要 flag)。

步骤 1 跟用户对齐的是 `<exp_root>` + `<candidate_store_root>` **两个路径**(后者默认建议 `<exp_root>/workspace/`,也可完全独立 —— 候选数据 = spec 树 × 候选 × 代,体积可能很大,想放别的盘/位置就独立);**`<run_dir>` 步骤 10 跑 `optimize()` 时才创建**(步骤 1 不建)。⚠ config YAML 里 `<run_dir>` 的 key 叫 `workspace_dir`(与 `LocalCandidateStore` 参数同名)—— 它指 candidate store 的**单次 run 目录**,**不是 exp_root、也不是 candidate store 根目录**。

---

## 通用约定(贯穿各步)

跨步骤的规则集中在这,各步引用,别散在步骤里。

- **实验记忆(NOTES.md)**:每步产出追加写 `<exp_root>/NOTES.md`(`## 步骤 N — <标题>`),续做 / 新会话先读它再动手。见上方"实验记忆 NOTES.md"。
- **AntOmniEvo 一律 pip 装包,组件放 `<exp_root>/antomnievo/`**(统一约定,不再"代码还是包"二选一,记 NOTES):**不拉源码 clone** —— `pip install ant-omnievo`(core;要可视化 → 再 `pip install ant-omnievo-visualizer`)。本实验补充的模块实现和脚本(dataset / spec_def / System / Evaluator / Optimizer 子类 / 入口脚本)**全部放专门目录 `<exp_root>/antomnievo/`**(默认):里面建本场景包 `<scenario>/`(如 `peizhiagent/`),组件按 `dataset|spec_defs|system|evaluator|optimizer` 子目录排;放一个最小 `pyproject.toml` + `uv pip install -e <exp_root>/antomnievo` 让场景包可 import(PYTHONPATH 兜底);venv 在 `<exp_root>/antomnievo/.venv/`。**不改已装的包**;README/example 等参照从已装包里读(`python -c "import antomnievo,os;print(os.path.dirname(antomnievo.__file__))"`,下面有 `example/`、`model/spec_defs/` 等)。详见 `references/system-recipe.md` §0。
- **tests / smoke 输出目录**:所有冒烟/测试产物统一放 `<exp_root>/tests/<smoke_name>/`(下称 `<smoke dir>`,如 `bootstrap_smoke`、`system_smoke`)—— **不写 `/tmp`、不写业务仓库的 `outputs/`**,集中放实验根目录下方便用户回看;**保留不清**(后面 System/Evaluator 要解析这些真实数据的格式 + 用户回看)。各次冒烟用一个独立子目录,路径记进 NOTES。
- **路径全绝对**:传子进程 / System 构造的路径(`generate_script` / `python_path` / `agent_src` / `local_source_repo` / `env_file` / `output_dir` / `cases_path` / `candidate_meta.spec_dir`)全用绝对路径,子进程 cwd 无关。详见 `references/system-recipe.md` §3 坑8。
- **业务字段不写死 / 不耦合业务名**:运行上下文 / 可编辑条目 / scoring 等业务变化部分从 gold/用户读,不写死业务默认值;照范本**结构**,别照具体**业务包名/字段**。
- **AntOmniEvo 组件的 description 要反映 generate/evaluate 机制**:`System.system_description()` / `Evaluator.scoring_criteria()` 等描述字符串,要基于你**写过的 generate.py / evaluate.py 的真实机制**写清 —— system 写:运行上下文怎么来的、agent 工具面 + 工作流、产出什么 artifact、在哪停(awaiting/HITL)、空产物的失败因(漏改而非崩溃);evaluator 写:拿什么比、分数语义(0/1 各代表什么)、reason 来源、依赖什么前置(如 schema manifest)。这俩字符串注入 AntOmniEvo 的 proposer / 分析 prompt —— **错或空会让它错误归因(把系统/数据问题算到 spec 头上)**。写 System/Evaluator 时一并写好,别留空 / 泛泛。

---

## 步骤 0:拿代码地址 + 下载代码 + 配各代码目录环境

🎯 后续所有步骤都要在**业务系统代码**和**评测代码**上动手 —— 一开始就把代码拿到本地、把各代码目录的环境配好,后面才不卡。

1. **问用户两个代码地址**(别猜,给候选 + 允许自输;**git 代码地址或本地代码仓路径都行**):
   - **eddy 高代码系统代码地址**(业务 agent 所在的系统仓库):git URL 或本地已有 checkout 路径。
   - **评测代码地址**(评测 pipeline 所在):可能与系统代码**同仓库**(如仓库内的 eval 目录),也可能是**独立仓库** —— 问清楚。
   - **用户告诉地址后,执行者自己下载**(`git clone` 到跟用户确认的位置);本地已有 checkout 就直接用,确认路径 + 当前分支/commit 记 NOTES。
2. **同时问用户指定例子脚本**(系统怎么跑、评测怎么跑的**参照脚本**,步骤 4 写 generate/evaluate 的复用对象):系统运行例子脚本(怎么起 agent、出 predictions/trajectories)+ 系统评测例子脚本(怎么打分、出 reason)—— 脚本路径(仓内相对路径即可)或命令;有就在步骤 0 一并拿到、记 NOTES,步骤 4 不用再问;没有就说没有,步骤 4 从零写。
3. **各代码目录分别配环境**:python 项目 → 每个仓库目录下建 venv(`uv venv --python 3.12 <repo>/.venv`)+ 装依赖(`uv pip install -r <repo>/requirements.txt --index-strategy unsafe-best-match`;**装完别再 `uv sync`** —— 会剪掉 requirements.txt 装进来的 deps)。非 python 代码目录(如 java/proto 源码仓库)只需确认 checkout 可用、版本能解析(评测/沙箱按 case 的 code_version export 快照用)。
4. **sanity**:各 python venv 能 import 各自主包(`<repo>/.venv/bin/python -c "import <pkg>"` 不报错)。
5. → [同步] 把各代码目录路径 + 例子脚本路径 + venv 路径 + 依赖状态告诉用户;写 `<exp_root>/NOTES.md`(步骤 0:系统代码地址/评测代码地址/本地 checkout 路径/**例子脚本路径**/各 venv 路径/依赖状态);问「是否继续」,继续后进步骤 1。

---

## 步骤 1:对齐实验根目录 + candidate store 目录 + 配置环境(创建 venv、拉 AntOmniEvo 包)

🎯 把 AntOmniEvo 实验的落地基础备好。📖 具体 venv/安装/目录布局命令 → `references/workspace-setup-recipe.md`。

1. **让用户定两个路径**(『两个目录概念』,都要**独立、可写、别和业务项目混**,跟用户确认再往下)。**问法:给候选 + 允许自输,别开放式问** —— 用 AskUserQuestion(或等效)给 2~3 个**具体候选路径**让用户选,用户也可以选 Other 自己输入;候选按当前环境推断(**默认第一个候选 = 当前工作目录 `<cwd>` 本身**,其余如 `<cwd>/exp-<agent>`、用户惯用实验目录),**每个候选附一句取舍说明**(如"与业务仓库同级,自包含" / "放别的盘,候选数据大时合适");用户选完若对默认有疑虑,可给调整后的候选再问一轮,最终路径以用户确认为准:
   - **实验根目录 `<exp_root>`**:放 `NOTES.md`、config YAML、`run.env`、`tests/` 冒烟产物、`initial_spec/`、AntOmniEvo 入口脚本拷贝(后续从 `antomnievo/example/` 拷对应那份再改)、实验日志、(可选)`.venv`。
   - **candidate store 根目录 `<candidate_store_root>`**:**单独一个目录,只放优化 run 的候选数据**;候选给:默认 `<exp_root>/workspace`(**推荐**,集中管理)、`<exp_root>/candidate_store/`、独立路径(想放别的盘/位置,用户自输)。**`<run_dir>`(时间戳子目录)本步不建** —— 步骤 10 跑 `optimize()` 时才创建。
2. **建组件目录 + 专用 python 环境 + pip 装 AntOmniEvo**:路径定了后,**建 `<exp_root>/antomnievo/`(专门目录,非源码 clone)**,然后**在其中创建一个专供 AntOmniEvo 用的 python 环境**:`uv venv --python 3.12 <exp_root>/antomnievo/.venv`(python ≥ 3.12 即可,有更新版本就用机器上已验证过的),**pip 装包**(不拉源码):`uv pip install ant-omnievo --python <exp_root>/antomnievo/.venv/bin/python`(core)。**问用户要不要用可视化前端**:要 → 再 `uv pip install ant-omnievo-visualizer --python <exp_root>/antomnievo/.venv/bin/python`(README §9;前端还要 `npm install`,见 recipe)。**业务项目自己的运行/打分 harness 不在这里装**(README §5:System/Evaluator shells out → 各自单独装);本技能的 generate/evaluate 跑在**业务项目自己的 venv**,不是这个 AntOmniEvo venv。
3. **读 README + 选最像的 example**(从已装包里读,不 clone):`<pkg> = $(<exp_root>/antomnievo/.venv/bin/python -c "import antomnievo,os;print(os.path.dirname(antomnievo.__file__))")` → 读 `<pkg>/../README*.md`(随包装;没有就 `pip download` 或让用户给仓库地址只读参考)重点 §5/§6/§7/§8 + spec 概念;扫 `<pkg>/example/`(terminalbench / text2sql / rag / appworld)挑系统形态最像的一份当起点——`example/rag/agentic_rag_internal.py`(最简单)、`example/text2sql/birdtest_text2sql.py`(batch-subprocess `System`,更接近"调业务项目 generate/evaluate")。后续写各模块就地参考。
4. **sanity**:`<exp_root>/antomnievo/.venv/bin/python -c "import antomnievo; from antomnievo.store.candidate_store import LocalCandidateStore; print(antomnievo.__file__)"` 能 import(且 `antomnievo.__file__` 指向该 venv 的 site-packages,**证明用的是 pip 装的包**)。
5. → [同步] 告知用户 exp_root + candidate store 根目录两个路径 + AntOmniEvo import OK;写 `<exp_root>/NOTES.md`(步骤 1:两个路径/venv/example 选择);告知已完成步骤 1、剩余步骤 2–6;问「是否继续」,继续后进步骤 2。

---

## 步骤 2:对齐数据格式 + 写 AntOmniEvo 数据层

1. **问清数据 + 读样本**:评测数据在哪?要 train / val / test 三个 jsonl(至少 test)。让用户给路径或贴样本,**读 2~5 行**原始 jsonl,看清楚 schema 再跟用户复述确认。要摸清的字段(以实际样本为准,别套别的领域):唯一 id(`case_id`/`query_id`...)、输入(用户需求 / query / `input.*`...)、gold(可能结构化对象:直接答案 / `golden_*` / `expected.*`)、回放/约束上下文、类目难度(可选)。
2. **在组件目录写数据层三个文件**:`<exp_root>/antomnievo/<scenario>/dataset/` 下放 `<domain>_data_inst.py` / `<domain>_dataset_loader.py` / `__init__.py`(结构对照已装包里 `antomnievo/dataset/<既有某 domain>/` 的一份,**别改已装的包**)。📖 可对号模板 + 字段抽取要领 + 坑 + sanity → `references/data-layer-recipe.md`。
   - `<domain>_data_inst.py`:`<Domain>DataInst(DataInst)`(`antomnievo.interface.data_inst`:pydantic,基类只强求 `id`/`query`/`golden_answer`(str));`from_raw(raw)` 抽取轻字段 + 领域字段,**重数据留 `raw`(exclude=True)+ `to_case_dict()` 回原行**,不要摊平。
   - `<domain>_dataset_loader.py`:`async load_dataset(cases_jsonl, max_samples=0, shuffle=False) -> list[<Domain>DataInst]`,逐行读、跳过无 id / 损坏行、`from_raw` 构造。
   - `__init__.py`;若 `antomnievo/dataset/__init__.py` 有域名注册,按相同方式登记。
3. **sanity**:`asyncio.run(load_dataset('<test>', max_samples=3))` 加载 N 条,且 `id/query/golden_answer` 都非空。
4. → [同步] 把数据层文件 + 加载条数 + 字段理解告诉用户;写 `<exp_root>/NOTES.md`(步骤 2:cases 路径/字段抽取/registry 登记);告知完成步骤 2、剩 3–6;问「是否继续」,继续后进步骤 3。

---

## 步骤 3:对齐 agent module + 写 AntOmniEvo spec(spec = module 的可编辑文件集)

🎯 AntOmniEvo spec = 一目录**可编辑**文件;`LocalCandidateStore` 整树 `copytree` 进每个 candidate(只 ignore `__pycache__`),proposer 在 candidate 的 `spec_dir` 能改任意文件,`SpecSchema` 只软提示、无路径白名单。所以 `initial_spec_dir` 既不能指**整个** module(env/bootstrap/(大/重的非行为数据) 全进每个 candidate、全机器可改、且 重数据 × 代 × rollout 爆炸),也不该外置。**正确:把约定的可编辑条目抽出成独立目录 `<exp_root>/initial_spec/`(目录名固定叫 `initial_spec`,见 item 5),`initial_spec_dir` 指它**;候选 spec 自然就是"按 `<pkg>`-相对路径排好的可编辑文件集",步骤 4 的 generate 再按 `--editable` 条目逐条 load 回 module。📖 SpecSchema + 写法 + 映射 → `references/spec-recipe.md`。

1. **和用户对齐 agent module + 启动入口**:
   - module 路径(运行期包,任何名字,如 `<业务项目>/src/<pkg>`)= 步骤 4 generate 的 `--agent-src`。
   - 找启动入口(**不假定具体名**;很多 eddy agent 的入口在 `<pkg>` 下某处(如 `agents/` 子包,但不限),但不限):grep `builder.build()`/`AgentBuilder`/模块顶层 `agent = …`、读 `app-metadata.yml`/`server-simple.yaml`(`module_path`+`attr`)/`pyproject[tool.arec]` main-entry/`eddy run`/项目 `CLAUDE.md`、列 `*agent*.py` 候选;候选给用户确认入口(`<包内路径>:<attr>`),多义/找不到 → 让用户给。入口 = **"code integrity" 的 import 锚**。
2. **和用户对齐"可编辑文件集"**(过滤 `__pycache__`/`.pyc`):扫整个 module,逐个说清每个文件/目录用途、逐条确认,**跟用户约定要优化哪些文件/目录**(即后续 generate 的 `--editable` 条目)——
   - 可编辑 = 想优化的行为面,**由用户选**:可以是整条可编辑子包(名以项目实际为准),也可只挑一个 skill(如 `<可编辑子包>/<某子集>/`)、一个顶层文件(如 `<顶层可编辑文件>`)、或几处散落(如 `<可编辑子包>/<子集>/` + `<顶层可编辑文件>`)。**边界以用户确认为准**;每个条目都用 `<pkg>`-相对路径表达(`<可编辑子包>`、`<可编辑子包>/<子集>`、`<顶层可编辑文件>`…)。
   - 非可编辑(留 module,不进 spec):运行配置、启动 bootstrap、日志/非行为组件、大或重的非行为数据、其它无需优化的部分(具体名以项目扫描 + 用户确认为准) —— **不进 candidate、不被 load 触及**。
   - ⚠ 可编辑部分**通常不能单独 import 跑**(入口 import 顶层非可编辑兄弟);运行靠步骤 4 generate 的 "load spec" 把候选的可编辑部分按 `--editable` 合并回整个 module 才能跑。
3. **看范例 + 写 spec**(写在组件目录 `<exp_root>/antomnievo/<scenario>/spec_defs/<domain>_spec_def.py`,**只列与用户对齐的那棵可编辑树**;在已装包的 `antomnievo/model/spec_defs/` 选**系统形态最像的**一份 `<x>_spec_def` 作结构参照 —— `spec_schema.py` 的 `FileSchema`/`FolderSchema`、`common_descriptions.py` 可复用描述):
   - `_<DOMAIN>_SPEC_SCHEMA = FolderSchema(name=<根>, description=<行为源 + 约束…>, files=[…可编辑条目树…])`,约束:**无冗余 / 无矛盾 / 泛化(每条通用陈述配一个具体例子)/ 代码完整(任何改动后 `python -c "import <步骤1入口>"` 仍成功)**。
   - `INITIAL_SPEC_DIR` = item 5 抽出的 `<exp_root>/initial_spec/`(**不指 module 包根**)。本步只写 Schema。
4. **sanity + 给用户的确认件**:`<exp_root>/antomnievo/.venv/bin/python -c "from <scenario>.spec_defs.<domain>_spec_def import <DOMAIN>_SPEC_SCHEMA; from antomnievo.model.spec_schema import render_spec_schema; print(render_spec_schema(<DOMAIN>_SPEC_SCHEMA)[:800])"`(spec_def 从本场景包 import,`render_spec_schema` 从已装 AntOmniEvo import);**把三样交给用户确认** —— ① 步骤 2 约定的可编辑条目清单(`--editable` 候变每个条目及其作用)② `render_spec_schema(...)` 渲染出的 spec 树(应**只含可编辑条目**,无 env/bootstrap/(大/重的非行为数据))③ 写好的 `<exp_root>/antomnievo/<scenario>/spec_defs/<domain>_spec_def.py` 路径 + 约束段。让用户核对:边界对不对、有没有该进/该出的文件丟了/多了、约束是否合理。
5. **生成 initial spec —— 问用户用现有代码还是从零,确认后本步就实际抽出到 `<exp_root>/initial_spec/`(目录名固定叫 `initial_spec`,别用别的名)**:
   - **用现有代码**:把 item 2 约定的可编辑条目**逐项**从 module 拷到 `<exp_root>/initial_spec/`(按 `<pkg>`-相对路径排好,跳 `__pycache__`/`*.pyc`;dir 用 `rsync -a --exclude __pycache__ <src>/<ent>/ <dst>/<ent>/` —— **源路径带尾斜杠**才是拷内容,不带会多套一层目录)。抽完 `diff -r` 对源验证逐字节一致。候选初值 = 项目现有可编辑文件 AS-IS,AntOmniEvo 从当前基线开始改。
   - **从零开始**:`<exp_root>/initial_spec/` 留空(或只放最小模板文件),AntOmniEvo 从空白状态摸索出做法。
   - **`initial_spec_dir` 永远指 `<exp_root>/initial_spec/`,不指 module 包根**(spec ≠ agent module:包根含运行配置/bootstrap/(大/重的非行为数据),整树进每个 candidate 会爆炸,且 proposer 能碰非可编辑文件)。
   - **同步时必须向用户讲清 initial_spec 怎么被使用**:它是 AntOmniEvo **root candidate(第 0 代基线)的 spec** —— `optimize()` 启动时 CandidateStore 把 `initial_spec/` 整树 copytree 成 root candidate 的 `spec_dir`,先跑 baseline 评测;之后每代候选 = proposer 在某候选 spec 副本上改出的新树;评测时 generate.py 用 `--spec-dir <候选 spec_dir> --editable <条目>…` 把该树 load 回运行期 checkout 跑(步骤 4 的映射)。**改 `initial_spec/` = 改优化起点基线**。
   - 写进 `<exp_root>/NOTES.md`(initial spec 来源:existing / from-scratch + `<exp_root>/initial_spec/` 路径 + 条目数/文件数)。
6. → [同步] 把「可编辑文件集」边界 + spec 树 + 约束 + initial spec 来源 + `<exp_root>/initial_spec/` 路径**及它怎么被使用**(上一条) + 写好的 `<domain>_spec_def.py` 给用户确认;写 `<exp_root>/NOTES.md`(步骤 3:agent module 路径/入口/可编辑条目/initial_spec_dir/spec_def 路径/initial-spec 来源);告知完成步骤 3、剩 4–6;问「是否继续」,继续后进步骤 4。

> 注:某些已 ship 的 spec_def 把**整包**当 spec、只靠"少动"描述做软约束 —— 那是特例,不是隔离手段;新领域收窄到与用户约定的可编辑集 + 抽出式 `<exp_root>/initial_spec/` 作 `initial_spec_dir` 才硬隔离。

---

## 步骤 4:写业务项目侧 generate/evaluate(generate 做 "load spec")

generate 跑一个 (运行期 + 候选 spec) 组合 —— AntOmniEvo 的 System 跑 generate、Evaluator 跑 evaluate。📖 逐项模式 + 冒烟配方 + 文件形状表 → `references/generate-evaluate-recipe.md`。

**两条 flag,两个概念**(别和 AntOmniEvo 的候选 spec 混):
- `--agent-src <dir>`(必填)= **运行期 agent 包**(import 目标 = 完整可 import 的包;按结构找 = 步骤 3.1 的 module)。`--agent-module`/`--agent-attr` = 步骤 3.1 跟用户确认的入口(项目具体,别假定值)。
- `--spec-dir <dir>`(可选,需配 `--editable`)= **候选的可编辑 spec**(= AntOmniEvo 候选 `spec_dir`,其内部布局按 `<pkg>`-相对路径排好那批可编辑文件)。`--editable <pkg-rel-path>`(可重复)= 步骤 3 跟用户约定的可编辑条目(如 `<可编辑子包>`、`<可编辑子包>/<子集>`、`<顶层可编辑文件>`… 名字以项目实际为准)。

**“load spec” 映射 —— 按 `<pkg>`-相对路径、逐条目替换(非整树 merge-copy)**:
1. 拿 `--agent-src` 做一份 tmp checkout(整包,跳 `__pycache__`/(大/重的非行为数据),(大/重的非行为数据) symlink 回源 → 不每 rollout 拷 重数据)。
2. 对每个 `--editable ent`:源 = `<spec-dir>/<ent>`、目标 = `<checkout>/<pkg>/<ent>`(**同一条相对路径**):
   - **dir → `rm 目标`(基线)后再 `copytree(源, 目标)`** —— 候选在该 dir 内的删除/改名能传过去;**不能**用 `copytree(dirs_exist_ok=True)`(merge 会让删除文件残留)。
   - **file → `rm 目标` 后 `copyfile(源, 目标)`**。
   - 候选没有 `<ent>`(候选删了)→ 只 `rm`。不在 `--editable` 里的路径 → checkout 留运行期原样,不动。
3. 从该 checkout import agent 跑(generate 自带 dep 自动安装、data-driven 运行上下文、复用项目 converter)。

- **写 generate/evaluate 之前,先问用户,别自己先一顿调查**(**步骤 0 已指定例子脚本的直接用、不必重问**,只针对性读代码验证;没指定才在这步问):开口第一句就问"有没有可以参照的**系统运行脚本**(怎么跑 agent、怎么出 predictions/trajectories)和**系统评测脚本**(怎么打分、出 reason)?路径/命令/获取方法是什么" —— **先问、拿到用户指认后再针对性读代码验证**,不要自己先把仓库翻个底朝天再开口(顺序反了,浪费且易认错)。参照/复用 ≠ wholesale delegate,两脚本分工不同:
  - **generate.py 必须自己写、自己实现 load-spec**(checkout + `--editable` 逐条替换 + 从 checkout import + 自己的 invoke 循环):项目的现成推理脚本**不支持 `--spec-dir`/`--editable`**,直接委托它 = 候选 spec 根本载不进来,达不到 AntOmniEvo 的目标。对现成运行脚本的正确用法是**读它、复用它的机制**(prompt/运行上下文怎么构造、sandbox-transport 怎么挂、converter/轨迹 builder 直接 import 调),不是 shell 出去。
  - **evaluate.py 委托项目评测脚本**(委托的前提 = 项目评测脚本能复用已有推理产物、不重跑 agent;具体支不支持、flag 叫什么看项目 eval CLI,以实际为准);项目没有 scorer 才从零写。别闷头自己写一份跟项目不一致的。
- **通用参数 + 能力(可复用底子)**:generate.py / evaluate.py 有一套**每个 eddy 业务都该有**的通用参数与能力(按结构定位包/入口、load-spec、dep 自动装、并发+单 case 超时、env-file、写型 agent 的 sandbox-transport、委托项目 eval、`score∈[0,1]` 归一、`reason` 有信息量…),每条都附**为什么** → 详见 `references/generate-evaluate-recipe.md` §通用参数与能力。**给新业务生成 gen/eval 时直接照搬这套,只改业务适配部分(入口名 / 可编辑条目 / 运行上下文字段 / converter / scorer)**。
- `--dry-run`(仅用于开发自测,不是冒烟):不调 agent,种合成 artifact。冒烟请用真模型(不带 `--dry-run`)。
- **generate.py(写预测,不评分)**:产物 `predictions.jsonl` + `run_summary.json`(含 `agent_src`/`spec_loaded`/`spec_dir`/`editable`/`checkout`)+ workspace + 可选 trajectories。eddy `agent.invoke(...)` 包 `RunContext`;包按结构定位、`--agent-module`/`--agent-attr`=确认入口;dep 自动安装(扫最终跑那份)、运行上下文从 case 的 gold 读、复用项目已有 converter(配 shallow 兜底)。单条失败不连累、按输入序、`Semaphore(--concurrency)`。
- ⚠ **写法范式:流式写盘(强制)** —— generate.py 的 `generate_predictions` 必须"完成一条立即 append 写盘并释放大对象、全部跑完再聚合(run_summary 从计数器取)",**禁止** `asyncio.gather` 把全量 case 的 row+完整 trajectory 攒内存后最后 `write_text` 一次写(否则中途"结果一个都没有"+内存爆)。被 evaluate 委托的项目 eval pipeline 里的并发 judge(若你改到)也同范式 + 序列化对齐。骨架/对齐表/验收清单见 `references/generate-evaluate-recipe.md` §「写法范式:流式写盘(强制)」。
- **写 evaluate.py 前先跟用户对齐"怎么打分"**(同步骤 3 的对齐风格;**本技能不预设任何业务打分法/指标名/eval 入口**——每项目不同,别照搬):
  ① **让用户给一个 `期望产物` vs `真实产物` 的对比例子**(gold 长怎样、agent 产什么、什么算"对"),把打分基准从抽象落到具体。
  ② **或去业务仓库找已有 eval/scorer 代码** —— 用户给线索或自己 grep(`eval`/`score`/`grade`/`judge`/`predictions`/`offline`…),把候选列给用户**确认哪个是这项目正确的打分法**,以及它的输入(读哪个文件/哪段结构)、输出(产出的 metric 字段名)、per-case 产物(从中合成 `reason` 的来源)。
  ③ 据确认结果写 evaluate.py —— **项目已有 scorer/pipeline → delegate**(subprocess 或 import 调它,把它的 metric 归一化到 [0,1] 当 `EvalResult.score`,从它的 per-case 产出合 `reason`);**用户给了对比例子 → 按例子实现确定性判定**;**都没 → 通用 recall 兜底 + 把判定逻辑写清给用户确认**。**别自创与项目已有 scorer 不一致的 scoring。**
- **evaluate.py(评分,不重跑 agent;每条 case 出 score + reason)**:读 generate 的产物(用户确认的 format)+ `--cases`(gold),**按确认的打分法**调/读 scorer;`EvalResult.score∈[0,1]` = 把确认的 metric 归一化到 [0,1](给 optimizer 当 metric);per-case 产物 + `reason` 用确定性文案从 scorer 的 per-case 产出(用户确认的字段来源)抽;`--output` 才落盘。具体写什么文件 / per-case 文件键名 **看项目 evaluate.py `--help` + 实读一份真产物文件确认**。
- **AntOmniEvo System 接线(后续)**:每候选 → 跑 `generate --agent-src <module> --spec-dir <candidate_spec_dir> --editable <entry1> --editable <entry2> …`(`entry` = 步骤 3 约定的);`run_summary.checkout` 指向那次 checkout,事后核对。
- **并发注意**(每候选一个 generate.py 进程):① 每候选**独立 `--output-dir`**(不撞产物);② `uv pip install` 写共享 venv 可能竞争 → 做一次性 dep **pre-flight**(装齐)后候选运行传 `--no-install-deps`;③ 每进程留一份 tmp checkout(可加 `atexit` 清理);④ 多版本同并发注意 model key 限流公平(共用一把 key 会把"慢"伪装成"差")。
- ⚠ **按 agent 是否"写产物"选运行路径**(详见 recipe 坑节):只读型 agent(产物=纯检索/推理回答)用 `LOCAL_WORKSPACE=1` 即可;**写型 agent**(产物 = config/source edit / release ticket 等)**不能只设 `LOCAL_WORKSPACE=1`** —— 会 `status=completed` 但 `prediction_present=False`(没产物)。写型走 sandbox-transport(`--local-sandbox-transport --local-source-repo <项目源码仓库 checkout>`,复用项目既有的"挂本地 VFS"机制)。agent 用 MCP 时还要先备好 MCP 身份 token + 账号权限(见 recipe 坑节)。
- ⚠ **轨迹要复用项目既有 schema** —— generate 写的 `trajectories.jsonl` 后面要被 evaluate 委托的 eval pipeline (evaluate 委托的项目 eval pipeline 里 LLM-scorer / per-case 分析) 读;schema 缺字段 → 项目的 LLM scorer / judge 判"轨迹为空"→ 全 0 分。复用项目 项目的 trajectory 序列化函数,或照它的 schema 字段(`tool_calls`/`tool_results`/`message_summary`/`human_input_required`/…) 手动抽装。详见 recipe 坑节。
- → [同步] 把 generate.py/evaluate.py + `--help` + 关键契约 + load 映射 给用户确认;写 `<exp_root>/NOTES.md`(步骤 4:flags/`--editable` 条目/scoring 对齐结果/找到的 eval 代码);告知完成步骤 4、剩 5–6;问「是否继续」,继续后进步骤 5。

---

## 步骤 5:检查业务仓库代码 venv

业务项目这边的环境得先就绪,步骤 4 写的 generate/evaluate 才跑得起来(独立于步骤 1 的 AntOmniEvo venv):

- 业务项目自己的 venv 是否就绪(有 `.venv`、运行依赖装齐——eddy/antmcp 等:`uv pip install -r <业务项目>/requirements.txt --index-strategy unsafe-best-match`,装完别再 `uv sync`)。
- 用业务项目的 venv 验证步骤 3.1 确认的 agent 入口能 import:`<业务项目>/.venv/bin/python -c "from <确认的入口 module> import <attr>"` 不报错;`import <步骤 3.1 确认的包名>` 能定位到该项目的版本(非别处)。
- agent 在 **import 时**就会 `build()` 模型 / 构造 MCP,**必须先有 model key(如 `THETA_API_KEY`)**+ 本地跑开关(`LOCAL_WORKSPACE=1` 跳过 ARCA)等;没有或不确定 → 先跟用户要/确认。
- **先判断 agent 用不用 MCP,再决定要不要 token 那套** —— 有的 agent 不用 MCP,别给不用 MCP 的用户也搞这一套。判断法:grep agent 包里的 MCP 用法(MCP module / antmcp / MCP client 工具;步骤 3 扫 module 时顺手确认)。**确认用 MCP 才需要**:MCP 身份 token(如 `IAM_TOKEN`)+ 账号 MCP 权限;蚂蚁内部拿 IAM token 的标准方法 = 内网授权页(`login-intranet.alipay.com/pub/oauth/AppAuthorize.htm?...`,页面粘贴 `mcpnexus.alipay.com` 认证后拿 token;项目脚本常内置 `--prompt-iam-token` 流程,优先让用户走它)—— 详见 `references/generate-evaluate-recipe.md` 坑节;**token 拿到先解码验签名段 + exp,注意聊天粘贴可能截断**。不用 MCP → 只要 model key,跳过这套。
- (generate.py 的 dep 自动安装能补装扫描到的缺失第三方包,但**基础运行依赖**得先在业务 venv 装齐;AntOmniEvo 的 venv 不重复装这些。)
- → [同步] 把「业务 venv 能 import + key / 开关就绪」告诉用户;写 `<exp_root>/NOTES.md`(步骤 5:venv 路径/deps/key 状态);告知完成步骤 5、只剩步骤 6(最后冒烟 + 最终确认);问「是否继续」,继续后进步骤 6。

---

## 步骤 6:冒烟 + 用户确认

冒烟产物按『通用约定』放 `<smoke dir>`(= `<exp_root>/tests/bootstrap_smoke/`)、保留不清。

**冒烟必须真跑 agent(不带 `--dry-run`)** —— 输出的 predictions / trajectories / workspace artifacts 必须是真实数据,因为:① 用户要确认格式对不对;② 后续写 System/Evaluator 要参考这些真实数据的字段结构。合成的数据没参考价值。所以冒烟前先跟用户确认 model key 就绪 +(agent 用 MCP 的话)MCP 身份 token + 账号权限就绪 —— 没准备好就先停等(详见 recipe 坑节)。

**冒烟只跑少量数据(强制,别浪费时间)**:generate 一律 `--limit 1`(1 条 case;真实 agent 单条可能就要几分钟到十几分钟,**绝不**在冒烟跑全量/大批量);evaluate 只评这 1 条 predictions(把 predictions 里的 case_id 传给项目 eval,别让它扫全量 cases 文件);load-spec 冒烟同样 `--limit 1`。冒烟要验证的是**链路和产物格式**,不是分数覆盖率 —— 全量跑分是步骤 10 正式 optimize 的事。

逐步命令与断言 → `references/generate-evaluate-recipe.md` §冒烟:

1. **generate 真跑 1 case**:按步骤 4"选运行路径"选 —— 只读型 `LOCAL_WORKSPACE=1`,写型加 `--local-sandbox-transport --local-source-repo <项目源码仓库 checkout>`。命令形如 `<model-key>=<key> generate.py --agent-src <步骤3.1 module> --cases <test> --output-dir <smoke dir>/gen --limit 1 [写型再加 --local-sandbox-transport --local-source-repo <repo>]` → 验证 `status`∈{completed,awaiting} + **`predictions.jsonl` 有真实 artifact(`prediction_present=True`)** + `trajectories.jsonl` 有真实消息流。
2. **evaluate 闭环**:对上面的 predictions.jsonl 跑 `evaluate.py --predictions <smoke dir>/gen/predictions.jsonl --cases <test> --output <smoke dir>/eval [按步骤 4 跟用户对齐的 eval 参数]` → 验证 per-case 产物 `score` 合理 + `reason` 非空有诊断价值 + eval 全部中间产物保留。**先跑快的(无 LLM)那档确认产物对不对,要多维分再跑全档**(具体档位/flag 以项目 eval 为准,别套别的项目的 stage 名 / 文件名)。
3. **generate load-spec 真跑(必须带步骤 3 抽好的 `<exp_root>/initial_spec/`,不是另做的临时 spec)** —— 冒烟要验证的就是正式 `optimize()` 会用的那份 spec 能被正确 load,拿别的 spec 等于没验到真东西。临时往 `initial_spec/` 的入口文件加一行无害注释 marker(如 `# SMOKE_MARKER`),跑 `generate.py --spec-dir <exp_root>/initial_spec --editable <entries> --output-dir <smoke dir>/load --limit 1` → 断言 `spec_loaded=true` + checkout 里该文件**含 marker**(证明跑的是 spec 版而非运行期原版)+ `prediction_present=True` + `status`∈{completed,awaiting};**断言通过立刻删掉 marker 并 `diff -r` 验证 `initial_spec/` 恢复与源码逐字节一致**(initial_spec 是优化起点基线,不留冒烟痕迹)。

**自检(跑完了先自己看,别急着给用户)**:① 轨迹:`trajectories.jsonl` 有真实消息流(非空,有 tool_call/tool_result);② 评分:summary 产物 `score∈[0,1]`(0 分 + reason 说"漏改" 是合理的;0 分 + reason 说"轨迹为空" 是 bug —— 轨迹 schema 没对齐 → 修 generate 的 trajectories.jsonl,复用项目既有 `prediction.build_trajectory()` 而不是自己简化);③ reason:per-case 产物文件每条 `reason` 有信息量(指名漏改/错改/多改字段,不能只写 "correct"——应来自 evaluate 委托的 项目的 LLM scorer / judge 文案)。(文件名/键名以你 evaluate.py 实际产出为准,别假设。)

**最终确认门**:把四类产物路径 + 关键数字(`score`/`exact_rate`/`n_cases`/`n_failed`/`spec_loaded`/reason 摘要)告诉用户;把冒烟总结写入 `<exp_root>/NOTES.md`(步骤 6:通过的全部冒烟点 + 产物路径 + score 基线);再次列**全 6 步已完成**,接下来就是 AntOmniEvo 后续接线;**用户确认无误后**才进 AntOmniEvo 后续;没确认前不往下做。

---

## 步骤 7:写 AntOmniEvo System 模块(候选 spec → 预测)

🎯 把 AntOmniEvo 优化循环里的 **System** 组件写出来:给它一个候选 spec,它把 agent 跑起来、产出预测(trajectory + output)给 Evaluator 评。本步主要覆盖"系统 = 调外部 generate.py 子进程"形态(对标 text2sql;eddy generate.py 就是这种)。📖 逐项模式 + 坑 + 验证配方 → `references/system-recipe.md`。

1. **组件放哪**(『通用约定』已统一:pip 装包,组件全放 `<exp_root>/antomnievo/<scenario>/`,不改已装的包):System 写 `<exp_root>/antomnievo/<scenario>/system/<domain>_system.py`,记 NOTES(组件目录)。📖 `references/system-recipe.md` §0。
2. **读 System 契约 + 找最像的 example(别凭记忆写)**:读 `antomnievo/interface/system.py`(System ABC:`_run`/`run_batch` 关系)、`model/{system_result,rollout_result,trajectory,candidate_data}.py`(`SystemResult`/`RolloutResult`/`Trajectory` span 树/`CandidateMeta.spec_dir`)、**最像的 example**(子进程 generate 形态 → `system/text2sql/text2sql_system.py` + `example/text2sql/birdtest_text2sql.py` + `optimizer/text2sql/text2sql_optimizer.py`;in-process 形态 → `system/rag_pipeline/`)、`optimizer/optimizer.py` 的 `Optimizer._run_and_evaluate`(**看清它调 `run_batch` 传不传 kwargs** —— generic 默认 `run_batch(meta, data_list)` 不传 kwargs,所以你得配套写 optimizer 子类,步骤 8)。📖 system-recipe §1。
3. **写 System**(对标 `Text2SQLSystem`):override `run_batch(candidate_meta, data_list, *, output_dir, cases_path, **kwargs)`;构造参数全**绝对路径**(`generate_script`/`python_path`/`agent_src`/`editable`/`local_source_repo`/`env_file`/`timeout`/`concurrency`/`local_sandbox_transport`/`no_install_deps`);拼 generate.py 命令(`--agent-src --spec-dir <candidate_meta.spec_dir> --editable <ent>... --cases <cases_path> --output-dir --local-sandbox-transport --local-source-repo --env-file --no-install-deps --timeout-seconds --concurrency`);`subprocess.run` 经 `loop.run_in_executor`(超时 `timeout*N+300`,rc≠0 记 stderr 不 raise);读回 `predictions.jsonl`+`trajectories.jsonl`,按 `data_inst.id` 建 `SystemResult`(`output.content`=产物摘要 JSON、`trajectory`=span 树 + tool_call 子 span);`_run` raise NotImplementedError;`system_description()` 准确反映 generate.py 机制(见『通用约定』)。📖 system-recipe §2。
4. **坑(实测得的)**:① generic `Optimizer` 不传 kwargs → 配套写 optimizer 子类(步骤 8)给 `run_batch` 传 `output_dir`+`cases_path`;System 的 `run_batch` 签名收这两个 kwarg;② `cases_path` 用 `to_case_dict()` 写**全 case 行(带 gold)**,别只写 id/query;③ `candidate_meta.spec_dir` = `--spec-dir`,配 `--editable` 做 load spec;④ 写型 agent 要 `--local-sandbox-transport`(只读 LocalWorkspace 产不了产物,见步骤 4 坑);⑤ **artifact 形态先实读 predictions.jsonl 确认**(别假设 `payload.field_name`;本场景形如 `{all_change_summary, changes[0]{config_name/app/env/base_config_version/target_type/target_config/summary}}`,换领域以实际为准);⑥ `Trajectory` 用 span 树别留空(tool_call 做子 span、其余放 root metadata);⑦ 路径全绝对(见『通用约定』);⑧ 运行前置(model key + MCP 权限 + sandbox 仓库,步骤 4/5 坑)要备齐,否则 `run_batch` 跑完 `prediction_present=False`(空跑)。📖 system-recipe §3。
5. **验证(必做,别跳)**:① `import` + `issubclass(X, System)`;② **离线** `_build_system_result` 喂真 predictions/trajectories(验产物提取对、pydantic 过、span 树 + tool_call 配对对 —— 直接验真实 artifact 形态,省一次 agent 跑);③ **端到端** `run_batch` 1 case 真模型冒烟(造 `CandidateMeta(spec_dir=baseline 包根)` + batch cases(1 条 `to_case_dict`)+ output_dir(本步 `<smoke dir>`,如 `system_smoke`),`await system.run_batch(...)`;断言:返回 `SystemResult` 数==batch 数、`prediction_present=True` + 产物对齐 gold(`config_name`/`base_version`/`app`/`env`/`target_type`)、trajectory 有 tool_call 子 span + `run_status`∈{completed,awaiting} + `errors` 空);修 bug 后**离线复验** `_build_system_result`(不必重跑 agent)。跑不过先分清:运行前置没备齐(MCP 403/无 VFS → `prediction_present=False`)还是提取/构造 bug(对照真 predictions.jsonl 修)。📖 system-recipe §4。
6. → [同步] 把 System 模块路径 + `run_batch` 契约(`output_dir`/`cases_path` kwargs)+ 构造参数 + 冒烟证据(产物对齐 gold 的 case_id + 字段)告诉用户;写 `<exp_root>/NOTES.md`(步骤 7:组件目录/System 路径/构造参数/editable/run_batch kwargs/冒烟通过点);告知完成步骤 7、剩步骤 8(Evaluator)起;问「是否继续」,继续后进步骤 8。

---

## 步骤 8:写 AntOmniEvo Evaluator 模块(预测 → 评分)

🎯 把 AntOmniEvo 的 **Evaluator** 组件写出来:接 System 的 predictions,打分(`score∈[0,1]` + reason)给优化循环选优 / 淘汰。本步对标"评分 = 调外部 evaluate.py 子进程"形态(本项目 evaluate.py 就是这种)。📖 逐项模式 + 坑 + 验证配方 → `references/evaluator-recipe.md`。

1. **放哪**(同步骤 7 的组件目录):`<exp_root>/antomnievo/<scenario>/evaluator/<domain>_evaluator.py`(跟 System 同一场景包)。📖 evaluator-recipe §0。
2. **读 Evaluator 契约 + 找最像的 example(别凭记忆写)**:读 `antomnievo/interface/evaluator.py`(`Evaluator` ABC:`_evaluate`/`evaluate_batch`/`scoring_criteria`)、`model/evaluation_result.py`(`EvaluationResult{data_id, metric_name, score∈[0,1], reason}`)、**最像的 example**(子进程 evaluate 形态 → `evaluator/text2sql/text2sql_evaluator.py`)、**项目的 `scripts/evaluate.py` CLI + 输出**(看 `--help` 收什么 flag、跑什么 stage、写什么 output file;⚠ **实读一份真 per-case 产物文件**确认 score/reason/id 键名,别假设,每项目不同)、`optimizer/optimizer.py` 的 `Optimizer._run_and_evaluate`(看清它调 `evaluate_batch` 传不传 kwargs —— generic 默认不传,你要配套写 optimizer 子类步骤 9 传 `output_dir`/`predictions_path`/`cases_path`)。📖 evaluator-recipe §1。
3. **写 Evaluator**(对标 `Text2SQLEvaluator`):override `evaluate_batch(data_list, system_results, *, output_dir, predictions_path, cases_path, **kwargs)`(签名跟步骤 9 optimizer 子类对齐);构造参数全**绝对路径**(`evaluate_script`/`python_path`/`timeout`/`extra_args`;项目需要的话加 `schema_manifest`/`eval_stage`/`accuracy_threshold` 等项目特定 flag);拼 evaluate.py 命令(看你项目 evaluate.py `--help` 接受什么 flag → 传 `--predictions`/`--cases`/`--output` + 项目需要的其它);`subprocess.run` 经 `loop.run_in_executor`(rc≠0 记 stderr 不 raise);读回 evaluate.py 的 per-case 产物(`--help` 说它写什么 → 实读一份真产物文件确认键名),按 `data_inst.id` 匹配 → `EvaluationResult(data_id, metric_name, score∈[0,1], reason)`(缺该 case → score=0/"no detail");**score 归一化到 [0,1]**;`system_results` 不消费(同 text2sql)。`_evaluate` raise NotImplementedError;`scoring_criteria()` 准确反映 evaluate.py 打分机制(见『通用约定』)。📖 evaluator-recipe §2。
4. **坑(实测得的)**:① generic `Optimizer` 不传 kwargs → 配套写 optimizer 子类(步骤 9)给 `evaluate_batch` 传 `output_dir`+`predictions_path`+`cases_path`;② `predictions_path` = System 的 `<gen_dir>/predictions.jsonl`,`cases_path` = batch cases(全行带 gold);③ **per-case 产物的 score/reason/id 键以实读为准**(每项目不同;别假设);④ score 必须**归一化到 [0,1]**;reason 要有信息量;⑤ **项目特定的 flag**(如 `--schema-manifest` / `--eval-stage` / `--source-repo` 等)看你项目 evaluate.py 需要 → 不预设;
⑥ `eval_stage`:fast 档适合优化循环(快);detailed/full 档慢(LLM judge 等),用不用要跟用户讨论 trade-off;
⑦ `scoring_criteria()` 要机制准确(见『通用约定』);⑧ `_evaluate` raise NotImplementedError(别 pass)。📖 evaluator-recipe §3。
5. **验证(必做,别跳)**:① `import` + `issubclass(X, Evaluator)` + `scoring_criteria()` 非空;② **离线**用一份真 per-case 产物文件(之前 evaluate 跑留的产出)喂解析逻辑 → 验 `EvaluationResult` 字段对(score/reason/id 键对、score∈[0,1]);③ **端到端** `evaluate_batch` 1 case 冒烟:复用步骤 7 System 冒烟的真产物(`<smoke dir>` 的 `gen/predictions.jsonl` + batch cases),`output_dir` 放 `<smoke dir>/eval`(没 exp_root → `/tmp`),`await evaluator.evaluate_batch(...)`;断言:返回 `EvaluationResult` 数==batch 数、`data_id` 对、`score∈[0,1]`、`reason` 非空、(已知正确的 case)`score` 应高;④ evaluate.py 落盘的产物文件落盘可看。修 bug 后离线复验(不必重跑 evaluate.py)。📖 evaluator-recipe §4。
6. → [同步] 把 Evaluator 路径 + `evaluate_batch` 契约(kwarg)+ 构造参数(项目特定 flag 看你 evaluate.py `--help`)+ 冒烟证据(`score` + reason)告诉用户;写 `<exp_root>/NOTES.md`(步骤 8:evaluator 路径/构造参数/evaluate_batch kwargs/per-case 产物键名/scoring_criteria 要点/冒烟通过点);告知完成步骤 8、剩步骤 9(Proposer/optimizer/入口 + `optimize()`);问「是否继续」,继续后进步骤 9。

---

## 步骤 9:写 Optimizer 子类(串 System+Evaluator 的 run+eval)

🎯 在 System+Evaluator 之上写 **Optimizer 子类**,override `_run_and_evaluate`(把 System.run_batch + Evaluator.evaluate_batch 经 kwargs 串起来、每候选一个 tempdir 跑+评)。(入口脚本 + spec_def + config 是步骤 10。)📖 `references/optimizer-recipe.md`。

1. **放哪**:同组件目录 —— optimizer 子类写 `<exp_root>/antomnievo/<scenario>/optimizer/<domain>_optimizer.py`,入口脚本 `<exp_root>/antomnievo/<scenario>/<domain>_optimize.py`。
2. **用默认还是扩展?(关键决策 —— 看你步骤 4 写的 generate.py/evaluate.py 的输入输出)**:
   - **子进程 + 文件路径 I/O**(generate 取 `--cases/--output-dir/--spec-dir`、evaluate 取 `--predictions/--cases/--output`)→ 默认 `Optimizer._run_and_evaluate`(调 `run_batch(meta, data_list)`+`evaluate_batch(data_list, results)` **不传 kwargs**)给不出这些路径 → **必须 subclass + override `_run_and_evaluate`**(造 tempdir → 写 batch cases → thread `output_dir`/`cases_path`/`predictions_path`,对标 `Text2SQLOptimizer`)。
   - **in-process**(System/Evaluator 拿 data_inst 直接出结果、无文件 I/O)→ 默认 `Optimizer` 就够,**别 subclass**。
   本项目 generate/evaluate 都是子进程 → 要 subclass。**这个决策是看 generate/evaluate 实际 I/O 得出的,不是猜**。📖 optimizer-recipe §0。
3. **读 optimizer 契约 + 范本**:`antomnievo/optimizer/optimizer.py`(`Optimizer._run_and_evaluate` 默认不传 kwargs;`optimize()` 主循环;`__init__` 要 system/proposer/evaluator/evolution_algorithm/candidate_store/train/val/batch_size/budget/num_proposals/initial_spec_dir...)、最像的 example `antomnievo/optimizer/text2sql/text2sql_optimizer.py`(subclass 范本)、`ParetoFrontierEvolutionAlgorithm`/`Budget`/`LocalCandidateStore` + **agent proposer**(抽象名;已装包 `antomnievo/proposer/` 里 `BaseProposer` 的具体实现,**以包内实际为准、不写死实现名**;构造参数 `spec_schema`/`candidate_store`/`evaluator`/`system`/`api_key`/... 以所选实现的签名为准)。📖 optimizer-recipe §1。
4. **写 optimizer 子类**(对标 `Text2SQLOptimizer`):`<Domain>Optimizer(Optimizer)` override `_run_and_evaluate(candidate_id, data_list) -> RolloutEvalResult`:tempdir → `gen_dir`+`eval_dir` → 写 `cases_batch.jsonl`(全 case 行带 gold,`data_inst.to_case_dict()` 按 id 排序)→ `system.run_batch(meta, data_list, output_dir=gen_dir, cases_path=batch_path)` → `evaluator.evaluate_batch(data_list, results, output_dir=eval_dir, predictions_path=gen_dir/predictions.jsonl, cases_path=batch_path)` → `RolloutEvalResult`。**kwarg 名跟步骤 7/8 的 System/Evaluator 签名对齐**。(spec_def + 入口 + config 在步骤 10。)📖 optimizer-recipe §2。
5. **坑(实测得的)**:① 默认 Optimizer 不传 kwargs → 子进程形态必须 subclass(决策见 §2);② batch cases **全行带 gold**(`to_case_dict`);③ kwargs 签名跟步骤 7/8 System/Evaluator 对齐(对不上 TypeError);④ per-candidate per-batch 独立 tempdir;⑤ `_run_and_evaluate` 自己 **不 persist run-record**(wrapper/`_evolve_one` 才 persist)—— 裸调它做 wiring 冒烟看不到 `run_*.json` 正常;⑥ **agent proposer 需其对应的 coding-agent CLI + api_key**(要哪个 CLI 看所选实现的实现名/文档/报错);全量 `optimize()` 还要 model key + MCP 权限 + sandbox 仓库 + schema manifest —— 都是重开销(每候选真跑 agent + LLM 改 spec),**别误跑**;⑦ train/val 无划分 → 入口里切;⑧ 路径全绝对(通用约定)、测试时 `<run_dir>` 没定 → candidate store 用 `/tmp`(通用约定);⑨ `system_description`(步骤 7)/`scoring_criteria`(步骤 8)已写好,proposer 用,错或空→错误归因(通用约定)。📖 optimizer-recipe §3。
6. **验证(wiring 冒烟,不跑 proposer)**:**先** `python scripts/extract_initial_spec.py --agent-src src/<pkg> --editable <步骤3 可编辑条目> --output <exp_root>/initial_spec`(**步骤 3 已抽出 `<exp_root>/initial_spec/` 则直接复用,别重复抽**;抽出可编辑 spec——**spec ≠ agent module**,详见步骤 10);构造 optimizer(proposer 占位 api_key、不调它)+ `candidate_store.create_root(initial_spec_dir=<抽出的 spec dir>)` → `await optimizer._run_and_evaluate(root_id, [1 case])` → `RolloutEvalResult`;断言:`results[0]` `prediction_present=True`(+ artifact 字段)、`evals[0]` `EvaluationResult(score∈[0,1], reason)`、已知正确 case `score≥0.9`。验证 System↔Evaluator 经 optimizer kwargs 串通 + 候选 spec 能 load(≈1 agent run)。没 exp_root → candidate store 目录 + 输出放 `/tmp`(通用约定)。全量 `optimize()` 验证在步骤 10。📖 optimizer-recipe §4。
7. → [同步] 把 optimizer 路径 + (用默认还是扩展的决策依据)+ wiring 冒烟证据(`RolloutEvalResult` 的 score/reason)告诉用户;写 `<exp_root>/NOTES.md`(步骤 9:用默认还是扩展/optimizer 路径/wiring 通过点);告知完成步骤 9,剩步骤 10(入口脚本 + config + `optimize()`);问「是否继续」,继续后进步骤 10。

---

## 步骤 10:写 example 启动入口脚本 + 配置(`await optimizer.optimize()`)

🎯 把 System+Evaluator+Optimizer 接到 **入口脚本**:装 Proposer + EA + CandidateStore + 优化循环,跑 `await optimizer.optimize()`。**配置(secrets + 路径 + 超参)放一个 config YAML 文件(放 `<exp_root>`),入口加载,不要写死在代码**。📖 `references/entry-recipe.md`。

1. **放哪**:入口 `<exp_root>/antomnievo/<scenario>/<domain>_optimize.py`(同组件目录里的场景包)。
   ⚠ **YAML 的 `workspace_dir` = candidate store 的单次 run 目录 `<run_dir>`**(见『两个目录概念』):`<candidate_store_root>/run_YYYYMMDD_HHMMSS/` —— **不是 exp_root、也不是 candidate store 根目录**。AntOmniEvo 的 `LocalCandidateStore` 会检查 `statistics.root_candidate_id`:有 → 续跑(resume,跳 root baseline);没 → 从头建。**续跑用同一 `<run_dir>`;新 run 换一个新 timestamped 子目录。不需要 flag**(AntOmniEvo 内置行为,README §8)。per-batch gen+eval 产物放 **tempfile**(batch 结束自动清,不 pollute `<run_dir>`)。📖 entry-recipe §2。
2. **先检查/装 pi CLI**(agent proposer 固定用 pi 实现):`which pi` 查 → **没装就帮用户装** `npm install -g @mariozechner/pi-coding-agent`(需 **Node ≥ v22.22.1**);装好 `pi --version` 确认。
3. **主动问用户要配置(别硬编码 secrets)—— 必须问全下面这张清单,一项没问清就不写入口、不跑 optimize**(用 AskUserQuestion 批量问 + 允许 Other 自输;secrets 让用户贴或给文件路径,绝不写死进代码):
   **必问清单(打勾才继续)**:
   - [ ] **proposer = pi agent 实现,固定默认,不让用户选**(用包里 pi-based 的 `BaseProposer` 实现;⚠ 不提供 claude 实现选项 —— claude 目前有问题;文本里仍用抽象名 "agent proposer",但选型不开放)。要确认的只是:`pi` CLI 装了没(`which pi`,没装帮装)。
   - [ ] **proposer `model`(必填,别猜)** + **`base_url`(换了网关必须问,模型名和网关要配套)** + **`api_key`**(贴或给文件路径)
   - [ ] **system 运行期 secrets**(本项目 `THETA_API_KEY` + `IAM_TOKEN`:复用现有 .env.local 还是换新的;注意 token 有效期 vs 跑的长度)
   - [ ] **train 条数 + val 条数**(val 空=0 也要确认)+ 数据路径
   - [ ] **优化循环打分档**(快档还是全档 —— 全档慢/要 key,跟用户对齐 trade-off)
   - [ ] **超参不用问,先用默认**(batch_size/num_proposals 用 Optimizer 默认);**预算**:跟用户讲清支持的预算类型(`max_iterations` 迭代数 / `max_rollouts` 训练 case 累计 / `max_system_runs` 全 split case 累计 / `max_tokens` / `max_elapsed_seconds` 墙钟),**默认设时间预算 8 小时**(`max_elapsed_seconds: 28800`),并明确告诉用户**调参位置 = config YAML 的 `hyperparams` 段**(要改预算/并发/批量就改那里,不改代码)
   - [ ] **`workspace_dir`(`<run_dir>`)**(默认 `<candidate_store_root>/run_<ts>` 新建;续跑用已有 run 目录)
   细节:
   - **proposer**:`api_key` + `base_url` + **`model`(必填,无默认,别猜)**(+ CLI 路径/`provider` 等可问默认)。
   - **system**(agent/mcp 跑要的):模型 key(本项目 `THETA_API_KEY`)+ MCP 身份 token(本项目 `IAM_TOKEN`)—— 看项目主进程读的 env 名。
   - 路径(repo/源码仓库/cases/schema_manifest/workspace_dir)+ `initial_spec_dir`/`editable`。
   - **数据集对齐(train/val 哪来)**:train cases 怎么拿?本地路径 / 云端下载?**格式跟步骤 2 data 层对齐**(读 2~5 行 sample 确认);val cases 怎么拿?(可能 = 留空 / 单独 val 文件 / 同一切分 / 云端)—— **跟用户对齐**到底用什么、空不空、**train 多少条**、**val 多少条**(记录)。YAML `cases`(gold 文件路径) + `hyperparams.train_max`(**用户对准的真实数量**)+ `hyperparams.val_max`(**默认 0 = 无 val**;真有 val 才填 > 0)。⚠ 代码里不能给 `val_max` 非 0 默认(我之前默认 2,跟"val = 空"矛盾,已改)。
   - ⚠ **`hyperparams` 里放的是真跑数量;冒烟用了 `smoke: true` 开关 override 到小量**,不是改 hyperparams —— 冒烟完改一行 `smoke: false` 就真跑,不用改数据:
     - `smoke: true` → 代码 override `train_max=2, val_max=0, max_iterations=1, num_proposals=1, batch_size=1`(快速冒烟)。
     - `smoke: false` → 用你跟用户对齐的 `hyperparams` 里的真跑数量(如 train=98/val=0/iter=20),**恢复到对齐的量**,不是手动改。
     - **这不只是个开关——是数据对齐的保障**:你跟用户对齐"train N 条、val M 条" → 写进 hyperparams → 冒烟时 smoke=true override 到小量跑通 → 切 smoke=false 就真 N 条,不会再改数字。如果冒烟数据量也写进 hyperparams 改,冒烟完恢复时容易忘改/改错(我之前就写成了 smoke 数据忘了恢复)。
   - 超参不问用户,先用默认(batch_size/num_proposals 用 Optimizer 默认);预算默认时间预算 8 小时,调参位置 = config YAML 的 `hyperparams` 段(见上面必问清单对应项);小 budget smoke 先跑通再切 `smoke: false`。
   - 收齐后**自查缺不缺**(入口 `--check-config` 列缺失);少就让用户补,最终加载进 YAML。
3. **写 spec_def + 抽 initial_spec**:
   - spec_def(`<exp_root>/antomnievo/<scenario>/spec_defs/<domain>_spec_def.py`):`FolderSchema(name=<步骤 3 可编辑根>, ...)` + 候选树 + 约束段(无冗余/矛盾、跨实例泛化、改后仍 importable、保工具流+HITL、别耦合单 case/别动非可编辑文件)。proposer 用它 mut spec。(也可在步骤 3 一起写。)
   - **抽 initial_spec**:步骤 3 已把可编辑条目抽到 `<exp_root>/initial_spec/`(目录名固定 `initial_spec`)→ 直接复用;若没抽过才跑 `scripts/extract_initial_spec.py --agent-src src/<pkg> --editable <步骤3 可编辑条目> --output <exp_root>/initial_spec` → 只抽可编辑 → `initial_spec_dir` 指 OUTPUT(不是 agent_src);**spec ≠ agent module** —— LocalCandidateStore 整树拷每候,agent module 含 config/knowledge_data/平台 bootstrap → 不能用 `src/<pkg>`。
4. **写入口脚本**(`<exp_root>/antomnievo/<scenario>/<domain>_optimize.py`):**initial_spec 复用步骤 3 抽好的 `<exp_root>/initial_spec/`(目录名固定 `initial_spec`);没抽过才跑 `<exp_root>/antomnievo/<scenario>/scripts/extract_initial_spec.py --agent-src src/<pkg> --editable <步骤3 可编辑条目> --output <exp_root>/initial_spec`**(只抽出可编辑部分 —— spec **不等于** agent module;LocalCandidateStore 整树拷,agent module 含 config/knowledge_data/平台 bootstrap → 重数据爆炸 + proposer 能碰非可编辑 → 不能用 `src/<pkg>`;extract 脚本也放组件目录)。`--config <exp_root>/config.yaml`(或 env `ADCONFIG_CONFIG`)加载配置;**所有 secrets 从 YAML 读,绝不写死**;`initial_spec_dir=<extracted spec dir>(不是 agent_src)`;构造 System(系统 secrets 由入口物化到 `<run_dir>/run.env` 给 generate.py `--env-file`,单源=YAML;credential 跟 run 走)+ Evaluator + AgentProposer(抽象名,具体实现以已装包 `antomnievo/proposer/` 为准;`spec_schema=<spec_def>, candidate_store, evaluator, system, api_key=<YAML>, base_url=<YAML>, ...`) + `ParetoFrontierEvolutionAlgorithm` + `LocalCandidateStore(<run_dir>)` + `<Domain>Optimizer(..., initial_spec_dir=<extracted spec dir>)` + `await optimizer.optimize()`。train/val(无划分 → 顺序子集切先冒烟;正式分层按用户对齐的维度)。对标 `antomnievo/example/text2sql/birdtest_text2sql.py`。给个 `--check-config`(验 YAML 必填、不跑)。📖 entry-recipe §2。
5. **坑**:① **别把 secrets 写进代码**(写死=难改+泄)—— 放 config YAML(在 `<exp_root>`)、入口加载;② 配置**主动问用户**、收齐 `--check-config` 查缺;③ `run.env` 由入口从 YAML system 部分物化(generate.py 读),单源(YAML);④ **proposer 需 `pi` coding-agent CLI**(装好)+ proposer key;全量 `optimize()` 还要 model key + MCP 权限 + sandbox 仓库 + schema manifest + 大开销(每候选真跑 agent + LLM 改 spec),**别误跑**;⑤ train/val 无划分 → 入口切;⑥ 路径全绝对 / 测试时 `<run_dir>` 没定 → `/tmp`(通用约定)。📖 entry-recipe §3。
6. **验证**:① `--check-config` 列必填 secrets 缺不缺(没少才跑);② **小 budget `optimize()`**(可能/重):`max_iterations=1`、`train≈2`、`val≈0` 跑一次,看 root baseline → propose → child → 比较 循环通(proposer CLI + key + 全前置就绪后);③ 再放大;**val=0 时 `summary.json` avg_score 始终 0 不能看 —— 看 optimize 日志里每 iteration 的 batch 提升值(`old → new → improvement >= threshold`)判断采纳与否**;④ 轨迹/统计看 `<exp_root>/NOTES.md`。📖 entry-recipe §4。
7. → [同步] 把 entry 路径 + YAML config 路径 + (问了用户哪些 + 缺不缺)告诉用户;写 `<exp_root>/NOTES.md`(步骤 10:entry 路径/config 路径/spec_def/proposer CLI 依赖/train-val 切法);权限/key 确认就绪;问「是否跑小 budget `optimize()`」。

---

## 优化运行后:怎么看结果 + 用结果(主动引导,别让用户自己摸索)

优化跑完(或跑到一半想看效果)后,你(执行者) **主动**帮用户看这几样,**不用用户自己翻文件**:

### 1. 进展概况(statistics.json)
```
<run_dir>/logs/statistics.json
```
读 + 给用户:
- `baseline_avg_score`(root 基线) vs `best_avg_score`(当前最优) → 提升了多少。
- `avg_score_history`(每 slot 的最优值序列,单调不降 = 每次 iteration 至少保持平或更好)。
- `total_candidates_created` / `rejected_count` → 通过/淘汰比。

但 ⚠ **val=0 时 `baseline_avg_score` 和 `best_avg_score` 始终 0** → 不能看这几个数。改看:
### 2. 每 iteration 的 batch improvement(优化器日志)
从 `<run_dir>/optim_*.log` 或 `<run_dir>/logs/` 里 grep:
```
Parent <id> scores: [case_id=0.6, ...], Child <id> scores: [case_id=0.8, ...]
New candidate <id> ... (new=2.4, old=1.8, threshold=0.5), accepting
```
- `old` = parent batch 分数和 → `new` = child batch 分数和 → `improvement = new - old`。
- `improvement >= threshold` → 采纳(child 成为新 pending);否则 reject → EA 下轮选另一个再试。
- **每轮的 `old → new → improvement` 是 val=0 时的优化信号**(avg_score=0 不能看)。

### 3. 改了什么(changelog)
```
<run_dir>/candidates/<best_id>/data/changelog.jsonl
```
每行是一条变异:`type`(feat/fix/refactor...)+ `subject` + `body`(为什么改)+ `diff`(文件级 diff)+ `files_modified`。读 + 总结给用户:"第 N 轮在 `<file>` 改了 `<what>` 因为 `<body>`"。

### 4. 最优 candidate 的 spec → 怎么应用回项目
AntOmniEvo 跑完后,最优 spec = `<run_dir>/candidates/<best_id>/spec/<editable entries>/`(candidate 的 spec_dir)。
你(执行者)主动做:
1. `diff <exp_root>/initial_spec <run_dir>/candidates/<best_id>/spec/` → 看改了哪些文件。
2. 把改动总结给用户(逐文件 changed-lines + why)。
3. 问用户是否把改动应用回业务的 agent 代码(`cp` / `git apply` / 用户手动 review)。
4. 应用后让用户跑一次真冒烟(步骤 6 流程)验证改过的 agent 行为不变。

### 5. 可选:可视化器(AntOmniEvo built-in)
AntOmniEvo 自带 React + Flask visualizer → 源码仓库的 `visualizer/`(pip 包 `ant-omnievo-visualizer`;README §9)。启动命令以 AntOmniEvo README §9 为准。浏览器打开后看:Pareto frontier 候选 + changelog 时间线 + per-case score 热力 + lineage 树。

→ [同步] 把:① statistics.json 的 baseline vs best(或 "val=0 看 batch improvement")告诉用户;② 改了哪些文件 + 为什么;③ 最优 candidate spec 路径;④ 问是否应用回业务代码。

---

## 预算管理(Budget:给用户一个安全网)

`Budget(max_iterations=N)` 是上限,但 **max_iterations=N 一个就可能跑很久(agent + proposer + evaluator LLM judge 全开)**。告诉用户加两个 safety:
- `max_tokens=N`(累计 input+output token 硬上限,达了就停开新 slot)—— 防止天价 LLM 账单。
- `max_elapsed_seconds=3600`(1 小时测试等)—— 防止脚本跑飞无人看时无限跑。
把这两个写进 YAML:
```yaml
budget:
  max_iterations: 1000            # 用户设;迭代上限
  max_tokens: 5000000             # AI(opt) 安全上限;AntOmniEvo 把所有能耗都入预算
  max_elapsed_seconds: 86400      # 一天;跑飞时自动停
```
AntOmniEvo 按所有规模 axis 用 OR 条件:任一个超出 → 新 slot 不开。`None` = 那个 axis 不限。告诉用户的最少三选之一: `max_tokens` / `max_elapsed_seconds` / `max_iterations` 你不上最小都行,不要不上!

---

## 沟通风格

- 主动提问优先:exp_root / candidate store 目录 / 数据 / agent module / 业务代码位置与格式,别默认假设;模糊就停下问。
- 给结论附证据:每个步骤跑完先自验,再把"路径 + 关键内容/数字 + 怎么看"给用户。
- 失败要诚实:冒烟不过就说哪步不过、贴输出,不粉饰成通过。
- 不喧宾夺主:确认门前只做本技能的范围;后续 AntOmniEvo 接线等用户发话。

## 参考文档(本技能用到)
- `references/workspace-setup-recipe.md` —— 步骤 1(对齐实验根目录 + candidate store 目录 + venv + 装 AntOmniEvo + 读 README/选 example)用:具体命令 + 目录布局 + sanity(entry-point 骨架不在此,直接读 AntOmniEvo 的 example)。
- `references/data-layer-recipe.md` —— 步骤 2(写 `<domain>_data_inst` / `<domain>_dataset_loader`)用:可对号模板 + 字段抽取要领 + 坑 + sanity check。
- `references/spec-recipe.md` —— 步骤 3(对齐 agent module + 写 AntOmniEvo spec)用:`SpecSchema` 形态 + 结构参照 + 编辑集/initial_spec_dir 落法 + `--editable` 映射 + 约束段模板 + sanity。
- `references/generate-evaluate-recipe.md` —— 步骤 4/6(写 generate/evaluate + load-spec + 冒烟)用:逐项模式 + load 映射 + 并发注意 + 冒烟配方 + 文件形状表。
- `references/system-recipe.md` —— 步骤 7(写 AntOmniEvo **System 模块**)用:组件放哪(pip 装包 → `<exp_root>/antomnievo/<scenario>/`)+ 读什么(System 基类/models/最像的 example/optimizer 调 run_batch 的地方)+ 怎么写(子进程 generate.py 形态,对标 Text2SQLSystem + **eddy→Trajectory 用共享 parser `parse_eddy_trajectory`(代码 `antomnievo/common/utils/trajectory_parser.py`,3 个 size 参数可调)**)+ 坑(generic Optimizer 不传 kwargs→配套 optimizer 子类、cases_path 带全 gold、`candidate_meta.spec_dir`=`--spec-dir`、写型要 sandbox-transport、artifact 形态以实读为准别假设、Trajectory 用 span 树别留空 **+控制 trajectory 文件大小:不冗余 metadata + 截断大 tool output(常量 `TOOL_OUTPUT_MAX_CHARS` 可调)**)+ 验证(import 子类校验 / 离线 `_build_system_result` 对真产物 / 端到端 `run_batch` 1-case 冒烟断言产物对齐 gold + trajectory 有 tool_call span)+ ad-config 实例参考。
- `references/evaluator-recipe.md` —— 步骤 8(写 AntOmniEvo **Evaluator 模块**)用:先定放哪(沿用步骤 7)+ 读什么(Evaluator 基类/Text2SQLEvaluator/项目 evaluate.py CLI + 实读真 per-case 产物键)+ 怎么写(evaluate_batch override,子进程 evaluate.py → per-case 产物 → `EvaluationResult` [0,1]+reason)+ 坑(generic Optimizer 不传 kwargs→配套 optimizer 子类、predictions/cases 带 gold、per-case 键实读为准、score 归一 [0,1]、项目特定 flag 看 `--help`、eval_stage 跟用户对齐、scoring_criteria 机制准确)+ 验证(import/离线/端到端 evaluate_batch 冒烟,没 exp_root → /tmp)+ ad-config 实例代码位置。
- `references/optimizer-recipe.md` —— 步骤 9(写 AntOmniEvo **Optimizer 子类**,_串 System+Evaluator 的 run+eval_)用:**先定用默认还是扩展**(看你步骤 4 写的 generate.py/evaluate.py 的 I/O:子进程+文件路径→必须 subclass override `_run_and_evaluate` 串 `output_dir`/`cases_path`/`predictions_path`,in-process→默认够)+ 读什么(Optimizer/`Text2SQLOptimizer` 范本)+ 怎么写(subclass `_run_and_evaluate`)+ 坑(默认不传 kwargs→子进程必须扩展、cases 全 gold、kwarg 对齐、tempdir 隔离、`_run_and_evaluate` 不 persist)+ 验证(wiring 冒烟 `_run_and_evaluate` 1 case → RolloutEvalResult,不跑 proposer)+ ad-config 实例参考。
- `references/entry-recipe.md` —— 步骤 10(写 **example 启动入口脚本** + 配置,跑 `await optimizer.optimize()`)用:**主动问用户要配置(secrets/config),收齐 `--check-config` 查缺**+ 放一个 **config YAML(放 `<exp_root>`)**(secrets 在这、入口加载、绝不硬编码;`run.env` 从 YAML system 部分物化)+ 读什么(入口范本 birdtest/Proposer/EA/CandidateStore/spec_def)+ 怎么写(入口脚本 + YAML 配置 schema + 物化 run.env + 串 optimize) + 坑(secrets 别写码、问用户单源、proposer 需 pi CLI、全量 optimize 重别误跑、train/val 无划分)+ 验证(`--check-config`、小 budget `optimize()`)+ ad-config 实例参考。
