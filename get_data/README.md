docker build -t get_data .
docker run --rm -it -p 8501:8501 -v ${PWD}:/work get_data
