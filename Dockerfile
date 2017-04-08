FROM debian:stretch-slim

RUN apt-get update --fix-missing -qq
RUN apt-get install -y -qq bubblewrap
RUN apt-get install -y -qq python3.5
RUN apt-get install -y -qq python3-pip
RUN apt-get install -y -qq ostree
RUN apt-get install -y -qq gir1.2-ostree-1.0
RUN apt-get install -y -qq python3-dev
RUN apt-get install -y -qq python3-gi
RUN apt-get install -y -qq git

# Install BuildStream
ADD . /buildstream
RUN pip3 install /buildstream
RUN rm -rf /buildstream

# Use locales that exist, otherwise build-stream will not run
ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
