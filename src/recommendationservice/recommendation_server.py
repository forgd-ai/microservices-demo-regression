#!/usr/bin/python
#
# Copyright 2018 Google LLC
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

import os
import random
import time
import traceback
from concurrent import futures

# @TODO: Temporarily removed in https://github.com/GoogleCloudPlatform/microservices-demo/pull/3196
# import googlecloudprofiler

from google.auth.exceptions import DefaultCredentialsError
import grpc

import demo_pb2
import demo_pb2_grpc
from fbt_data import COOCCURRENCE
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from logger import getJSONLogger
logger = getJSONLogger('recommendationservice-server')

def initStackdriverProfiling():
  project_id = None
  try:
    project_id = os.environ["GCP_PROJECT_ID"]
  except KeyError:
    # Environment variable not set
    pass

  # @TODO: Temporarily removed in https://github.com/GoogleCloudPlatform/microservices-demo/pull/3196
  # for retry in range(1,4):
  #   try:
  #     if project_id:
  #       googlecloudprofiler.start(service='recommendation_server', service_version='1.0.0', verbose=0, project_id=project_id)
  #     else:
  #       googlecloudprofiler.start(service='recommendation_server', service_version='1.0.0', verbose=0)
  #     logger.info("Successfully started Stackdriver Profiler.")
  #     return
  #   except (BaseException) as exc:
  #     logger.info("Unable to start Stackdriver Profiler Python agent. " + str(exc))
  #     if (retry < 4):
  #       logger.info("Sleeping %d seconds to retry Stackdriver Profiler agent initialization"%(retry*10))
  #       time.sleep (1)
  #     else:
  #       logger.warning("Could not initialize Stackdriver Profiler after retrying, giving up")
  return

class RecommendationService(demo_pb2_grpc.RecommendationServiceServicer):
    def ListRecommendations(self, request, context):
        max_responses = 5
        # fetch list of products from product catalog stub
        cat_response = product_catalog_stub.ListProducts(demo_pb2.Empty())
        product_ids = [x.id for x in cat_response.products]
        filtered_products = list(set(product_ids)-set(request.product_ids))
        num_products = len(filtered_products)
        num_return = min(max_responses, num_products)
        # sample list of indicies to return
        indices = random.sample(range(num_products), num_return)
        # fetch product ids from indices
        prod_list = [filtered_products[i] for i in indices]
        logger.info("[Recv ListRecommendations] product_ids={}".format(prod_list))
        # build and return response
        response = demo_pb2.ListRecommendationsResponse()
        response.product_ids.extend(prod_list)
        return response

    def ListFrequentlyBoughtTogether(self, request, context):
        max_results = request.max_results if request.max_results > 0 else 4
        cart_ids = list(request.product_ids)

        # Pull recent cart history for this user, weighted lower than the
        # current cart since older interest is a weaker signal.
        history_ids = []
        if request.user_id and cart_service_stub is not None:
            try:
                history = cart_service_stub.GetCartHistory(
                    demo_pb2.GetCartHistoryRequest(user_id=request.user_id, limit=20))
                history_ids = [pid for pid in history.product_ids if pid not in cart_ids]
            except grpc.RpcError as e:
                logger.warn("GetCartHistory failed, falling back to cart-only signal: {}".format(e))

        seeds = [(pid, 1.0) for pid in cart_ids] + [(pid, 0.3) for pid in history_ids]

        # Aggregate scores per candidate product, plus the top contributing
        # seed item so we can produce a human-readable reason.
        scores = {}            # candidate_id -> aggregated score
        counts = {}            # candidate_id -> raw cooccurrence count for the top contributor
        top_contributor = {}   # candidate_id -> seed product_id that contributed most
        for seed_id, weight in seeds:
            for cand_id, count in COOCCURRENCE.get(seed_id, []):
                if cand_id in cart_ids:
                    continue
                score = count * weight
                scores[cand_id] = scores.get(cand_id, 0) + score
                if score > counts.get(cand_id, -1):
                    counts[cand_id] = count
                    top_contributor[cand_id] = seed_id

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:max_results]

        # Resolve product names once for the contributors that appear in the
        # response so we can include them in the reason text.
        contributor_ids = {top_contributor[pid] for pid, _ in ranked}
        names = {}
        for pid in contributor_ids:
            try:
                p = product_catalog_stub.GetProduct(demo_pb2.GetProductRequest(id=pid))
                names[pid] = p.name
            except grpc.RpcError:
                names[pid] = pid

        response = demo_pb2.FBTResponse()
        for cand_id, _ in ranked:
            contrib = top_contributor[cand_id]
            response.items.append(demo_pb2.FBTItem(
                product_id=cand_id,
                cooccurrence_count=counts[cand_id],
                reason="Often bought with {}".format(names.get(contrib, contrib)),
            ))
        logger.info("[Recv ListFrequentlyBoughtTogether] cart={} history_len={} returned={}".format(
            cart_ids, len(history_ids), [i.product_id for i in response.items]))
        return response

    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING)

    def Watch(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.UNIMPLEMENTED)


if __name__ == "__main__":
    logger.info("initializing recommendationservice")

    try:
      if "DISABLE_PROFILER" in os.environ:
        raise KeyError()
      else:
        logger.info("Profiler enabled.")
        initStackdriverProfiling()
    except KeyError:
        logger.info("Profiler disabled.")

    try:
      grpc_client_instrumentor = GrpcInstrumentorClient()
      grpc_client_instrumentor.instrument()
      grpc_server_instrumentor = GrpcInstrumentorServer()
      grpc_server_instrumentor.instrument()
      if os.environ["ENABLE_TRACING"] == "1":
        trace.set_tracer_provider(TracerProvider())
        otel_endpoint = os.getenv("COLLECTOR_SERVICE_ADDR", "localhost:4317")
        trace.get_tracer_provider().add_span_processor(
          BatchSpanProcessor(
              OTLPSpanExporter(
              endpoint = otel_endpoint,
              insecure = True
            )
          )
        )
    except (KeyError, DefaultCredentialsError):
        logger.info("Tracing disabled.")
    except Exception as e:
        logger.warn(f"Exception on Cloud Trace setup: {traceback.format_exc()}, tracing disabled.") 

    port = os.environ.get('PORT', "8080")
    catalog_addr = os.environ.get('PRODUCT_CATALOG_SERVICE_ADDR', '')
    if catalog_addr == "":
        raise Exception('PRODUCT_CATALOG_SERVICE_ADDR environment variable not set')
    logger.info("product catalog address: " + catalog_addr)
    channel = grpc.insecure_channel(catalog_addr)
    product_catalog_stub = demo_pb2_grpc.ProductCatalogServiceStub(channel)

    # CartService is optional: if unset, FBT falls back to current-cart-only signal.
    cart_addr = os.environ.get('CART_SERVICE_ADDR', '')
    cart_service_stub = None
    if cart_addr:
        logger.info("cart service address: " + cart_addr)
        cart_channel = grpc.insecure_channel(cart_addr)
        cart_service_stub = demo_pb2_grpc.CartServiceStub(cart_channel)
    else:
        logger.info("CART_SERVICE_ADDR not set; FBT will not use cart history")

    # create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # add class to gRPC server
    service = RecommendationService()
    demo_pb2_grpc.add_RecommendationServiceServicer_to_server(service, server)
    health_pb2_grpc.add_HealthServicer_to_server(service, server)

    # start server
    logger.info("listening on port: " + port)
    server.add_insecure_port('[::]:'+port)
    server.start()

    # keep alive
    try:
         while True:
            time.sleep(10000)
    except KeyboardInterrupt:
            server.stop(0)
