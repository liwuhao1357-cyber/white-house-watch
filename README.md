# WHITE HOUSE / WATCH V0.3

原版深黑、藏蓝、香槟金界面；零预算部署修订版。

## 运行方式
- GitHub 公开仓库，Actions 标准 ubuntu-latest 运行器，每 5 分钟请求三个 RSS；可能排队或延迟。
- 数据保存为本仓库 feed.json；保留最近 500 条、每条最多 280 字符摘录、原链接与源检查时间。
- EdgeOne 免费方案直接上传；edge-functions/api/feed.js 读取公开数据，经网站同域接口提供给浏览器。数据更新不触发构建。
- 不使用收费 API、服务器、自购域名、付费运行器、个人令牌或共享写入密钥。翻译关闭。

## 数据来源与边界
Trump’s Truth 是 Defending Democracy Together 维护的第三方档案，非 Truth Social 官方接口；其 FAQ 明确提供 RSS 订阅。白宫公告和总统行政文件来自 whitehouse.gov RSS。保留来源链接；停用未经确认许可的 CNN JSON 备用采集。本站为独立项目，非白宫或任何信源的官方网站。

RSS 可订阅不等于无限转载许可。面向国内公众提供时政新闻服务涉及许可及稿源要求；部署可用不等于已完成公开运营合规认定。不要据此声称有运营资质。人工翻译未提供，不伪装中文译文。

## 验证与维护
`python3 -m unittest -v test_collector`，再执行 `python3 collector.py` 可采集真实数据。全部源失败时拒绝覆盖旧数据；页面显示最后采集时间，超过 30 分钟提示陈旧。公开仓库长时间无活动时 GitHub 可能禁用定时任务。

EdgeOne 直接上传的 ZIP 根目录需包含 index.html 和 edge-functions。不要将 ZIP 本身当作网站文件。免费域名有效期及账户实际额度以控制台为准，不开启自动升级或付费方案。
