FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web_search/ ./web_search/
COPY server.py .

EXPOSE 8787

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8787 \
    MCP_TRANSPORT=streamable-http

CMD ["python", "server.py"]
