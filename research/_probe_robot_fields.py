#!/usr/bin/env python3
"""Probe robot API response to check company field shape."""
import sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
import json

client = ResearchApiClient()
data = client._get("robots/robots/", params={"company_ref": 1375, "page": 1, "page_size": 1})
r = data["results"][0]
print("Keys:", list(r.keys()))
print("company field type:", type(r.get("company")))
print("company field value:", repr(r.get("company")))
print("company_name:", repr(r.get("company_name")))
print("tags:", repr(r.get("tags")))
print("videos:", repr(r.get("videos")))
print("sub_category_slug:", repr(r.get("sub_category_slug")))
print("movement_type_keys:", repr(r.get("movement_type_keys")))
