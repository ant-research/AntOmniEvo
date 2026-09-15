# ant-omnievo release pipeline (ACI)

`antomnievo/.aci/python/.aci.yml` publishes two internal Python packages — the
`ant-omnievo` core and `ant-omnievo-visualizer` (Flask viz backend) — to Ant's
internal package source, so both are `pip install`-able internally.

## What gets published

| Package | Built from | Note |
|---|---|---|
| `ant-omnievo` | `${ACB_BUILD_DIR}/code-repo` (repo root, flat) | publish first |
| `ant-omnievo-visualizer` | `${ACB_BUILD_DIR}/code-repo/visualizer` | depends on `ant-omnievo` (resolved from `simple` at install) |

Both: `python -m build` (sdist + wheel), setuptools; version `0.1.0` read from
each `pyproject.toml` — bump per release.

## Internal source

| Library | Where |
|---|---|
| Test (pre-prod) | `https://artifacts.antgroup-inc.cn/artifact/repositories/simple-dev/` |
| Production | `antArtifactRepo: simple` |
| Build deps | `https://pypi.antfin-inc.com/simple/` (`PIP_INDEX_URL`) |

Test-install: `pip install -i https://artifacts.antgroup-inc.cn/artifact/repositories/simple-dev/ <ant-omnievo | ant-omnievo-visualizer>`

## Pipeline (per package)

1. `build` / `build-visualizer` (`pypi-artifact-uploader`) — build sdist+wheel, upload to `simple-dev`.
2. **Verify & Confirm** — manual gate; test-install before promoting.
3. `select-artifact` / `select-visualizer-artifact` (`artifact-transfer-check`) — pick artifacts for `simple`.
4. `sync-to-prod` / `sync-visualizer-to-prod` (`ant-artifact-transfer`) — transfer to production; auto-skips if none selected, needs approver confirmation.

## Before first release

1. **Approvers** — `lyuyubin.lyb` + `hanpu.mwx` in each `sync-*-to-prod...confirm.approvers`. Per-package: these accounts need the **per-package** formal-library publish role on the platform; the `ant-omnievo` role does not cover `ant-omnievo-visualizer`.
2. **Version** — bump `version` in each `pyproject.toml` per release.

## README after install

Neither package declares a `readme` field, so each shows only its one-line
`description` on the artifact index / `pip show <pkg>`. The full visualizer docs
(install, run) live in the root `README.md` §9 *Visualizer* — the standalone
`visualizer/README.md` was merged into it.

## Pitfalls

- Publish `ant-omnievo` before `ant-omnievo-visualizer` — the visualizer's `ant-omnievo` dependency resolves from `simple` at install.
- Build is flat from each package dir (repo root / `visualizer/`), not a `python/packages/...` subdir.
- `PIP_INDEX_URL` is required or the isolated build hits the public PyPI.
