#!/bin/sh
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

# Generate a base sysroot for running the BuildStream integration tests.
#
# The sysroot is based off the Debian Linux distribution.

set -eux

DOCKER_ARCH=${DOCKER_ARCH:-amd64}

export DOCKER_DEFAULT_PLATFORM="linux/%{DOCKER_ARCH}"

IMAGE_NAME="integration-tests-debian-base"

docker build --tag ${IMAGE_NAME} -f - << "EOF"
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev make autoconf automake && \
    rm -rf /var/lib/apt/lists/*
EOF

CONTAINER_NAME="$(docker create ${IMAGE_NAME})"

docker export "${CONTAINER_NAME}" | xz > ${IMAGE_NAME}.tar.xz

docker rm "${CONTAINER_NAME}"
