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
