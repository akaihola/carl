# Carl's server: the page, the WebSocket and the API, with the config file and
# prompts baked in. Nothing secret goes in: the secrets are the container's
# secret environment variables. Build from the repo root; see
# docs/operations.md.

ARG PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim

FROM ${PYTHON_IMAGE} AS build
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
# Behind a TLS-intercepting proxy, pass its CA bundle as the optional build
# secret `ca` (docker build --secret id=ca,src=…). It never enters the image.
RUN --mount=type=secret,id=ca \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca PIP_CERT=/run/secrets/ca; fi \
    && pip install --no-cache-dir uv==0.8.17 \
    && uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=secret,id=ca \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi \
    && uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE}
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY config.toml ./
COPY prompts ./prompts
ARG GIT_COMMIT=unknown
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080 CARL_COMMIT=${GIT_COMMIT} CARL_CLOUD=1
USER nobody
EXPOSE 8080
CMD ["carl", "serve", "--host", "0.0.0.0"]
