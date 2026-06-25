FROM python:3.10.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app /config ~/.config
RUN ln -s /config /root/.config/TorrUpd

WORKDIR /app

COPY requirements.txt .
COPY *.py .

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "torrent_updater.py" ]