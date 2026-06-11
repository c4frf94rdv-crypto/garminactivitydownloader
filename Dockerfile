FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tmux \
    bash \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Checksum from the official release: https://github.com/tsl0922/ttyd/releases/download/1.7.7/SHA256SUMS
RUN curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 -o /usr/local/bin/ttyd \
    && echo "8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55  /usr/local/bin/ttyd" | sha256sum -c - \
    && chmod +x /usr/local/bin/ttyd

WORKDIR /app

COPY . .
RUN pip install -r requirements.txt

RUN chmod +x entrypoint.sh

EXPOSE 9000

CMD ["./entrypoint.sh"]