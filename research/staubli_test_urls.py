"""Quick test to verify all Stäubli image URL mappings are clean."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from staubli_fix_images_final import resolve_image

tests = [
    ("TX2-90XL HE", "TX2-90XL"),
    ("TX2-60L HE", "TX2-60L"),
    ("TX2-60L MedX Ready", "TX2-60L"),
    ("TX2-200L HE", "TX2-200L"),
    ("TX2-160L HE", "TX2-160L"),
    ("PF3", "PF3"),
    ("TP80 FAST Picker", "TP80"),
    ("RX160", "RX160"),
    ("Staubli TS2-40", "TS2-40"),
    ("Staubli TX2-40", "TX2-40"),
    ("TX2-40", "TX2-40"),
    ("TX2-200", "TX2-200"),
]
all_ok = True
for name, model in tests:
    url = resolve_image(name, model)
    valid = url and url.startswith("https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--") and len(url) > 80
    status = "OK" if valid else "FAIL"
    if not valid:
        all_ok = False
    print(f"[{status}] {name}: {url}")

print()
print("All OK" if all_ok else "FAILURES DETECTED - do not run live")
