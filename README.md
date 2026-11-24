# 衣序 · 智慧衣橱 Agent

前后端分离的 Docker 开发项目：Vue 3 / TypeScript / Pinia / Element Plus + FastAPI + MySQL + LangChain / LangGraph + DeepSeek。Redis/Celery 执行衣物识别、推荐和虚拟试衣，RustFS（S3 兼容对象存储） 私有存储图片，Nginx 提供同源入口。

## 启动

需要 Docker Desktop（Linux containers）。在 PowerShell 7 中执行：

```powershell
cd C:\Users\admin\Documents\简历\wardrobe-agent
./scripts/setup.ps1
```

打开 http://localhost:8088 ，首次使用注册账号。API 文档：http://localhost:8088/api/docs 。所有数据库和文件服务仅在 Docker 内网开放，现有本机服务不会被覆盖。数据保存在命名卷中。

脚本自动生成 `.env` 和随机本地密码。填入你自己的 `DEEPSEEK_API_KEY` 和 `ARK_API_KEY`（火山方舟） 后保存即可自动加载。密钥不要提交或发送到聊天。没有密钥时，账号、衣橱、手动分类、身材档案和照片管理可正常使用，AI 接口明确返回未配置错误。

## 功能与使用

1. 上传单件衣物照片（最多 12 MB），后台识别类别、颜色和季节；可编辑和设置清洗中/暂不可用。
2. 在个人档案保存自愿填写的身高、尺码、风格偏好、城市坐标及全身照。不会从照片猜测尺寸。
3. 在穿搭顾问提出场景和约束。LangGraph 调度衣橱、天气和偏好工具，生成候选搭配，校验真实 ID、可用状态与基本品类组合。错误时最多修复一次，仍失败则询问用户。
4. 继续同一对话可要求“只换外套”等调整。历史消息和推荐记录落 MySQL，重启后可继续会话。
5. 确认照片使用授权后，从穿搭结果生成完整试穿图；工作室显示阶段轨迹、检查结果、失败原因与重试入口，图片可删除。
6. 提交 1–5 分及文字反馈，后续推荐读取最近反馈。开启每日推荐后按北京时间整点生成，记录在任务列表，可从历史对话打开。

天气使用 Open-Meteo 公共 API，商用部署需要根据供应商条款配置适用套餐。接口失败时返回天气缺失提示，模型应询问温度，不使用虚构天气。

## 虚拟试衣

试衣使用 **DeepSeek + Seedream 的 LangGraph Harness**。DeepSeek 处理规划、图像检查与修正指令；豆包 Seedream 执行多图编辑，人物照和所有衣物图作为同一次生成的参考图。

```text
校验本人照片和真实可穿衣物
  → DeepSeek 多图理解并制定试衣计划
  → Seedream 生成一张完整穿搭图
  → DeepSeek 比较原人物、原衣物和生成图
  → 通过：保存私有结果
  → 未通过：修正提示词，使用原始参考图重新生成
  → 达到预算仍未通过：标记失败，不返回合格结果
```

Harness 的具体控制：白名单图像工具、Pydantic 输出校验、默认最多两次生成（1–3 可配置）、单次图像调用 240 秒超时、整体 900 秒阶段预算、规划与检查各最多输出 1800 tokens、图片格式/尺寸检查、重复投递防护、结果保存前再次核对衣橱状态。提供方网络错误不自动重复生图，避免隐含增加调用次数。视觉检查属于模型判断，可能误判，不保证真实合身度或每个细节都正确。

每次计划、生成、检查、修正的阶段记录存入 MySQL Job.trace；包含衣物 ID、提示词版本、原始参考图 SHA-256、生成次数和检查结果。不记录 API 密钥、base64 图片或模型隐含思维过程。LangGraph 使用本地执行，不需要 LangSmith 服务。

配置方式：

```dotenv
DEEPSEEK_API_KEY=填写你自己的新密钥
ARK_API_KEY=填写火山方舟密钥
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_IMAGE_MODEL=doubao-seedream-5-0-flash-260915
ARK_RESPONSE_FORMAT=url
TRYON_MAX_ATTEMPTS=2
```

需在火山方舟开通对应图片模型，也可把 ARK_IMAGE_MODEL 改为你已开通且支持多图编辑的 Seedream Model ID / Endpoint ID。保存配置后，API、Worker 和定时进程自动重载，刷新网页即可。两个平台按各自服务计费；只拥有 DeepSeek 密钥不能调用豆包生图。无凭据时明确返回 503，不提供伪造生成结果。

原全身照和衣物图会发送给 DeepSeek 与火山方舟；提交试衣任务前需在页面确认。只交付模型视觉检查通过的图，仍需用户自己判断搭配效果。此前第三方专用试衣 API 已移除。

## 架构与可靠性边界

```text
浏览器 → Nginx → Vue/Vite
               → FastAPI → MySQL / RustFS（S3 兼容对象存储）
                         → Redis → Celery Worker → DeepSeek（规划/检查）+ Seedream（图片生成）
                                  Celery Beat（单实例）
```

开发配置将前端目录、后端源码及 `.env` 直接挂载进容器。前端使用 Vite 热更新，API、Worker 和 Beat 由开发监视器在保存源码或 `.env` 后自动重载，无需重建镜像。Worker 会先完成正在执行的任务再重载。之后启动使用 `./scripts/dev.ps1` 或 `docker compose up -d --no-build`；只有新增/修改依赖时才需更新依赖镜像。API 和 Worker 可独立容器部署；Compose 在本机启动多服务，不代表已经部署跨主机集群。MySQL 保存会话、业务状态、任务结果和可审查的工具/校验轨迹，不记录模型隐含思维过程。LangGraph 单次运行状态位于内存，尚未实现节点级 checkpoint，Worker 中断的任务由定时任务在 40 分钟后标记失败，用户可重新提交（可能产生新的供应商费用），不承诺断点恢复或 exactly-once。

生产前需替换 Vite 为静态构建服务、开启 HTTPS/COOKIE_SECURE、配置备份与资源限制、网关限流和监控。不要直接把开发 Compose 暴露公网。原始个人照片和生成图为私有对象，通过已登录且所属用户匹配的接口读取；删除入口会删除对应对象。

## 开发与检查

```powershell
docker compose ps
docker compose logs --tail=100 api worker
docker compose exec api pytest -q
docker compose exec frontend npm run build
docker compose exec api python scripts/smoke.py
docker compose exec api python scripts/smoke_tryon.py
docker compose stop
```

`smoke.py` 使用随机测试用户检查账号、图片上传、编辑、对象隔离、档案、会话和任务接口，不调用收费模型。业务规则单测包含虚构衣物、清洗状态、重复和品类冲突。更改数据模型后添加 Alembic migration，不修改已发布迁移。

参考：[DeepSeek 图片输入](https://api-docs.deepseek.com/guides/vision/)、[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)、[火山方舟图片生成 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)。
