# AntOmniEvo 可调产物配法(可调产物 = module 的可调文件集)

被 SKILL.md「步骤 3」引用。可调产物 = 跟用户约定好的**可调文件集**(按 `<pkg>`-相对路径摆放),作为 AntOmniEvo 的优化面 —— 不是整包,也不外置。参照结构:已装包里 `antomnievo/model/tunable_artifact_schema.py` 的 `TunableArtifactSchema`,以及在已装包的 `antomnievo/model/tunable_artifact_defs/` 选一份**系统形态最像的** `<x>_tunable_artifact_def`(只照结构,别照它的范围/字段)。

## 0. 为什么不能拿整个 module 当可调产物(AntOmniEvo 机制)

- `LocalCandidateStore.create_root/create_child` 整树 `shutil.copytree(initial_artifacts_dir, candidate_artifact_dir, ignore=ignore_patterns("__pycache__"))` —— `initial_artifacts_dir` 里有什么就全量拷进每个 candidate × 每代 × 每次 rollout;只忽略 `__pycache__`。
- `TunableArtifactSchema` 只软提示:只 `render_tunable_artifact_schema` 渲染进 proposer/分析 prompt(`base_proposer.py:442/459/584`),**无任何校验**;proposer 在 `cwd=artifact_dir` 改任意文件,唯一程序化后检查是 `mtime`,**无路径白名单**(`base_proposer.py:412`)。
- 结论:`initial_artifacts_dir = 整个 src/<pkg>` ⇒ env/bootstrap/(大/重的非行为数据) 全进每个 candidate、全机器可改 + 爆炸。"少动"描述不是硬隔离。
- **正确:`initial_artifacts_dir` = agent module 的包根、只保留可调文件**(自定义 `CandidateStore` 的 `ignore_patterns` 丢非可调 → 候选只剩可调文件按 `<pkg>`-相对排好;或精心 curated);non-tunable 物理上不进 candidate。可调产物是 module 的一部分(非整包、非外置)。

## 1. TunableArtifactSchema 形态(`antomnievo/model/tunable_artifact_schema.py`)

```python
class FileSchema(BaseModel):   name: str; description: str          # type="file"
class FolderSchema(BaseModel): name: str; description: str; files: list[FileSchema|FolderSchema] = []   # type="folder"
TunableArtifactSchema = FileSchema | FolderSchema      # tunable_artifact_def 产出一个根 FolderSchema
```

`render_tunable_artifact_schema(s)` 渲染成"树 + 逐项 description"的 markdown 进 proposer prompt —— 唯一作用(软提示)。

## 2. 对齐 module + 入口 + 划"可调文件集"

1. **module 路径**(运行期包,任何名字,如 `<业务项目>/src/<pkg>`) = generate 的 `--agent-src`、= `INITIAL_ARTIFACTS_DIR` 的包根。
2. **找启动入口**(不假定具体名;很多 eddy 入口的入口在 `<pkg>` 下某处(如可调子包,但不限),但不限):grep `builder.build()`/`AgentBuilder`/模块顶 `agent = …`;读 `app-metadata.yml`/`server-simple.yaml`(`module_path`+`attr`)/`pyproject[tool.arec]`/`eddy run`/`CLAUDE.md`;列 `*agent*.py` 候选;候选给用户 → 确认入口(`<包内路径>:<attr>`);多义/找不到 → 让用户给。入口 = **"code integrity" 的 import 锚**。
3. **扫 module 全部文件/目录,过滤 `__pycache__`/`.pyc`**,逐个说清用途、逐条确认,**跟用户约定要优化哪些文件/目录**(= generate 的 `--tunable` 条目)。可调样例(以用户确认的为准,不硬挑):
   - 用 `<pkg>`-相对路径表达每条目:`<可调子包>`、`<可调子包>/<子集>`、`<顶层可调文件>` …(名字以项目实际为准)
   - 非可调(留 module,不进可调产物):env 运行配置、启动 bootstrap、(日志等非行为组件)、(大/重的非行为数据)、以及任何不打算改的部分。
   - ⚠ 可调部分**通常不能单独 import 跑**(入口 import 顶层非可调兄弟,如 顶层非可调兄弟(如运行配置/日志等;具体名以项目为准));运行靠 generate 的 "load 可调产物" 按可调条目合并回整个 module 才能跑(见 generate-evaluate-recipe)。

## 3. initial_artifacts_dir + load 流程

- `INITIAL_ARTIFACTS_DIR = <module>`(**包根**),入口脚本(后续)里设。
- 用**自定义 `CandidateStore`** 重写 `create_root`/`create_child` 的 `ignore_patterns`,**丢非可调**(步骤 2 里确认的非可调条目(以实际扫描+用户确认为准;别套任何别的项目的名));给窄集(只一个 skill/散落)时给一份精心 curated 的根(也按 `<pkg>`-相对路径)。AntOmniEvo `copytree(INITIAL_ARTIFACTS_DIR, candidate_artifact_dir)` → 候选可调产物 = 可调文件按 `<pkg>`-相对排好。
- 候选改那些;generate 跑候选时 HAPPENS: `generate --agent-src <module> --artifact-dir <candidate_artifact_dir> --tunable <pkg-rel-path> …` — load 按 `--tunable` 条目逐个对应到 `<pkg>/<ent>`(见 generate-evaluate-recipe §"load 可调产物 映射")。
- **重数据 (大/重的非行为数据) 不进可调产物**;generate 把它从运行期 symlink 进 checkout,不每 rollout 拷 重数据。即便真要优化它,另按单份共享 + symlink 进可调产物处理。

## 4. 写 `<exp_root>/antomnievo/<scenario>/tunable_artifact_defs/<domain>_tunable_artifact_def.py`(只列与用户对齐的那棵可调树;不改已装的包)

照搬一份**系统形态最像的** `<x>_tunable_artifact_def`(选 `tunable_artifact_schema.py` 的 `FileSchema`/`FolderSchema` + 描述 + 约束),`files` 树**只列跟你/用户约定的可调条目树**(把 env/bootstrap/非可调面 全删);各 path+description 用步骤 2 跟用户对齐的用途(过滤 pycache):

```python
from antomnievo.model.tunable_artifact_defs.common_descriptions import _ADDITIONAL_FILES_DESCRIPTION
from antomnievo.model.tunable_artifact_schema import FileSchema, FolderSchema, TunableArtifactSchema

_<DOMAIN>_ARTIFACT_DIR_DESCRIPTION = """\
The tunable-artifact directory holds the agreed TUNABLE artifacts of the ``<pkg>`` agent — only the files/dirs that the user chose to optimize. Non-tunable runtime (env config, bootstrap, 日志、大或重的非行为数据) is OUT of the tunable artifacts.
<一句话:agent 吃什么输入、产什么、怎么打分>.

## Global constraints
### No redundancy  <每条规则/工具/知识只在一处;规则与工具实现不许重复编码同一检查>
### No contradiction <系统 prompt 与 docstring/module/知识不许冲突;冲突选一处 canonical>
### Generalization  <每个通用陈述配一个具体例子(before/after 或真实失败 case)>
### Code integrity
- Edits MUST NOT break import relationships: after any change, ``python -c "import <步骤2入口 module>"`` must still succeed.
- 入口仍 import 顶层非可调兄弟(顶层非可调兄弟(如运行配置/日志等;具体名以项目为准));可调改动不得破坏这些 import。
- Do NOT introduce dangling references (删了还在 import / 改名没改调用点)。
"""

<DOMAIN>_TUNABLE_ARTIFACT_SCHEMA: TunableArtifactSchema = FolderSchema(
    name=<根>,                    # 用 step2 约定的根名(按步骤2 确认的根名)
    description=_<DOMAIN>_ARTIFACT_DIR_DESCRIPTION,
    files=[
        FileSchema(name="<确认的入口文件>.py", description="<系统 prompt + 装配;步骤2确认的入口>"),
        FolderSchema(name="<可调子包1>", description="<用途;与步骤2对齐>", files=[]),
        FolderSchema(name="<可调子包2>", description="<用途;与步骤2对齐>", files=[]),
        # ……按与用户对齐的可调条目树列,非可调一律不列……
        FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
    ],
)
```

- `INITIAL_ARTIFACTS_DIR` 在入口脚本设 `= os.path.normpath(os.path.join(<业务项目根>,"src","<pkg>"))`(配合自定义 store 的 ignore)。本步只写 `*_TUNABLE_ARTIFACT_SCHEMA`。

## 5. 坑

1. **别拿整个 module 当可调产物**(全进每 candidate、可改 env/bootstrap、爆炸);收窄到与用户约定的可调集 + 包根 initial_artifacts。
2. **TunableArtifactSchema "少动"是软提示不是隔离**;隔离 = 可调产物只含可调文件(initial_artifacts 根 + ignore/curated)。
3. **load 必 rm 后再 copy**(dir: `rm`+`copytree`;file: `copyfile`)—— `copytree(dirs_exist_ok=True)` 是 merge、会让删除/改名残留;见 generate-evaluate-recipe §load 映射。
4. **`__pycache__`/`.pyc` 一律过滤**;(大/重的非行为数据) 默认不进可调产物(symlink 进 checkout)。
5. **入口/包名别照抄现有 tunable_artifact_def**;用步骤 2 用户的确认结果。
6. **AgentSkills-style agent**(顶层 skill 文件 + scripts/ + references/ + assets/):`agent_skill_tunable_artifact_def.py` 是可照的系统形态之一(可调产物根就是那些 skill 文件);eddy python-package agent:用整条可调子包(或与用户约定的子集)作可调集。

## 6. sanity check(写完即自测)

```bash
<workspace>/.venv/bin/python -c "
from antomnievo.model.tunable_artifact_defs.<domain>_tunable_artifact_def import <DOMAIN>_TUNABLE_ARTIFACT_SCHEMA
from antomnievo.model.tunable_artifact_schema import render_tunable_artifact_schema
print(render_tunable_artifact_schema(<DOMAIN>_TUNABLE_ARTIFACT_SCHEMA)[:1200])
"
```
渲染出的树**必须只含与用户约定的可调条目**(无 env/bootstrap/非可调面/`__pycache__`)。把这段渲染给用户做步骤 3 的确认。
