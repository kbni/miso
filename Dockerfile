FROM python:3.7-slim-buster as base

FROM base as builder
RUN apt-get update && apt-get install -y gcc
RUN mkdir /install
WORKDIR /install
COPY requirements.txt /requirements.txt
RUN pip install --no-warn-script-location --no-cache-dir --prefix=/install -r /requirements.txt

FROM base
COPY --from=builder /install /usr/local
COPY scripts/loop.sh /app/bin/loop
COPY scripts/restart.sh /app/bin/restart
COPY scripts/force-restart.sh /app/bin/force-restart
COPY miso /app/miso
WORKDIR /app

ENV PATH="/app/bin:$PATH"
CMD ["python", "--version"]
