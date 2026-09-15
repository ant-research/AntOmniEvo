# 数据层配方 (data_inst + data_loader)

新领域接入 AntOmniEvo 的数据层(对应 SKILL.md 步骤 2)。范式对照 `antomnievo/dataset/<既有某 domain>/` 任选一份(结构/契约对齐,别照字段)。

## 基类契约

`antomnievo.interface.data_inst.DataInst` 是 pydantic `BaseModel`,只强求三字段 + 算个 `.name`:

```python
class DataInst(BaseModel):
    id: str         # 数据实例标识
    query: str      # 输入问题/需求
    golden_answer: str  # ground truth(结构化对象先 json.dumps 成字符串)
    @property
    def name(self) -> str: return self.__class__.__name__
```

子类只管加领域字段 + 重数据留 `raw`。

## 文件清单(放组件目录 `<exp_root>/antomnievo/<scenario>/dataset/`;不改已装的包)

```
<exp_root>/antomnievo/<scenario>/dataset/
  __init__.py
  <domain>_data_inst.py        # <Domain>DataInst(DataInst)
  <domain>_dataset_loader.py    # async load_dataset(...)
```

## `<domain>_data_inst.py` 模板(结构对照所选既有 domain 的 `*_data_inst.py`)

```python
from __future__ import annotations
import json
from pydantic import Field
from antomnievo.interface.data_inst import DataInst


class <Domain>DataInst(DataInst):
    """<领域> case 数据实例。范式:<输入> → agent 产出 <产物> → 与 <gold> 比对。

    原始 case 行整行留在 ``raw``(``exclude=True``,不进 RunRecord),
    供 to_case_dict 原样回写 _batch.jsonl——子进程常要原始全字段。
    """

    category: str = Field(default="", description="Case 分类,供 proposer 参考")
    # ……其它领域分析用字段
    raw: dict = Field(default_factory=dict, exclude=True)

    def to_case_dict(self) -> dict:
        return self.raw

    @classmethod
    def from_raw(cls, raw: dict) -> "<Domain>DataInst":
        case_id = raw.get("case_id", "") or raw.get("id", "")
        inp = raw.get("input", {}) or {}
        query = str(inp.get("user_request") or inp.get("query") or "")
        # 回放/约束上下文按该领域实际位置取
        # gold:可能直接答案,也可能结构化对象
        expected = raw.get("expected", {}) or {}
        golden_answer = json.dumps(expected, ensure_ascii=False)  # 整体结构化 -> str
        category = str(raw.get("category", ""))
        return cls(id=str(case_id), query=query, golden_answer=golden_answer,
                   category=category, raw=raw)
```

## `<domain>_dataset_loader.py` 模板

```python
import json, logging, os, random
from antomnievo.dataset.<domain>.<domain>_data_inst import <Domain>DataInst
logger = logging.getLogger(__name__)

async def load_dataset(cases_jsonl: str, max_samples: int = 0, shuffle: bool = False) -> list[<Domain>DataInst]:
    if not os.path.isfile(cases_jsonl):
        raise FileNotFoundError(cases_jsonl)
    result = []
    with open(cases_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: raw = json.loads(line)
            except json.JSONDecodeError as e: logger.warning(f"Skip malformed: {e}"); continue
            if not (raw.get("case_id") or raw.get("id")): logger.warning("Skip no-id"); continue
            result.append(<Domain>DataInst.from_raw(raw))
    if max_samples > 0: result = result[:max_samples]
    if shuffle: random.shuffle(result)
    logger.info(f"Loaded {len(result)} <domain> cases from {cases_jsonl}")
    return result
```

## 抽取要领(结构对照所选既有 domain)

从所选既有 domain 的 `*_data_inst.py:from_raw` 学**抽取手法**(**别套字段名**),再按新领域**实际样本**改:
- `id` ←  case row 的唯一标识字段(pos: `case_id`/`query_id`/`id`…)
- `query` ←  输入字段 + (如有)回放/约束 extra_context 拼进去
- `golden_answer` ←  gold 字段(结构化对象先 `json.dumps` 成 str,基类要 str)
- 可选分析字段(类目/难度…)
- `raw` ←  整 case 行(供 `to_case_dict()` 回写)

## 坑

1. **`golden_answer` 必须是 str**。若 gold 是结构化对象/列表,先 `json.dumps`。后续 evaluate 再按领域逻辑反序列化比对。
2. **重数据留 `raw` + `exclude=True`**。不要为了"好看"把整个 case 摊成几十个 pydantic 字段——会爆、会丢类型、会难回写。`to_case_dict()` 原样回原始行。
3. **先对齐再写**:实际读样本确认字段名/嵌套层级,**别照别的领域猜**。新领域的字段结构(输入/gold/extra)与既有 domain 可能完全不同 —— 以你和用户读样本后确认的为准。
4. **load_dataset 是 async**:AntOmniEvo 框架按 await 调。纯文件读取但签名也要 `async def`。
5. **registry**:若 `antomnievo/dataset/__init__.py` 或别处有域名登记,记得按同样方式注册新域名,否则入口找不到。

## sanity check(写完立刻自测)

```bash
python -c "import asyncio;from antomnievo.dataset.<domain>.<domain>_dataset_loader import load_dataset as L;\
r=asyncio.run(L('<test_path>', max_samples=3));\
print(len(r));print(r[0].id, r[0].query[:40], r[0].golden_answer[:40]);assert all(x.id and x.query for x in r)"
```
N 条、`id/query/golden_answer` 都非空即过。
