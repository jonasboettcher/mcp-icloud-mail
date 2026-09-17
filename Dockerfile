FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml /app/
COPY icloud_mail /app/icloud_mail
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home connector
USER connector
ENV ICLOUD_MAIL_CONFIG=/run/secrets/icloud_config PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
ENTRYPOINT ["icloud-mail-mcp", "--host", "0.0.0.0"]
