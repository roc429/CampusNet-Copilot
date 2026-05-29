"""
向netbox注入网络设备拓扑信息的脚本。
"""

import requests

NETBOX_URL = "http://localhost:8000"    #docker挂起的netbox实例地址(即netbox提供服务的地址)
NETBOX_TOKEN = "NC4xINsFLqPLKIwWQ2Syu6pRwaxOqK5u5ISmqrmD"

HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
}

def api_get(path, params=None):
    r = requests.get(f"{NETBOX_URL}{path}", headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def api_post(path, payload):
    r = requests.post(f"{NETBOX_URL}{path}", headers=HEADERS, json=payload, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"POST {path} failed: {r.status_code} {r.text}")
    return r.json()

def api_patch(path, payload):
    r = requests.patch(f"{NETBOX_URL}{path}", headers=HEADERS, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def get_or_create(endpoint, query, payload):
    data = api_get(endpoint, params=query)
    if data["count"] > 0:
        return data["results"][0]
    return api_post(endpoint, payload)

def main():
    # 1) Site + Location
    site = get_or_create(
        "/api/dcim/sites/",
        {"name": "图书馆"},
        {"name": "图书馆", "slug": "library"},
    )
    location = get_or_create(
        "/api/dcim/locations/",
        {"name": "图书馆三层", "site_id": site["id"]},
        {"name": "图书馆三层", "slug": "library-3f", "site": site["id"]},
    )

    # 2) Manufacturer + DeviceType + Role
    mfg = get_or_create(
        "/api/dcim/manufacturers/",
        {"name": "CampusLab"},
        {"name": "CampusLab", "slug": "campuslab"},
    )

    ap_type = get_or_create(
        "/api/dcim/device-types/",
        {"model": "Campus-AP"},
        {
            "manufacturer": mfg["id"],
            "model": "Campus-AP",
            "slug": "campus-ap",
        },
    )
    sw_type = get_or_create(
        "/api/dcim/device-types/",
        {"model": "Campus-SW"},
        {
            "manufacturer": mfg["id"],
            "model": "Campus-SW",
            "slug": "campus-sw",
        },
    )

    role_ap = get_or_create(
        "/api/dcim/device-roles/",
        {"name": "ap"},
        {"name": "ap", "slug": "ap", "color": "00bcd4"},
    )
    role_sw = get_or_create(
        "/api/dcim/device-roles/",
        {"name": "switch"},
        {"name": "switch", "slug": "switch", "color": "ff9800"},
    )

    # 3) Devices
    ap1 = get_or_create(
        "/api/dcim/devices/",
        {"name": "AP-LIB-3F-01"},
        {
            "name": "AP-LIB-3F-01",
            "site": site["id"],
            "location": location["id"],
            "device_type": ap_type["id"],
            "role": role_ap["id"],
            "status": "active",
        },
    )
    ap2 = get_or_create(
        "/api/dcim/devices/",
        {"name": "AP-LIB-3F-02"},
        {
            "name": "AP-LIB-3F-02",
            "site": site["id"],
            "location": location["id"],
            "device_type": ap_type["id"],
            "role": role_ap["id"],
            "status": "active",
        },
    )
    sw = get_or_create(
        "/api/dcim/devices/",
        {"name": "SW-LIB-AGG-01"},
        {
            "name": "SW-LIB-AGG-01",
            "site": site["id"],
            "location": location["id"],
            "device_type": sw_type["id"],
            "role": role_sw["id"],
            "status": "active",
        },
    )

    # 4) Interfaces
    ap1_if = get_or_create(
        "/api/dcim/interfaces/",
        {"device_id": ap1["id"], "name": "eth0"},
        {"device": ap1["id"], "name": "eth0", "type": "1000base-t"},
    )
    ap2_if = get_or_create(
        "/api/dcim/interfaces/",
        {"device_id": ap2["id"], "name": "eth0"},
        {"device": ap2["id"], "name": "eth0", "type": "1000base-t"},
    )
    sw_if_12 = get_or_create(
        "/api/dcim/interfaces/",
        {"device_id": sw["id"], "name": "GigabitEthernet1/0/12"},
        {"device": sw["id"], "name": "GigabitEthernet1/0/12", "type": "1000base-t"},
    )
    sw_if_13 = get_or_create(
        "/api/dcim/interfaces/",
        {"device_id": sw["id"], "name": "GigabitEthernet1/0/13"},
        {"device": sw["id"], "name": "GigabitEthernet1/0/13", "type": "1000base-t"},
    )

    # 5) Cables (uplink relation)
    # 注意：如果已连线，这里会报错，可忽略或先检查 connected endpoints
    try:
        api_post(
            "/api/dcim/cables/",
            {
                "a_terminations": [{"object_type": "dcim.interface", "object_id": ap1_if["id"]}],
                "b_terminations": [{"object_type": "dcim.interface", "object_id": sw_if_12["id"]}],
                "status": "connected",
            },
        )
    except Exception:
        pass

    try:
        api_post(
            "/api/dcim/cables/",
            {
                "a_terminations": [{"object_type": "dcim.interface", "object_id": ap2_if["id"]}],
                "b_terminations": [{"object_type": "dcim.interface", "object_id": sw_if_13["id"]}],
                "status": "connected",
            },
        )
    except Exception:
        pass

    # 6) Management IP + primary_ip4
    ip1 = get_or_create(
        "/api/ipam/ip-addresses/",
        {"address": "10.10.3.11/24"},
        {
            "address": "10.10.3.11/24",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": ap1_if["id"],
            "status": "active",
        },
    )
    ip2 = get_or_create(
        "/api/ipam/ip-addresses/",
        {"address": "10.10.3.12/24"},
        {
            "address": "10.10.3.12/24",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": ap2_if["id"],
            "status": "active",
        },
    )
    ip_sw = get_or_create(
        "/api/ipam/ip-addresses/",
        {"address": "10.10.3.254/24"},
        {
            "address": "10.10.3.254/24",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": sw_if_12["id"],
            "status": "active",
        },
    )

    api_patch(f"/api/dcim/devices/{ap1['id']}/", {"primary_ip4": ip1["id"]})
    api_patch(f"/api/dcim/devices/{ap2['id']}/", {"primary_ip4": ip2["id"]})
    api_patch(f"/api/dcim/devices/{sw['id']}/", {"primary_ip4": ip_sw["id"]})

    print("Import completed.")

if __name__ == "__main__":
    main()