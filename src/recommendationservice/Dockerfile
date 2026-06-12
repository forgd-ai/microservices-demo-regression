# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Define a default value so it's not empty if the builder fails to provide it
ARG BUILDPLATFORM=linux/amd64

FROM --platform=$BUILDPLATFORM public.ecr.aws/z8z1z1j0/workshop-base-images:python_3.14.4-alpine AS base

FROM base AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# apk fetches over HTTP so TLS-intercepting proxies don't break index
# downloads; package signatures are still verified
RUN sed -i 's/^https/http/' /etc/apk/repositories \
    && apk update \
    && apk add --no-cache g++ linux-headers \
    && rm -rf /var/cache/apk/*

# get packages
COPY requirements.txt .
# --trusted-host disables TLS certificate verification for the pypi
# hosts so TLS-intercepting proxies don't break package downloads
RUN pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

FROM base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN sed -i 's/^https/http/' /etc/apk/repositories \
    && apk update \
    && apk add --no-cache libstdc++ \
    && rm -rf /var/cache/apk/*

# get packages
WORKDIR /recommendationservice

# Grab packages from builder
COPY --from=builder /usr/local/lib/python3.14/ /usr/local/lib/python3.14/

# Add the application
COPY . .

# set listen port
ENV PORT="8080"
EXPOSE 8080

ENTRYPOINT ["python", "recommendation_server.py"]
