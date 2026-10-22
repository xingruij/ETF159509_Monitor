# 景顺纳指科技 ETF（159509）溢价率提醒：GitHub Actions + ntfy

个人使用的免费示例项目：每小时检查一次，网页设置阈值（默认 10.00%）；溢价率**跌破阈值**时提醒一次；重新回到阈值或以上后重新布防。

> **重要：数据源不是官方行情 API。** 项目使用东方财富公开行情接口的 `f402` 字段（社区资料将其解释为“折价率”，负数代表溢价），并以 `premium_pct = -f402` 得到溢价率。不同接口/时段可能变化，首次部署必须按“行情接口验证”核对同一时刻券商行情；未验证前不要把提醒用于交易决策。每小时采样会漏掉小时内短暂越线，GitHub Actions 定时任务也可能延迟。

## 项目结构

- `monitor.py`：取行情、计算溢价率、判断一次性提醒/重新布防。
- `config.json`：公开配置，仅存阈值与非秘密参数。
- `state.json`：告警布防状态；由 Action 自动提交更新。
- `.github/workflows/monitor.yml`：每小时运行 + 手动诊断/测试。
- `docs/`：GitHub Pages 网页设置阈值。

## 免费部署

### 1. 建 GitHub 仓库

1. 在 GitHub 新建仓库，建议设为 **Private**（GitHub Pages 的可用性/免费条件取决于账号与仓库类型；若 Pages 在私有仓库不可用，可用 Public，但请确认仓库中绝不含密钥）。
2. 解压本 ZIP，把全部文件上传到仓库根目录并提交到 `main` 分支。
3. 在仓库 **Settings → Actions → General → Workflow permissions** 中允许工作流读写仓库内容（若此选项存在）。工作流本身已声明 `contents: write`。

### 2. 设置 ntfy iPhone 通知

1. 在 iPhone App Store 安装 **ntfy** 官方应用，打开后添加一个主题（topic）。
2. 主题名必须随机且不可猜，例如用密码管理器生成 32–48 位字母/数字/下划线/连字符；不要使用 `159509`、姓名、生日等可猜内容。
3. 在仓库 **Settings → Secrets and variables → Actions → New repository secret** 新建：
   - Name：`NTFY_TOPIC`
   - Value：上一步的随机主题名（不是完整 URL）
4. 该主题在 ntfy.sh 上是公开可订阅/发布的；随机主题只是降低被猜到的概率，不等同于访问控制。不要把主题写入仓库、网页或截图。若担心公开主题隐私，可改用有访问控制的自托管 ntfy 服务并相应修改 `NTFY_BASE_URL`。

### 3. 首次验证行情接口（务必先做）

1. 仓库 **Actions → ETF premium monitor → Run workflow**，勾选 `diagnostics`，运行。
2. 打开运行日志，查找 `RAW_QUOTE_JSON` 与 `INTERPRETED`。程序请求的是：
   `https://push2delay.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f2,f12,f14,f18,f402&secids=0.159509`
3. 核对 `f12` 是 `159509`、`f14` 名称正确、`f2` 最新价与券商行情大致一致，并且 `f402` 有数值。项目按 `premium_pct = -f402` 解释它。
4. 同一时刻打开券商或可信行情软件，核对溢价率方向和数量级。若软件显示溢价约 +X%，接口 `f402` 应大致为 -X；若不是，**不要继续启用提醒**。接口资料可能过时或字段定义变更。
5. 非交易时段可能是上一交易日/延时值；务必在交易时段核验。运行日志会显示 API 返回原始 JSON，不会输出 `NTFY_TOPIC`。

也可以在浏览器直接打开上面的 URL 查看 JSON。若接口返回空、没有 `data.diff`、没有 `f402` 或代码/名称不匹配，视为验证失败，不要手动猜字段。

### 4. 测试 ntfy 推送

1. 仓库 **Actions → ETF premium monitor → Run workflow**，勾选 `test_notify`，运行。
2. iPhone 应收到测试消息。若没有，检查 `NTFY_TOPIC` secret、iPhone ntfy 是否订阅同一个 topic、iOS 通知权限、专注模式和网络。

### 5. 启用每小时监控

1. 在仓库 **Settings → Pages**，Build and deployment 选择 **Deploy from a branch**；Branch 选 `main`，文件夹选 `/docs`，保存。
2. 等待 Pages 部署完成，打开页面地址（一般是 `https://<用户名>.github.io/<仓库名>/`）。
3. 页面输入 GitHub 仓库所有者、仓库名、分支（默认 `main`），设置阈值（默认 `10.00%`），再输入 Fine-grained Personal Access Token 并保存。
4. token 仅在当前页面内存中使用，不写入 localStorage；刷新页面后需重新输入。只给这个仓库授权 **Contents: Read and write**，不要使用 classic PAT 的全仓库权限。不要将 token 放进 HTML/JS、仓库文件、GitHub Actions secret 或截图。
5. 保存后会更新仓库根目录 `config.json`。阈值以百分数输入，例如 `10` 表示 10%。
6. 到 **Actions → ETF premium monitor** 手动运行一次（不勾 diagnostics）确认流程成功。之后按每小时 UTC 分钟 17 运行；GitHub 定时任务可能延迟，且公共仓库通常比私有仓库更可靠。

## 阈值与告警逻辑

- 默认阈值 `10.00%`。
- 仅当 `溢价率 < 阈值` 且当前处于“已布防”状态时发送一次提醒，并解除布防。
- 当 `溢价率 >= 阈值` 时重新布防，不发送“恢复”通知。
- 例如阈值 10%：11% → 9.8% 会提醒一次；之后 8% 不重复；再次回到 10% 或更高后重新布防；下一次跌破 10% 再提醒。
- 若某次行情请求失败，工作流失败并在日志中说明，不会用空值/旧值冒充当前溢价率。

## 安全与限制

- **不要把任何 token 或 ntfy topic 提交进 Git。** 若误提交，立即撤销/轮换。
- 网页需要 Fine-grained PAT 才能修改仓库配置；只授予单仓库 Contents 读写权限，保存阈值后可以撤销 token（下次改阈值再生成一个）。GitHub API 会把配置更新记录在提交历史中。
- 网页与 `config.json` 都不存 token；token 仅存在当前浏览器标签页内存，关闭/刷新即清除。但不要在不可信设备上输入 PAT。
- ntfy.sh 主题是公开的；任何知道主题名的人都可能订阅或发消息。主题名应高熵随机生成。
- GitHub Actions cron 不是精准闹钟；交易时段之外也可能拿到延时/上次值。项目是个人提醒工具，不构成投资建议，也不保证消息实时或必达。
- 免费服务政策和限额可能变化。请定期检查 Actions 运行记录与行情接口是否仍有效。

## 本地运行（可选）

需要 Python 3.11+ 和 `requests`：

```bash
pip install -r requirements.txt
python monitor.py --diagnostics
```

本地不设置 `NTFY_TOPIC` 时只打印行情和状态判断，不会发送推送。测试推送：

```bash
NTFY_TOPIC='你的随机主题' python monitor.py --test-notify
```
