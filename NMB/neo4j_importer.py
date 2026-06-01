#!/usr/bin/env python3
"""Neo4j 拓扑数据导入 —— 支持 topology_seed 格式。"""
import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv()
NEO4J_URI  = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PWD  = os.getenv("NEO4J_PWD",  "password")
BATCH_SIZE = 500


def parse_json(path):
    """解析新格式 topology_seed.json。
    返回 (devices, areas, links) 三元组。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    raw_devices = data.get("devices", [])
    raw_areas   = data.get("areas", [])
    raw_links   = data.get("links", [])

    # 设备 → {label: type, props: {name: device_id, ...所有字段}}
    devices = []
    for d in raw_devices:
        props = dict(d)
        did = props.pop("device_id", "")
        if not did:
            continue
        # 保留中文名作为 display_name，device_id 作为主 name
        display_name = props.pop("name", did)
        devices.append({
            "label": props.pop("type", "Device"),
            "props": {"name": did, "display_name": display_name, **props},
        })

    # 区域 → {label: "Area", props: {name: area_id, ...}}
    areas = []
    for a in raw_areas:
        props = dict(a)
        aid = props.pop("area_id", "")
        if not aid:
            continue
        display_name = props.pop("name", aid)
        areas.append({
            "label": "Area",
            "props": {"name": aid, "display_name": display_name, **props},
        })

    # 链路 → {from_label, from_name, to_label, to_name, rel_type, extra_props}
    links = []
    for l in raw_links:
        src = l.get("source", "")
        tgt = l.get("target", "")
        rel = l.get("relation", "CONNECTED_TO")
        if not src or not tgt:
            continue
        extra = {}
        for k in ("bandwidth_mbps", "latency_ms", "port_src", "port_tgt"):
            if k in l:
                extra[k] = l[k]
        links.append({
            "from_name": src,
            "to_name": tgt,
            "rel_type": rel,
            "extra": extra,
        })

    logging.info("解析: %d 设备 + %d 区域 + %d 链路", len(devices), len(areas), len(links))
    return devices, areas, links


def write_nodes(driver, nodes):
    """批量写入节点（优先 APOC，失败回退逐条）。"""
    if not nodes:
        return
    try:
        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i:i + BATCH_SIZE]
            with driver.session() as session:
                session.run(
                    "UNWIND $batch AS row "
                    "CALL apoc.merge.node([row.label], row.props) YIELD node "
                    "RETURN count(*) AS c",
                    batch=batch,
                )
            logging.info("写入进度: %d / %d", min(i + BATCH_SIZE, len(nodes)), len(nodes))
        logging.info("节点写入完成，共 %d 个", len(nodes))
    except Exception:
        logging.warning("APOC 不可用，逐条写入")
        _write_nodes_fallback(driver, nodes)


def _write_nodes_fallback(driver, nodes):
    for i in range(0, len(nodes), BATCH_SIZE):
        batch = nodes[i:i + BATCH_SIZE]
        with driver.session() as session:
            for node in batch:
                props = node["props"]
                if not props or "name" not in props:
                    continue
                flat = {}
                for k, v in props.items():
                    if isinstance(v, (str, int, float, bool, type(None))):
                        flat[k] = v
                session.run(
                    "MERGE (n:%s {name: $name}) SET n += $props" % node["label"],
                    name=props["name"],
                    props=flat,
                )
        logging.info("写入进度: %d / %d (fallback)", min(i + BATCH_SIZE, len(nodes)), len(nodes))
    logging.info("节点写入完成(fallback)，共 %d 个", len(nodes))


def write_links(driver, links):
    """写入关系：通过 name 匹配节点，创建关系并附带属性。"""
    if not links:
        return
    total = 0
    for i in range(0, len(links), BATCH_SIZE):
        batch = links[i:i + BATCH_SIZE]
        with driver.session() as session:
            for link in batch:
                try:
                    if link["extra"]:
                        session.run(
                            "MATCH (a {name: $from_name}) "
                            "MATCH (b {name: $to_name}) "
                            "MERGE (a)-[r:%s]->(b) "
                            "SET r += $extra" % link["rel_type"],
                            from_name=link["from_name"],
                            to_name=link["to_name"],
                            extra=link["extra"],
                        )
                    else:
                        session.run(
                            "MATCH (a {name: $from_name}) "
                            "MATCH (b {name: $to_name}) "
                            "MERGE (a)-[r:%s]->(b)" % link["rel_type"],
                            from_name=link["from_name"],
                            to_name=link["to_name"],
                        )
                except Exception as e:
                    logging.warning("关系写入失败 %s->%s: %s", link["from_name"], link["to_name"], e)
            total += len(batch)
        logging.info("关系进度: %d / %d", min(total, len(links)), len(links))
    logging.info("关系写入完成，共 %d 条", len(links))


def main():
    parser = argparse.ArgumentParser(description="Neo4j 拓扑数据导入")
    parser.add_argument("json_file", help="拓扑 JSON 文件路径")
    parser.add_argument("--clear", action="store_true", help="导入前清空数据库")
    args = parser.parse_args()

    devices, areas, links = parse_json(args.json_file)
    all_nodes = devices + areas

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
    try:
        driver.verify_connectivity()
        logging.info("Neo4j 连接成功 (%s)", NEO4J_URI)
    except Exception as e:
        logging.error("无法连接 Neo4j: %s", e)
        sys.exit(1)

    if args.clear:
        logging.info("正在清空数据库...")
        with driver.session() as session:
            result = session.run("MATCH (n) DETACH DELETE n RETURN count(n) AS deleted")
            deleted = result.single()["deleted"]
            logging.info("已删除 %d 个节点（含关系）", deleted)

    write_nodes(driver, all_nodes)
    write_links(driver, links)

    driver.close()
    logging.info("导入完成！")
    logging.info("总计: %d 设备节点, %d 区域节点, %d 条关系", len(devices), len(areas), len(links))


if __name__ == "__main__":
    main()
