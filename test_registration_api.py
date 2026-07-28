#!/usr/bin/env python
"""
Manual API test for registration endpoint.
Run from the project root with: python scripts/test_registration_api.py
"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"
REGISTRATION_URL = f"{BASE_URL}/api/v1/auth/registration/"

# Generate a unique test user
timestamp = int(time.time() * 1000000) % 1000000
test_username = f"testuser_{timestamp}"
test_email = f"{test_username}@test.robotaigeek.com"
test_password = "TestPassword123!"

print("\n" + "=" * 80)
print("REGISTRATION API TEST")
print("=" * 80)

print(f"\nTest User Details:")
print(f"  Username: {test_username}")
print(f"  Email: {test_email}")
print(f"  Password: {test_password}")

payload = {
    'username': test_username,
    'email': test_email,
    'password1': test_password,
    'password2': test_password,
}

print(f"\n[1] Sending registration request to {REGISTRATION_URL}")
try:
    response = requests.post(REGISTRATION_URL, json=payload)
    
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Headers:\n  {json.dumps(dict(response.headers), indent=2)}")
    
    try:
        response_data = response.json()
        print(f"\nResponse Body:")
        print(json.dumps(response_data, indent=2))
    except:
        print(f"\nResponse Body (raw):")
        print(response.text)
    
    if response.status_code in [200, 201]:
        print(f"\n✅ Registration successful!")
        print(f"\n[2] Check server logs for email sending confirmation")
        print(f"    Look for: '[REGISTRATION] ✅ Verification email sent successfully'")
    else:
        print(f"\n❌ Registration failed with status {response.status_code}")

except requests.exceptions.ConnectionError:
    print(f"\n❌ Connection failed. Is the Django server running at {BASE_URL}?")
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {str(e)}")

print("\n" + "=" * 80)
