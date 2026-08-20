FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY package.json package-lock.json tailwind.config.cjs ./
RUN npm ci

COPY . .

EXPOSE 8001

CMD ["sh", "-c", "npm run css:build && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"]
