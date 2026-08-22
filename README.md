# Crypto Trend Scanner

每四小时扫描 CoinGecko 市值前 300 名资产，并使用 OKX（欧易） 已收盘日线与 4 小时 K 线筛选趋势突破及首次回踩候选。仅在出现新的 A/B 级信号时通过飞书机器人推送。

## 运行时间

工作流在 UTC 00:17、04:17、08:17、12:17、16:17、20:17 运行，对应北京时间 08:17、12:17、16:17、20:17、00:17、04:17。GitHub Actions 可能因平台负载产生少量延迟。

## 飞书配置

进入仓库：

1. Settings
2. Secrets and variables
3. Actions
4. New repository secret

创建 Secret：

- Name: `FEISHU_TREND_WEBHOOK`
- Value: 飞书自定义机器人的纯 Webhook 地址

不要把 Webhook 写进代码、Issue 或 Actions 日志。

## 手动测试

进入 Actions，选择 “Scan crypto trend setups”，点击 “Run workflow”。扫描结果会作为 artifact 保存 14 天；只有出现新的 A/B 级信号才会发送飞书。

## 核心硬条件

- 日线多头或阶段 1 启动
- 4 小时整理或波动收缩
- 已收盘 K 线突破
- 成交量不低于 20 期均量 1.5 倍
- 收盘处于 K 线振幅上部 30%
- 结构止损距离不超过 8%
- 至下一阻力至少约 2R
- 首次回踩必须守住突破位、缩量并重新转强

本项目只用于市场筛选和研究，不构成投资建议，也不会自动下单。
