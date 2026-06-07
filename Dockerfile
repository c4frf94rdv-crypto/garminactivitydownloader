FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ttyd \
    tmux \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .
RUN pip install -r requirements.txt

RUN chmod +x entrypoint.sh

EXPOSE 9000

CMD ["./entrypoint.sh"]