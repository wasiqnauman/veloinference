FROM python:3.14-slim

WORKDIR /app

COPY . .

CMD ["uv", "run", "python", "-m", "gateway.main"]
