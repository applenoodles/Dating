# File: Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 先裝依賴，利用 layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再複製程式
COPY . .

EXPOSE 8501

# 用 streamlit 內建健康檢查端點
HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
