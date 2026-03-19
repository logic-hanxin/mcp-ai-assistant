FROM python:3.11-slim
WORKDIR /app

# 安装 Git 等基础工具
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# 复制当前目录下所有整理好的代码（包括 assistant 和 .env）
COPY . .

# 安装项目依赖
RUN pip install --no-cache-dir pypdf python-docx beautifulsoup4 qrcode pillow opencv-python requests mcp pymysql openai python-dotenv httpx fastapi uvicorn playwright -i https://mirrors.aliyun.com/pypi/simple/

# Playwright 浏览器依赖（关键！）
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# 安装 Chromium 浏览器
RUN playwright install chromium

# 这一步最关键：设置 PYTHONPATH，让 Python 能找到 assistant 包
ENV PYTHONPATH=/app

# 启动命令：必须匹配你的代码层级 assistant.web.run
CMD ["python", "-m", "assistant.web.run", "--host", "0.0.0.0", "--port", "8000"]
