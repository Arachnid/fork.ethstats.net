FROM tiangolo/uwsgi-nginx-flask:flask

COPY ./app /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
