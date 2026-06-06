#!/usr/bin/env python3
"""Import campus_topology.json into NetBox via REST API."""
import json, httpx

with open('NMB/campus_topology.json') as f:
    topo = json.load(f)

NETBOX_URL = "http://localhost:8008"
TOKEN = "32Y4JUdXmc1vOO5TY7gmDhLswqPoZyBBnaa4kAFR"

headers = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"}

def api(method, path, data=None):
    try:
        r = httpx.request(method, f"{NETBOX_URL}/api{path}", headers=headers, json=data, timeout=10)
        return r
    except Exception as e:
        print(f"  Connection error: {e}")
        raise

# 1. Create sites
print("=== Creating sites ===")
site_map = {}
for zone in topo["zones"]:
    r = api("POST", "/dcim/sites/", {"name": zone["zone_id"], "slug": zone["zone_id"].lower(), "status": "active"})
    if r.status_code in (200, 201):
        site_map[zone["zone_id"]] = r.json()["id"]
        print(f"  OK: {zone['zone_id']}")
    else:
        print(f"  FAIL {zone['zone_id']}: {r.status_code} {r.text[:80]}")

# 2. Device roles
print("\n=== Creating roles ===")
roles = {}
for name, slug in [("Access Point","ap"), ("Switch","switch"), ("Controller","controller"), ("Server","server"), ("Gateway","gateway")]:
    r = api("POST", "/dcim/device-roles/", {"name": name, "slug": slug, "color": "2196f3"})
    if r.status_code in (200, 201):
        roles[slug] = r.json()["id"]
        print(f"  OK: {name}")
    else:
        result = r.json() if r.text else {}
        # Check if already exists
        existing = api("GET", f"/dcim/device-roles/?slug={slug}")
        if existing.status_code == 200 and existing.json()["count"] > 0:
            roles[slug] = existing.json()["results"][0]["id"]
            print(f"  EXISTS: {name}")

# 3. Manufacturer
print("\n=== Creating manufacturer ===")
r = api("POST", "/dcim/manufacturers/", {"name": "CampusNet", "slug": "campusnet"})
if r.status_code in (200, 201):
    mfr_id = r.json()["id"]
else:
    existing = api("GET", "/dcim/manufacturers/?slug=campusnet")
    mfr_id = existing.json()["results"][0]["id"] if existing.json()["count"] > 0 else None
print(f"  mfr_id={mfr_id}")

# 4. Device types
print("\n=== Creating device types ===")
dtypes = {}
for model, slug in [("WiFi6 AP","wifi6-ap"), ("OpenvSwitch","openvswitch"), ("Ryu Controller","ryu-controller"), ("Linux Server","linux-server")]:
    r = api("POST", "/dcim/device-types/", {"manufacturer": mfr_id, "model": model, "slug": slug})
    if r.status_code in (200, 201):
        dtypes[slug] = r.json()["id"]
        print(f"  OK: {model}")
    else:
        existing = api("GET", f"/dcim/device-types/?slug={slug}")
        if existing.status_code == 200 and existing.json()["count"] > 0:
            dtypes[slug] = existing.json()["results"][0]["id"]
            print(f"  EXISTS: {model}")

# 5. Create devices
print(f"\n=== Creating {len(topo['devices'])} devices ===")
type_role = {
    "access_point": ("wifi6-ap", "ap"),
    "aggregation_switch": ("openvswitch", "switch"),
    "openflow_switch": ("openvswitch", "switch"),
    "controller": ("ryu-controller", "controller"),
    "application_server": ("linux-server", "server"),
    "gateway": ("linux-server", "gateway"),
}

count = 0
for dev in topo["devices"]:
    dt_key, role_key = type_role.get(dev["type"], ("openvswitch", "switch"))
    site_id = site_map.get(dev["zone_id"])
    if not site_id:
        print(f"  SKIP {dev['device_id']}: no site for {dev['zone_id']}")
        continue
    r = api("POST", "/dcim/devices/", {
        "name": dev["device_id"],
        "device_type": dtypes.get(dt_key),
        "role": roles.get(role_key),
        "site": site_id,
        "status": "active",
    })
    if r.status_code in (200, 201):
        count += 1
    else:
        # Check if already exists
        existing = api("GET", f"/dcim/devices/?name={dev['device_id']}")
        if existing.status_code == 200 and existing.json()["count"] > 0:
            count += 1
        else:
            print(f"  FAIL {dev['device_id']}: {r.status_code}")

print(f"\n=== Done: {count}/{len(topo['devices'])} devices ===")
