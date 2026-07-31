"""Publish DNS-AID (DNS for AI Discovery) records for robotaigeek.com on Cloudflare.

Creates ServiceMode SVCB records under the _agents namespace advertising the
production MCP endpoint (mcp-prod.robotaigeek.com), per
draft-mozleywilliams-dnsop-dnsaid / RFC 9460:

    _index._agents.robotaigeek.com      SVCB 1 mcp-prod.robotaigeek.com. alpn=h2 port=443
    _mcp._agents.robotaigeek.com        SVCB 1 mcp-prod.robotaigeek.com. alpn=h2 port=443
    _index._agents.www.robotaigeek.com  SVCB 1 mcp-prod.robotaigeek.com. alpn=h2 port=443
    _mcp._agents.www.robotaigeek.com    SVCB 1 mcp-prod.robotaigeek.com. alpn=h2 port=443

No _a2a record is published: we run an MCP server, not an A2A server.

Usage:
    export CLOUDFLARE_API_TOKEN=...   # needs Zone.DNS:Edit (+ Zone.DNSSEC:Edit for --enable-dnssec)
    python publish_dnsaid.py [--dry-run] [--enable-dnssec]

--enable-dnssec activates DNSSEC on the Cloudflare zone and prints the DS
record that must then be pasted into GoDaddy (Domain Settings > DNSSEC) —
that registrar step cannot be automated from here.

Idempotent: existing records with the same name/type are updated in place.
"""

import argparse
import json
import os
import sys
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ZONE_NAME = "robotaigeek.com"
TARGET = "mcp-prod.robotaigeek.com."
SVCB_VALUE = 'alpn="h2" port="443"'
TTL = 3600

RECORD_NAMES = [
    "_index._agents.robotaigeek.com",
    "_mcp._agents.robotaigeek.com",
    "_index._agents.www.robotaigeek.com",
    "_mcp._agents.www.robotaigeek.com",
]


def cf(method, path, token, body=None):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        out = json.load(resp)
    if not out.get("success"):
        raise RuntimeError(f"{method} {path} failed: {out.get('errors')}")
    return out["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--enable-dnssec", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("CLOUDFLARE_API_TOKEN is not set")

    # A token with only Zone.DNS:Edit cannot list zones; allow passing the
    # zone ID directly (Cloudflare dashboard > robotaigeek.com > Overview).
    zone_id = os.environ.get("CLOUDFLARE_ZONE_ID")
    if not zone_id:
        zones = cf("GET", f"/zones?name={ZONE_NAME}", token)
        if not zones:
            sys.exit(
                f"Zone {ZONE_NAME} not visible to this token. Either add "
                "Zone:Read to the token or set CLOUDFLARE_ZONE_ID."
            )
        zone_id = zones[0]["id"]
    print(f"Zone {ZONE_NAME} = {zone_id}")

    for name in RECORD_NAMES:
        existing = cf("GET", f"/zones/{zone_id}/dns_records?type=SVCB&name={name}", token)
        payload = {
            "type": "SVCB",
            "name": name,
            "ttl": TTL,
            "data": {"priority": 1, "target": TARGET, "value": SVCB_VALUE},
        }
        if args.dry_run:
            print(f"[dry-run] {'update' if existing else 'create'} {name} SVCB 1 {TARGET} {SVCB_VALUE}")
            continue
        if existing:
            cf("PUT", f"/zones/{zone_id}/dns_records/{existing[0]['id']}", token, payload)
            print(f"updated {name}")
        else:
            cf("POST", f"/zones/{zone_id}/dns_records", token, payload)
            print(f"created {name}")

    if args.enable_dnssec:
        if args.dry_run:
            print("[dry-run] would enable DNSSEC on the zone")
        else:
            ds = cf("PATCH", f"/zones/{zone_id}/dnssec", token, {"status": "active"})
            print("\nDNSSEC enabled on Cloudflare. Add this DS record at GoDaddy")
            print("(Domain Settings > DNSSEC) to complete the chain of trust:")
            for k in ("ds", "digest", "digest_type", "algorithm", "key_tag", "public_key"):
                if ds.get(k) is not None:
                    print(f"  {k}: {ds[k]}")

    print("\nVerify once TTLs settle:")
    print('  curl -s -H "accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=_index._agents.robotaigeek.com&type=SVCB"')
    print('  curl -s -X POST https://isitagentready.com/api/scan -H "Content-Type: application/json" -d \'{"url":"https://www.robotaigeek.com"}\'')


if __name__ == "__main__":
    main()
