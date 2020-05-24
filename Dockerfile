FROM python:3.8.3-alpine3.10

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY main.py ./

CMD python main.py