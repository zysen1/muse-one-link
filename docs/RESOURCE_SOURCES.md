# 免费云资源：官方核对入口

本页提供查规则的起点，不承诺任何账号都能领取、任何地区都能连接，也不将下面的平台视为已部署服务。Muse 每次执行 [免费云环境案例](../cases/cloud/README.md) 时，都应读取当前官方说明和账号实际状态，再选择适合项目的方案。

文档入口核对日期：2026-11-13。避免把这里的日期当成后续运行时的核对日期。

| 用途 | 官方入口 | 执行时重点核对 |
| --- | --- | --- |
| 临时开发、跑代码和演示 | [GitHub Codespaces 计费与个人额度](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces) | 账号剩余额度、计算与存储用量、预算和收费条件 |
| 开发环境能运行多久 | [Codespaces 生命周期](https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle) | 空闲停止、最长运行时间、数据保存与删除规则 |
| 静态网站托管 | [Cloudflare Pages 限制](https://developers.cloudflare.com/pages/platform/limits/) | 项目是否为静态站点、构建和文件限制；有后台逻辑时另核对运行方式 |
| 轻量服务与接口 | [Cloudflare Workers 计费](https://developers.cloudflare.com/workers/platform/pricing/) | 免费档调用与执行限制、需要的存储产品、超额行为；它不是通用 VPS |

这份清单不是固定选型。用户已有可用的云服务或给了其他平台链接时，优先核对其官方文档和当前账号条件。动态规则以运行时核对结果为准，平台报错和登录页不算资源已领取。

## 一份有用的核对记录

```text
项目需求：
候选平台与方案：
官方规则链接与核对日期：
当前账号是否具备资格、剩余多少额度：
适合的用途及不能做的部分：
是否要求登录、验证或付款方式：
免费期限、停止或休眠规则：
超额行为、实际预算设置：
源码与数据如何备份：
当前进度：候选 / 待用户操作 / 已创建资源 / 已部署 / 已验收外部访问
```

记录实际信息即可；不要把凭据写入这份文档。若某项查不到，写“未确认”和下一步检查方式，不自行补全。
