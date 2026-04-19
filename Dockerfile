FROM python:3.11-slim AS builder
ARG PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /build
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip --index-url ${PIP_INDEX_URL} && \
    python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); \
open('/tmp/reqs.txt','w').write('\n'.join(d['project']['dependencies']))" && \
    pip install --user --no-cache-dir --index-url ${PIP_INDEX_URL} -r /tmp/reqs.txt

FROM python:3.11-slim
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} bot && useradd -m -u ${UID} -g ${GID} bot
ENV TZ=Europe/Moscow \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/bot/.local/bin:$PATH
COPY --from=builder --chown=bot:bot /root/.local /home/bot/.local
WORKDIR /app
COPY --chown=bot:bot app/ ./app/
USER bot
CMD ["python", "-m", "app"]
