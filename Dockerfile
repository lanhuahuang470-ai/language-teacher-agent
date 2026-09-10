FROM python:3.13-slim

WORKDIR /app

# 先复制依赖声明，利用 Docker 层缓存：只有依赖变更时才重新 pip install
COPY pyproject.toml requirements.txt ./
COPY src/language_tutor ./src/language_tutor
COPY src/graph ./src/graph

# 以可编辑模式安装包，使 pyproject.toml 的 packages.find 能正确定位 src 下的模块
RUN pip install --no-cache-dir -e .

ENV TUTOR_HOST=0.0.0.0
EXPOSE 7860

CMD ["python", "-m", "language_tutor"]
