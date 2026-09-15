# 上下文恢复配方(长跑优化 → 用户清上下文后)

优化是长会话(max_iterations × batch = 数天甚至数周)。用户清上下文/重启对话后,执行者不会记得上次跑到哪。

> 目录概念(见 SKILL.md『两个目录概念』):`<exp_root>` = 实验根目录(NOTES.md/config/run.env 在这);`<run_dir>` = candidate store 的单次 run 目录(`<candidate_store_root>/run_<ts>/`,candidates//logs/statistics.json 在这)。

## 1. 保存动作(每次跑优化或跑完必做)

在 `<exp_root>/NOTES.md` 追加 `## 优化运行 <时间戳>`:

1. 路径:`<run_dir>` + config YAML + log + statistics.json
2. 配置摘要:smoke / eval_stage / hyperparams / proposer model / budget
3. **config YAML 里所有 credential 的过期时间**:遍历 `system.*` 和 `proposer.*` 里所有 token-like 字段(以 `eyJ` 开头的 JWT),用 python decode `exp` claim 记录;非 JWT 的 credential 标"非过期型,无需检查"。如果离过期 <2h → 立刻提醒用户换 credential。
4. 运行状态:current_iteration / accepted / rejected / best_candidate_id / best batch sum(via statistics.json + grep log)
5. 遗留事项(比如"可调 min_improvement_per_batch 加速";"credential N 小时后过期需换")

## 2. 恢复操作(新上下文第一步)

```bash
# 1. 读 NOTES.md(最快的恢复入口: 路径+配置+状态+遗留事项一目了然)
cat <exp_root>/NOTES.md
# 2. 读 statistics.json: current_iteration / best_candidate_id / avg_score
python3 -c "import json; s=json.load(open('<run_dir>/logs/statistics.json')); print(s)"
# 3. tail log: 看最新进展(iteration / scores / accepted / rejected)
tail -20 "<run_dir>/optim_*.log"
# 4. grep batch scores: Parent→Child improvement 历史
grep -E "Parent.*scores|Child.*scores|accepting|rejecting" "<run_dir>/optim_*.log"
# 5. 看是否还在跑
pgrep -af "<entry script pattern>"
# 6. 如果停了: resume = 同 --config (config 里 <run_dir> 不变 → AntOmniEvo 自动 resume from checkpoint)
```

## 3. credential 过期检测(通用,不只针对某个 token)

- 遍历 config YAML 里所有 credential 字段(system.* + proposer.*),用 python decode JWT exp claim(如果是 JWT);非 JWT 的 credential 不需要检查。
- **batch scores 突然从高跌到低(如高分突降为异常低分) = credential 过期的典型症状** → 第一步检查 credential 是否过期 → 从用户拿新 credential → 更新 config YAML + 重物化 `run.env` → resume。

## 4. 蚂蚁内部 MCP credential 过期 → 主动诊断 + 引导用户换 token

章节前提:蚂蚁内部 MCP(adconfig MCP / mcpnexus.alipay.com)的 JWT token 有效期 24h,过期后 agent 拿不到 MCP 资源 → batch score 从高跌到低。此章节含两步:主动诊断 + 引导用户去签发新 token。

### 4.1 什么时候怀疑 MCP credential 过期

如果优化跑着跑着 batch score 突然从高分异常跌到低分,或者 process judge reason 中出现以下关键词,第一个要排除的是 **MCP credential 过期**:

- `MCP_ERROR` / `McpError` / `认证不可用` / `无员工身份` / `403` / `身份` / `token 过期`
- agent 日志里 MCP connect failure(traceback `connect_to_server / failed for server`)

→ **执行者主动跟用户说**: "batch score 异常从高分跌到异常低分, 看起来是 MCP credentials(token)过期了 — agent 拿不到 MCP baseline, process judge 批仅给低分。你能否去以下地址重新签发 MCP token?"

### 4.2 蚂蚁内部 MCP token 换取(用户操作步骤)

1. 打开签发页: `https://login-intranet.alipay.com/pub/oauth/AppAuthorize.htm?token=2026082836a1c7f210bd48de9afba03a4ffb` (token 参数可能更新; 问用户最新的 URL)
2. 在页面输入栏输入 MCP server host: `mcpnexus.alipay.com`
3. 页面签发 JWT 身份凭证 = 你的 `system.iam_token` 值
4. 把签发的 token **原值**贴给执行者(不要手敲 → silent corruption;copy-paste)
5. 执行者用 python 精确更新 config YAML + `.env.local` + 重物化 `<run_dir>/run.env`:
   ```python
   import yaml, os
   cfg = yaml.safe_load(open("opt_config.yaml"))
   cfg["system"]["iam_token"] = "<用户贴过来的原值>"
   yaml.dump(cfg, open("opt_config.yaml", "w"), allow_unicode=True, default_flow_style=False, sort_keys=False)
   # 更新 .env.local 的 IAM_TOKEN=\<新原值>
   # 重物化 <run_dir>/run.env 追加 IAM_TOKEN=\<新原值>
   ```
6. **resume**: 同 `--config opt_config.yaml`(config 里 `<run_dir>` 不变 → AntOmniEvo 自动 resume from checkpoint;不用停现行程 — 下一个 candidate 的 generate.py 会自动读新 run.env)
7. **不要手敲 credential** (长 JWT 手敲易错 → 一字符错 → MCP 持续 403); 用 python 按精确值替换 + decode exp 验证。