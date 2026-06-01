#!/usr/bin/env python3
"""GraphRAG 检索测试 —— 覆盖多种查询场景与边界情况。"""
import json
import logging
import sys
import time

from hybrid_retriever import HybridGraphRAG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

TEST_CASES = [
    {
        "name": "考场卡顿 — AP 负载排查",
        "query": "302考场考试系统卡顿，是不是AP负载太高导致的？",
        "device_id": "AP-EXAM-302",
    },
    {
        "name": "考场无法访问 — 服务依赖链",
        "query": "401考场考生登录失败，考试系统无法访问，可能是什么原因？",
        "device_id": "AP-EXAM-303",
    },
    {
        "name": "核心交换机 — 全网影响",
        "query": "核心交换机CPU利用率异常，会影响哪些业务？",
        "device_id": "OF-CORE-01",
    },
    {
        "name": "防火墙 — 安全策略",
        "query": "防火墙是否有异常流量拦截，是否影响考试服务器？",
        "device_id": "SRV-GATEWAY-01",
    },
    {
        "name": "数据库 — 后端依赖",
        "query": "数据库连接池满了，对考试系统有什么影响？",
        "device_id": "SRV-AUTH-01",
    },
    {
        "name": "冗余设备 — 故障切换",
        "query": "OF-CORE-01如果故障，SW-DC-01能接管吗？",
        "device_id": "OF-CORE-01",
    },
    {
        "name": "不存在的设备 — 边界测试",
        "query": "XY-999设备出现故障了",
        "device_id": "XY-999",
    },
]


def run_test(retriever, case):
    logging.info("============================================================")
    logging.info("测试: %s", case["name"])
    logging.info("  query: %s", case["query"])
    logging.info("  device_id: %s", case["device_id"])
    start = time.perf_counter()
    result = retriever.hybrid_search(case["query"], case["device_id"])
    elapsed = time.perf_counter() - start
    tc = len(result.get("topology_chain", []))
    sh = len(result.get("semantic_hits", []))
    fo = len(result.get("filtered_out", []))
    total = tc + sh
    logging.info("  耗时: %.2fs", elapsed)
    logging.info("  证据: %d (拓扑%d + 语义%d)", total, tc, sh)
    logging.info("  过滤: %d", fo)
    logging.info("  摘要: %s", result.get("evidence_snapshot", "")[:120])
    return result

def run_all_tests(retriever):
    results = []
    for case in TEST_CASES:
        try:
            r = run_test(retriever, case)
            results.append({"case": case["name"], "evidence_count": len(r.get("topology_chain",[]))+len(r.get("semantic_hits",[]))})
        except Exception as e:
            logging.error("测试失败: %s — %s", case["name"], e)
            results.append({"case": case["name"], "evidence_count": None, "error": str(e)})
    return results


def print_summary(results):
    logging.info("=" * 60)
    logging.info("测试汇总:")
    for r in results:
        status = f'{r["evidence_count"]} 条' if r["evidence_count"] is not None else f'ERROR: {r.get("error")}'
        logging.info("  %s → %s", r["case"], status)
    print("\n" + json.dumps(results, ensure_ascii=False, indent=2))


def main():
    logging.info("🚀 GraphRAG 综合测试启动")
    logging.info("加载模型及连接（仅此一次）...")
    retriever = HybridGraphRAG()
    logging.info("模型就绪，可反复查询。输入查询或 'run' 运行全部测试，'quit' 退出。")

    while True:
        try:
            cmd = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue
        if cmd.lower() in ("quit", "exit", "q"):
            break
        if cmd.lower() == "run":
            results = run_all_tests(retriever)
            print_summary(results)
            continue

        # 自定义查询: query | device_id
        parts = cmd.split("|", 1)
        query = parts[0].strip()
        device_id = parts[1].strip() if len(parts) > 1 else "AP-EXAM-302"
        case = {"name": "自定义查询", "query": query, "device_id": device_id}
        run_test(retriever, case)


if __name__ == "__main__":
    main()