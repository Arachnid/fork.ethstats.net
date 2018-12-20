FROM jfloff/alpine-python:3.6-onbuild
COPY ./app /app
EXPOSE 5000

CMD ["python","./app/main.py"]


