#!/usr/bin/env python3
"""
Check API endpoints and print a short report.
Usage:
  python scripts/check_endpoints.py [BASE_URL]
Default BASE_URL: http://127.0.0.1:8000
This script will test some key endpoints used by the frontend and Playwright E2E tests.
"""
import sys
import json
try:
    import requests
except ImportError:
    requests = None

ENDPOINTS = [
    '/api/v1/forums/categories/',
    '/api/v1/forums/forums/',
    '/api/v1/forums/topics/',
    '/api/v1/forums/posts/',
    '/api/v1/users/',
]

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'


def _http_get_using_urllib(url):
    # lightweight fallback to urllib when requests isn't installed
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            status = resp.getcode()
            body = resp.read()
            ct = resp.getheader('Content-Type')
            return status, body, ct, None
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b''
        return e.code, body, e.headers.get('Content-Type'), None
    except Exception as e:
        return None, None, None, str(e)


def _http_get(url):
    if requests:
        try:
            r = requests.get(url, timeout=5)
            return r.status_code, r.content, r.headers.get('Content-Type'), None
        except Exception as e:
            return None, None, None, str(e)
    else:
        return _http_get_using_urllib(url)


def try_parse_json(b):
    if not b:
        return None
    try:
        return json.loads(b)
    except Exception:
        return None


def check_endpoint(base_url, path):
    url = base_url.rstrip('/') + path
    status, body, content_type, err = _http_get(url)
    report = {
        'url': url,
        'status': status,
        'content_type': content_type,
        'length': len(body) if body else 0,
        'error': err,
    }
    if body and (content_type and 'application/json' in content_type.lower()):
        parsed = try_parse_json(body)
        if parsed is not None:
            report['json_keys'] = list(parsed.keys()) if isinstance(parsed, dict) else ['<list>']
            if isinstance(parsed, dict) and 'results' in parsed:
                try:
                    report['results_count'] = len(parsed['results'])
                except Exception:
                    report['results_count'] = None
    return report


def main():
    print(f"Using base url: {BASE_URL}")
    for p in ENDPOINTS:
        r = check_endpoint(BASE_URL, p)
        print('\n---')
        print(r['url'])
        if r['error']:
            print('ERROR:', r['error'])
            continue
        print('Status:', r['status'])
        print('Content-Type:', r['content_type'])
        print('Length:', r['length'])
        if 'json_keys' in r:
            print('JSON keys:', r['json_keys'])
        if 'results_count' in r:
            print('Results count:', r['results_count'])


if __name__ == '__main__':
    main()
