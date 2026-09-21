# 可视化器

> [English](./visualizer.md) · **中文**

一个 React + TypeScript + Flask 前端,从一个 workspace 目录渲染整个进化过程。它是独立子包 `ant-omnievo-visualizer`,位于 `visualizer/`。

## 1. 安装

**pip**(两步,在仓库根目录):

```bash
pip install -e .             # 核心 ant-omnievo
pip install -e ./visualizer  # 可视化器(附带 ant-omnievo + flask 依赖)
cd visualizer && npm install # 前端构建依赖
```

**uv**(一步,在仓库根目录):

```bash
uv pip install -e ".[visualizer]"  # 通过 [tool.uv.sources]:核心 + 可视化器一次装好
cd visualizer && npm install
```

## 2. 启动

```bash
cd visualizer
antomnievo-visualizer-manage start
```

- 前端:http://localhost:5173
- API:http://localhost:3001

`Ctrl+C` 停止。把前端指向想看的 `workspace/<run>` 目录即可。

## 3. 界面导览

**Evolution — Lobster Gym。** 种群被渲染成一座健身房:候选个体以龙虾的形象训练,按分数分层归入不同的房间(顶层 Golden Hall,底层 Damp Basement)。每张卡片展示候选的短 id、代数/轮次/序号、平均分、相对 root 的提升、等级,以及实时状态(pending / evolving)。

![Evolution 标签页 — Lobster Gym](./assets/visualizer/gym.png)

**Lineage Tree。** 全部候选的父子关系树,每个节点标注分数、相对 root 的变化和等级徽章。`shift+click` 展开整棵子树;选中节点后在右侧打开详情面板。

![Lineage Tree 标签页](./assets/visualizer/lineage.png)

**Stats。** 最优平均分随迭代变化的曲线(含被接受的候选和 baseline),以及运行级计数:迭代进度、种群规模、创建总数、拒绝数、最高分、root/best id 和总耗时。

![Stats 标签页](./assets/visualizer/stats.png)

**Insights。** 逐题覆盖网格:任选一组候选,对比它们在每个数据集问题上的得分,所有候选都未解出的问题会高亮显示。

![Insights 标签页 — 覆盖网格](./assets/visualizer/insights.png)

**候选详情。** 点击候选打开详情面板:祖先链(含每一代的分数)、元信息(状态、父节点、反思深度、时间戳)、相对 root 的得分,以及可浏览的 system-run / proposer-run 文件。

![候选详情面板](./assets/visualizer/details.png)

**文件查看器。** 候选 workspace 目录下的所有产物(system run、proposer run、分数文件)都可以在应用内打开,带语法高亮和一键复制。

![文件查看器](./assets/visualizer/fileviewer.png)
