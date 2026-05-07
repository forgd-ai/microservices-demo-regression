# Seed co-occurrence data for "frequently bought together" recommendations.
#
# The map is keyed by product_id. Each value is a list of (paired_product_id,
# cooccurrence_count) tuples, sorted by count descending. Counts are notional
# basket co-occurrences from a synthetic transaction history. Pairs are
# symmetric: if A lists B with count N, B lists A with count N.

COOCCURRENCE = {
    "OLJCESPC7Z": [("66VCHSJNUP", 24), ("1YMWWN1N4O", 18), ("L9ECAV7KIM", 12)],
    "66VCHSJNUP": [("OLJCESPC7Z", 24), ("L9ECAV7KIM", 15), ("2ZYFJ3GM2N", 8)],
    "1YMWWN1N4O": [("L9ECAV7KIM", 22), ("OLJCESPC7Z", 18), ("66VCHSJNUP", 11)],
    "L9ECAV7KIM": [("1YMWWN1N4O", 22), ("66VCHSJNUP", 15), ("OLJCESPC7Z", 12)],
    "2ZYFJ3GM2N": [("0PUK6V6EV0", 14), ("LS4PSXUNUM", 10), ("66VCHSJNUP", 8)],
    "0PUK6V6EV0": [("LS4PSXUNUM", 28), ("9SIQT8TOJO", 19), ("2ZYFJ3GM2N", 14)],
    "LS4PSXUNUM": [("0PUK6V6EV0", 28), ("6E92ZMYYFZ", 21), ("9SIQT8TOJO", 16)],
    "9SIQT8TOJO": [("0PUK6V6EV0", 19), ("LS4PSXUNUM", 16), ("6E92ZMYYFZ", 13)],
    "6E92ZMYYFZ": [("LS4PSXUNUM", 21), ("9SIQT8TOJO", 13), ("0PUK6V6EV0", 9)],
}
