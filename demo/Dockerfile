FROM docker.io/python:3.12-slim

WORKDIR /work

RUN pip install --no-cache-dir influxdb-client pandas numpy scipy

ENTRYPOINT ["/work/entrypoint.sh"]