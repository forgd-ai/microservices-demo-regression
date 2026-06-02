"""Helpers for the recommendation service.

This module owns the orchestration around the FBT path — pulling the
user's cart history, scoring candidate products against the
co-occurrence map, resolving contributor names, and assembling the
response. Keeping it out of recommendation_server.py keeps the gRPC
surface thin and makes the scoring path easier to evolve.

Cart history is weighted below the current cart so a shopper's older
interest nudges results without dominating what's in the cart now.
"""

import grpc

import demo_pb2
from fbt_data import COOCCURRENCE


def compute_for_user(request, cart_service_stub, product_catalog_stub, logger):
    """Build an FBTResponse for the requesting user.

    Fetches recent cart history via cartservice (when available), runs
    the scoring pipeline, resolves contributor names from the product
    catalog, and returns a populated FBTResponse.
    """
    max_results = request.max_results if request.max_results > 0 else 4
    cart_ids = list(request.product_ids)

    history_ids = _fetch_history(cart_service_stub, request.user_id, cart_ids, logger)

    seeds = [(pid, 1.0) for pid in cart_ids] + [(pid, 0.3) for pid in history_ids]
    ranked, counts, top_contributor = _score_candidates(seeds, cart_ids, max_results)
    names = _resolve_names(product_catalog_stub, {top_contributor[pid] for pid, _ in ranked})

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


def _fetch_history(cart_service_stub, user_id, cart_ids, logger):
    """Pull recent cart history for the user, filtered against the
    current cart so a recently-added item doesn't double-count."""
    if not user_id or cart_service_stub is None:
        return []
    try:
        history = cart_service_stub.GetCartHistory(
            demo_pb2.GetCartHistoryRequest(user_id=user_id, limit=20))
        return [pid for pid in history.product_ids if pid not in cart_ids]
    except grpc.RpcError as e:
        logger.warn("GetCartHistory failed, falling back to cart-only signal: {}".format(e))
        return []


def _score_candidates(seeds, cart_ids, max_results):
    """Aggregate weighted co-occurrence counts across seed items and
    return (ranked, counts, top_contributor)."""
    scores = {}
    counts = {}
    top_contributor = {}
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
    return ranked, counts, top_contributor


def _resolve_names(product_catalog_stub, ids):
    """Resolve product ids to display names via the catalog. On lookup
    failure, fall back to the id itself."""
    names = {}
    for pid in ids:
        try:
            p = product_catalog_stub.GetProduct(demo_pb2.GetProductRequest(id=pid))
            names[pid] = p.name
        except grpc.RpcError:
            names[pid] = pid
    return names
