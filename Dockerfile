FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tmux \
    bash \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 -o /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

WORKDIR /app

COPY . .
RUN pip install -r requirements.txt

RUN chmod +x entrypoint.sh

EXPOSE 9000

CMD ["./entrypoint.sh"]