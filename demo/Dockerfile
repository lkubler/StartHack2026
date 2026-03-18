FROM docker.io/python:3.12-slim

WORKDIR /work

RUN pip install --no-cache-dir influxdb-client altair pandas streamlit numpy scipy

# streamlit specific settings
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
EXPOSE 8501

ENTRYPOINT ["/work/entrypoint.sh"]