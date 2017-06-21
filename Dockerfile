# Docker image for running BuildStream
# ====================================
#
# This image has BuildStream and its dependencies installed in /usr.
# See Dockerfile-build.sh for the full build instructions.
#
# To build it, run this command from the current directory:
#
#     docker build --tag=buildstream:latest .
#
# The build takes a long time because it has to download lots of packages using
# DNF and also build OSTree from source.


FROM fedora:25

ADD Dockerfile-build.sh /root/Dockerfile-build.sh
RUN bash /root/Dockerfile-build.sh

# Work around https://github.com/fedora-cloud/docker-brew-fedora/issues/14
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
