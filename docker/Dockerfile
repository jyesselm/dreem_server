FROM ubuntu:20.04

RUN apt-get update
RUN mkdir /dreem_server
ADD . /dreem_server
WORKDIR /dreem_server
RUN pip install -r requirements.txt
RUN python run_server.py
