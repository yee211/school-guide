# syntax=docker/dockerfile:1
# 后端镜像：FastAPI + LangChain
# 注意：torch 使用 CPU 版安装源，避免拉取数 GB 的 CUDA 包（本项目推理全部走云端 API，无需 GPU）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

WORKDIR /app

# 先装依赖，利用镜像缓存加速后续构建
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

# 拷贝后端代码
COPY backend/ backend/
WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
