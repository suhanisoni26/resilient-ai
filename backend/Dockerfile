FROM python:3.11-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt
FROM python:3.11-slim
COPY --from=build /install /usr/local
WORKDIR /app
COPY main.py .
EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
