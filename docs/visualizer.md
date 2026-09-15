# Visualizer

> **English** · [中文](./visualizer.zh-CN.md)

A React + TypeScript + Flask front-end that renders an evolution run from its workspace directory. It is a separate package, `ant-omnievo-visualizer`, under `visualizer/`.

## 1. Install

**pip** (two steps, from the repo root):

```bash
pip install -e .             # core ant-omnievo
pip install -e ./visualizer  # visualizer (adds ant-omnievo + flask deps)
cd visualizer && npm install # front-end build deps
```

**uv** (one step, from the repo root):

```bash
uv pip install -e ".[visualizer]"  # via [tool.uv.sources]: core + visualizer in one go
cd visualizer && npm install
```

## 2. Start

```bash
cd visualizer
antomnievo-visualizer-manage start
```

- Front-end: http://localhost:5173
- API: http://localhost:3001

`Ctrl+C` to stop. Point the front-end at the `workspace/<run>` directory you want to inspect.
