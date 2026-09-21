#!/usr/bin/env python3
"""Count all raw requests by source UID and numeric endpoint, not case labels.

This checks the six-request bound, not traffic success or full R4 coverage.
Invoke once per version, including every raw traffic file for that version.
"""
import argparse
import collections
import ipaddress
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-pairs', type=int, required=True)
parser.add_argument('files', nargs='+', type=Path)
args = parser.parse_args()
assert args.expected_pairs > 0
counts = collections.Counter()
nonces = set()
requests = 0
for path in args.files:
    rows = json.loads(path.read_text())
    assert isinstance(rows, list), path
    for row in rows:
        source = row['source']
        uid = source['uid'] if isinstance(source, dict) else row['source_uid']
        assert uid, 'missing source UID'
        url = urlsplit(row['command'][-1])
        assert url.scheme == 'http', url.scheme
        address = str(ipaddress.ip_address(url.hostname))
        assert parse_qs(url.query) == {'nonce': [row['nonce']]}, url.query
        pair = (uid, address, url.port or 80)
        nonce_key = (*pair, row['nonce'])
        assert nonce_key not in nonces, 'repeated nonce for the same physical pair'
        nonces.add(nonce_key)
        counts[pair] += 1
        requests += 1
bad = [{'source_uid': uid, 'address': host, 'port': port, 'requests': count}
       for (uid, host, port), count in sorted(counts.items()) if count != 6]
passed = len(counts) == args.expected_pairs and not bad
print(json.dumps({'result': 'pass' if passed else 'fail', 'requests': requests,
                  'physical_pairs': len(counts), 'expected_pairs': args.expected_pairs,
                  'requests_per_pair': 6, 'incorrect_counts': bad,
                  'traffic_success_checked': False}, indent=2))
raise SystemExit(0 if passed else 1)
