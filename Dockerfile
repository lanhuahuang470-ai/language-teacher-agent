FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY src/language_tutor ./src/language_tutor
COPY src/graph ./src/graph
RUN pip install --no-cache-dir .
ENV TUTOR_HOST=0.0.0.0
EXPOSE 7860
CMD ["python", "-m", "language_tutor"]

