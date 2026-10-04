# School Guide · 宝塔轻量服务器部署指南

适用环境：宝塔面板轻量服务器（4核4G），后端 Docker 化 + 前端宝塔站点托管。

## 架构总览

```
用户 → 宝塔 Nginx（80/443）
         ├─ /            → 前端静态文件（frontend/dist）
         └─ /chat、/knowledge → 反向代理 → 127.0.0.1:8000
                                            │
                               Docker Compose（仅本机可访问）
                               ├─ backend（FastAPI/uvicorn）
                               ├─ db（pgvector/pgvector:pg16）
                               └─ redis（redis:7-alpine）
```

LLM / Embedding / Rerank 全部走云端 API，服务器无需 GPU。

## 第 1 步：宝塔面板准备

1. 软件商店安装 **Nginx**（任意稳定版）和 **Docker**（宝塔的 Docker 服务自带 docker compose）。
2. 添加 4G 交换分区（4G 内存建议加，防止构建/解析文档时内存不够）：

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

3. 放行端口：宝塔面板「安全」放行 80、443；同时在**云厂商控制台的轻量服务器防火墙/安全组**里放行 80、443（两边都要放）。
4. （推荐）Docker 拉取镜像慢的话：宝塔 Docker 设置里配置镜像加速源。

## 第 2 步：上传代码

本地打包项目（**排除** `.venv`、`node_modules`、`__pycache__`），通过宝塔「文件」上传到例如 `/www/wwwroot/school-guide` 并解压。目录结构应为：

```
/www/wwwroot/school-guide/
├── backend/
├── frontend/dist/      ← 前端构建产物（必须包含）
├── requirements.txt
└── deploy/             ← 本部署目录
```

> 如果本地 `frontend/dist` 不是最新的，先在本地执行 `cd frontend && npm run build` 再上传。

## 第 3 步：配置环境变量

```bash
cd /www/wwwroot/school-guide/deploy
cp .env.example .env
vi .env    # 填入各家 API Key、模型名、Base URL 和数据库密码（与你本地 .env 一致）
```

## 第 4 步：构建并启动容器

```bash
cd /www/wwwroot/school-guide/deploy
docker compose up -d --build
docker compose ps          # 三个服务都应是 running/healthy
docker compose logs -f backend   # 跟踪日志，看到"知识库检索预热"即启动成功
```

首次构建安装轻量依赖（markitdown 等），仅需 1~2 分钟即可完成构建。

## 第 5 步：初始化知识库数据

首次部署需要灌入知识库（后端容器内执行）：

```bash
cd /www/wwwroot/school-guide/deploy
# 构建向量索引（读取 backend/data/raw 下的文档）
docker compose exec backend python -m scripts.build_index
# 导入结构化招生/录取数据
docker compose exec backend python -m scripts.import_structured
```

后续也可以直接通过网页端 `/knowledge/upload` 上传新文档。
注意：采用 MarkItDown 轻量解析引擎，无需下载额外深度学习模型权重，即开即用。

## 第 6 步：创建前端站点并配置反代

1. 宝塔「网站」→ 添加站点（填域名或服务器 IP），根目录如 `/www/wwwroot/school-web`。
2. 把 `frontend/dist` 里的**内容**（index.html、assets、school-logo.png）上传到站点根目录。
3. 站点 → 设置 → 配置文件，参照 `deploy/nginx-proxy.conf`，把其中的 location 片段合并进 `server {}` 块并保存。

## 第 7 步：验证

```bash
curl http://127.0.0.1:8000/docs    # 后端存活
```

浏览器打开 `http://服务器IP`，能看到前端页面并正常对话即部署成功。

## HTTPS（可选）

有域名的话：站点 → SSL → Let's Encrypt 申请证书并开启强制 HTTPS。
注意：国内服务器绑定域名访问需完成 ICP 备案；仅用 IP 演示则不需要。

## 日常维护命令

```bash
cd /www/wwwroot/school-guide/deploy

docker compose logs -f backend      # 查看后端日志
docker compose restart backend      # 重启后端
docker compose down                 # 停止全部（数据在卷里，不会丢）
docker compose up -d --build        # 更新代码后重新构建启动

# 备份数据库（建议定期）
docker compose exec db pg_dump -U school school > backup_$(date +%F).sql
```

更新代码流程：上传新代码覆盖 → `docker compose up -d --build`；仅前端改动时只需替换站点目录里的 dist 文件。

## 常见问题

- **端口 8000 访问不到**：正常，后端只绑定 127.0.0.1，必须通过站点反代访问。
- **流式回答变成一次性输出**：确认 nginx 中 `/chat` 的 `proxy_buffering off;` 已生效。
- **依赖下载较慢**：给 Docker 配置国内镜像加速，并确认 pip 使用可访问的镜像源。
- **内存不足进程被杀**：确认已加 swap；构建镜像时最吃内存。
- **数据库连接失败**：等 db 容器 healthy 后 backend 才会启动（compose 已配置），若仍失败看 `docker compose logs db`。
