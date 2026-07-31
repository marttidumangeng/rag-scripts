# DNS-AID (DNS for AI Discovery) — Publication Runbook

Goal: make `isitagentready.com` report `checks.discoverability.dnsAid.status = "pass"`
by publishing agent-discovery SVCB records under `_agents.robotaigeek.com` and
signing the zone with DNSSEC.

Spec: draft-mozleywilliams-dnsop-dnsaid + RFC 9460 (SVCB/HTTPS records).

## Current state (verified 2026-07-29)

- DNS hosted on **Cloudflare** (melody/valentin.ns.cloudflare.com); registrar is **GoDaddy**.
- No `_agents` records exist (scanner probes `_index`/`_a2a`/`_mcp` × SVCB/HTTPS/TXT on both apex and www — all NXDOMAIN).
- **DNSSEC not enabled** — no DS record at the registrar (`rdap.org` shows `delegationSigned: false`).
- The only real public agent endpoint is the production MCP server:
  `https://mcp-prod.robotaigeek.com/mcp` (GKE ingress `robotaigeek-mcp-prod-ingress`,
  static IP 34.117.19.78, managed cert Active, returns 401 without `X-API-Key` — alive).
- `mcp.robotaigeek.com` (mentioned in `robotaigeek-server/mcp/README.md`) has **no DNS record**; the deployed host is `mcp-prod`.
- `/.well-known/agent-card.json` etc. on www return the Nuxt SPA shell with a fake 200 (see follow-ups).

## Records to create (Cloudflare > robotaigeek.com > DNS)

Four SVCB records, all identical except the name. No `_a2a` record — we run MCP, not A2A.

| Field | Value |
|---|---|
| Type | SVCB |
| Name | `_index._agents` / `_mcp._agents` / `_index._agents.www` / `_mcp._agents.www` |
| Priority | `1` (ServiceMode) |
| Target | `mcp-prod.robotaigeek.com.` |
| Value | `alpn="h2" port="443"` |
| TTL | 1 hour |
| Proxy | DNS only (grey cloud — SVCB records cannot be proxied) |

Zone-file form:

```
_index._agents.robotaigeek.com.     3600 IN SVCB 1 mcp-prod.robotaigeek.com. alpn="h2" port="443"
_mcp._agents.robotaigeek.com.       3600 IN SVCB 1 mcp-prod.robotaigeek.com. alpn="h2" port="443"
_index._agents.www.robotaigeek.com. 3600 IN SVCB 1 mcp-prod.robotaigeek.com. alpn="h2" port="443"
_mcp._agents.www.robotaigeek.com.   3600 IN SVCB 1 mcp-prod.robotaigeek.com. alpn="h2" port="443"
```

Or run the script (idempotent, dry-run supported) with an API token that has
Zone.DNS:Edit on robotaigeek.com:

```bash
export CLOUDFLARE_API_TOKEN=...
python scripts/dns/publish_dnsaid.py --dry-run   # preview
python scripts/dns/publish_dnsaid.py             # apply
```

## DNSSEC (two halves — both required)

1. **Cloudflare**: DNS > Settings > DNSSEC > Enable. (Or `publish_dnsaid.py --enable-dnssec`,
   which also prints the DS record; token additionally needs Zone.DNSSEC:Edit.)
2. **GoDaddy**: Domain Settings > DNSSEC > add the DS record Cloudflare shows
   (Key Tag, Algorithm 13, Digest Type 2, Digest). Cloudflare shows "Success"
   on the DNSSEC card once the delegation is signed (can take up to 24 h).

## Verification

```bash
curl -s -H "accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=_index._agents.robotaigeek.com&type=SVCB"
```
Expect an Answer with type 64; after DNSSEC propagates, `"AD": true`.

```bash
curl -s -X POST https://isitagentready.com/api/scan -H "Content-Type: application/json" -d '{"url":"https://www.robotaigeek.com"}'
```
Expect `checks.discoverability.dnsAid.status: "pass"` (with `dnssecValidated: true` once the DS record lands).

## Follow-ups (not needed for the DNS check)

- Serve a real `/.well-known/agent-card.json` from the Nuxt app instead of the
  SPA catch-all's fake 200, then add `well-known="agent-card.json"` (or the
  draft's keyNNNNN form) to the SVCB values if the scanner starts requiring an
  endpoint SvcParam.
- Decide whether `mcp.robotaigeek.com` should exist as a CNAME to
  `mcp-prod.robotaigeek.com` to match the MCP README.
