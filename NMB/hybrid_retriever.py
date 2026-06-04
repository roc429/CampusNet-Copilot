import os
from dotenv import load_dotenv

load_dotenv()

import warnings
from FlagEmbedding import FlagModel, FlagReranker
from pymilvus import MilvusClient
from neo4j import GraphDatabase
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading

# ==========================================
# 0. 环境初始化配置
# ==========================================
warnings.filterwarnings('ignore', category=FutureWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-7s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# ==========================================
# 1. 资源管理器（单例模式 + 环境变量注入）
# ==========================================
class ResourceManager:
    _lock = threading.Lock()
    _embed_model = None
    _reranker = None
    _milvus_client = None
    _neo4j_driver = None

    @classmethod
    def get_embed_model(cls):
        if cls._embed_model is None:
            with cls._lock:
                if cls._embed_model is None:
                    logging.info('📦 首次加载 BGE-M3 嵌入模型到内存...')
                    cls._embed_model = FlagModel('BAAI/bge-m3', use_fp16=False)
        return cls._embed_model

    @classmethod
    def get_reranker(cls):
        if cls._reranker is None:
            with cls._lock:
                if cls._reranker is None:
                    logging.info('📦 首次加载 BGE-M3 重排序模型到内存...')
                    cls._reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=False)
        return cls._reranker

    @classmethod
    def get_milvus_client(cls):
        if cls._milvus_client is None:
            with cls._lock:
                if cls._milvus_client is None:
                    uri = os.getenv('MILVUS_URI', 'http://localhost:19530')
                    logging.info(f'🔌 首次建立 Milvus 连接 ({uri})...')
                    cls._milvus_client = MilvusClient(uri=uri)
        return cls._milvus_client

    @classmethod
    def get_neo4j_driver(cls):
        if cls._neo4j_driver is None:
            with cls._lock:
                if cls._neo4j_driver is None:
                    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
                    user = os.getenv('NEO4J_USER', 'neo4j')
                    pwd = os.getenv('NEO4J_PWD', 'password')
                    logging.info(f'🔌 首次建立 Neo4j 连接池 ({uri})...')
                    cls._neo4j_driver = GraphDatabase.driver(uri, auth=(user, pwd))
        return cls._neo4j_driver

# ==========================================
# 2. 混合检索核心业务逻辑
# ==========================================
class HybridGraphRAG:
    def __init__(self):
        self.embed_model = ResourceManager.get_embed_model()
        self.reranker = ResourceManager.get_reranker()
        self.milvus_client = ResourceManager.get_milvus_client()
        self.neo4j_driver = ResourceManager.get_neo4j_driver()
        self.collection_name = os.getenv('MILVUS_COLLECTION', 'test_knowledge')
        self.score_threshold = float(os.getenv('RERANK_THRESHOLD', '-2.0'))
        # 拓扑抗幻觉：设备名缓存 + 锁
        self._known_device_names = None
        self._known_names_lock = threading.Lock()

    def _load_device_names(self):
        """懒加载：从 Neo4j 拉取所有节点名称，缓存为 set。"""
        if self._known_device_names is None:
            with self._known_names_lock:
                if self._known_device_names is None:
                    logging.info('📋 从 Neo4j 加载设备名缓存...')
                    try:
                        with self.neo4j_driver.session() as session:
                            result = session.run('MATCH (n) RETURN DISTINCT n.name AS name')
                            names = {record['name'] for record in result if record['name']}
                        self._known_device_names = names
                        logging.info(f'📋 已缓存 {len(names)} 个设备/服务名')
                    except Exception as e:
                        logging.warning(f'加载设备名缓存失败: {e}，使用空集')
                        self._known_device_names = set()
        return self._known_device_names

    def extract_entities(self, text):
        """从文本中提取命中的设备/服务名（子串匹配）。"""
        names = self._load_device_names()
        matched = []
        # 按名称长度降序排列，优先匹配长名（避免 OF-CORE-01 被 SW 误匹配）
        for name in sorted(names, key=len, reverse=True):
            if name in text and name not in matched:
                matched.append(name)
        return matched

    def get_topology_neighborhood(self, device_id, max_hops=3):
        """查询以 device_id 为中心 max_hops 跳内的所有设备及其最短距离。
        返回 {device_name: min_hops} 字典；设备不存在或出错返回空 dict。"""
        logging.info(f'🔍 拓扑邻域查询: {device_id} (最大 {max_hops} 跳)')
        cypher = """
        MATCH (start {name: $device_id})
        MATCH path = shortestPath((start)-[*1..""" + str(max_hops) + """]-(n))
        WHERE n.name IS NOT NULL AND n.name <> $device_id
        WITH DISTINCT n.name AS name, length(path) AS hops
        RETURN name, hops
        ORDER BY hops
        """
        neighborhood = {}
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(cypher, device_id=device_id)
                for record in result:
                    name = record['name']
                    hops = record['hops']
                    if name not in neighborhood or hops < neighborhood[name]:
                        neighborhood[name] = hops
            logging.info(f'🔍 拓扑邻域命中 {len(neighborhood)} 个设备 (≤{max_hops}跳)')
        except Exception as e:
            logging.error(f'拓扑邻域查询出错: {e}')
        return neighborhood

    def _compute_topology_score(self, matched_devices, topology_neighborhood, device_id):
        """根据命中设备与目标设备的拓扑距离计算加权分数。
        取最有利命中（最近跳数），无命中返回 0，命中但不在邻域内返回 -0.3。"""
        if not matched_devices:
            return 0.0, None, []

        best_score = None
        best_hops = None
        best_device = None

        for dev in matched_devices:
            if dev == device_id:
                candidate_score = 0.4
                candidate_hops = 0
            elif dev in topology_neighborhood:
                hops = topology_neighborhood[dev]
                if hops <= 1:
                    candidate_score = 0.3
                elif hops <= 2:
                    candidate_score = 0.2
                elif hops <= 3:
                    candidate_score = 0.1
                else:
                    candidate_score = -0.3
                candidate_hops = hops
            else:
                # 是已知设备但不在 3 跳邻域内 → 罚分
                candidate_score = -0.3
                candidate_hops = 99

            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_hops = candidate_hops
                best_device = dev

        best_hops = 0 if best_device == device_id else best_hops
        return best_score, best_hops, matched_devices

    def _parse_topology_chain(self, content):
        import re
        m = re.search(r'(\S+)\s+--\[(\w+)\]-+>\s+\[\S+\]\s+(\S+)', content)
        if m:
            return {"source": m.group(1), "relation": m.group(2), "target": m.group(3)}
        return None

    def _build_snapshot(self, topology_chain, device_id):
        if not topology_chain:
            return "设备 " + device_id + " 未找到邻域拓扑链路。"
        parts = []
        for link in topology_chain:
            parts.append(link["source"] + " 通过 " + link["relation"] + " 关联到 " + link["target"])
        return "设备 " + device_id + " 的拓扑邻域：" + "；".join(parts) + "。"


    def retrieve_from_milvus(self, query, top_k=3):
        logging.info(f"Milvus 检索: 正在查找 '{query}' 相关的语义经验...")
        query_vector = self.embed_model.encode(query).tolist()
        try:
            results = self.milvus_client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                limit=top_k,
                output_fields=['text']
            )
            milvus_context = [hit['entity']['text'] for hits in results for hit in hits]
            logging.info(f'Milvus 命中 {len(milvus_context)} 条语义记录。')
            return [{"source": "milvus", "content": t} for t in milvus_context]
        except Exception as e:
            logging.error(f'Milvus 检索出错: {e}')
            return []

    def retrieve_from_neo4j(self, device_id):
        logging.info(f"Neo4j 检索: 正在查找设备 '{device_id}' 的多跳物理拓扑...")
        cypher_query = """
        MATCH (start {name: $device_id})-[r]-(connected_node)
        RETURN start.name AS Source, labels(start)[0] AS StartLabel,
               type(r) AS Relation,
               connected_node.name AS Target, labels(connected_node)[0] AS TargetLabel
        LIMIT 10
        """
        neo4j_context = []
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(cypher_query, device_id=device_id)
                for record in result:
                    src = record["Source"] or "(unnamed)"
                    sl  = record["StartLabel"] or ""
                    rel = record["Relation"] or ""
                    tgt = record["Target"] or "(unnamed)"
                    tl  = record["TargetLabel"] or ""
                    path_desc = f"拓扑路径: [{sl}] {src} --[{rel}]--> [{tl}] {tgt}"
                    neo4j_context.append({"source": "neo4j", "content": path_desc})
            logging.info(f'Neo4j 命中 {len(neo4j_context)} 条拓扑链路。')
            return neo4j_context
        except Exception as e:
            logging.error(f'Neo4j 检索出错: {e}')
            return []

    def rerank_and_filter(self, query, candidates, device_id=None):
        """重排序 + 可选拓扑约束抗幻觉过滤。
        若提供 device_id，会在 reranker 评分后叠加拓扑距离加权分。"""
        if device_id:
            logging.info('🔬 BGE-M3 重排序 + 拓扑约束抗幻觉验证...')
        else:
            logging.info('BGE-M3 重排序: 正在进行全局评估与幻觉过滤...')

        if not candidates:
            logging.warning('未检索到任何候选证据')
            return {"evidence": [], "context": "未检索到任何证据。"}

        # ── 第一轮：reranker 语义评分 ──
        contents = [c["content"] for c in candidates]
        scores = self.reranker.compute_score([[query, t] for t in contents])
        if isinstance(scores, float):
            scores = [scores]

        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        # ── 拓扑邻域查询（如有 device_id）──
        topology_neighborhood = {}
        if device_id:
            topology_neighborhood = self.get_topology_neighborhood(device_id, max_hops=3)

        # ── 第二轮：拓扑加权 ──
        evidence = []
        context_parts = []
        idx = 0
        for candidate, rerank_score in scored:
            is_kept = rerank_score > self.score_threshold
            logging.debug(f'评估链路: {candidate["content"]}')
            kept_label = '✓ 保留' if is_kept else '✗ 剔除 (分数过低)'
            logging.debug(f'相关性得分: {rerank_score:.2f}  |  状态: {kept_label}')

            if is_kept:
                # 拓扑验证
                topology_score = 0.0
                topology_hops = None
                matched_devices = []
                if device_id:
                    matched_devices = self.extract_entities(candidate["content"])
                    topology_score, topology_hops, matched_devices = self._compute_topology_score(
                        matched_devices, topology_neighborhood, device_id
                    )
                    if topology_score != 0:
                        direction = '↑ 加分' if topology_score > 0 else '↓ 降权'
                        logging.debug(
                            f'拓扑验证: 命中设备={matched_devices}, '
                            f'跳数={topology_hops}, 拓扑分={topology_score:+.2f} ({direction})'
                        )
                    else:
                        logging.debug(f'拓扑验证: 未命中具体设备，视为通用知识 (0)')
                else:
                    logging.debug(f'拓扑验证: 未提供 device_id，跳过')

                final_score = rerank_score + topology_score

                idx += 1
                source_name = "Milvus" if candidate["source"] == "milvus" else "Neo4j"
                item = {
                    "source": candidate["source"],
                    "content": candidate["content"],
                    "score": round(rerank_score, 4),
                    "topology_score": round(topology_score, 4),
                    "topology_hops": topology_hops,
                    "matched_devices": matched_devices,
                    "final_score": round(final_score, 4),
                }
                evidence.append(item)
                topo_note = ""
                if topology_hops is not None:
                    topo_note = f", 拓扑距离: {topology_hops}跳, 拓扑分: {topology_score:+.2f}"
                context_parts.append(
                    f"【证据{idx}，来源：{source_name}，语义相关性：{rerank_score:.2f}"
                    f"{topo_note}，综合得分：{final_score:.2f}】\n{candidate['content']}"
                )

        # 按综合得分重排
        evidence.sort(key=lambda x: x["final_score"], reverse=True)
        # 重建 context_parts 排序
        context_parts_sorted = []
        for i, ev in enumerate(evidence, 1):
            source_name = "Milvus" if ev["source"] == "milvus" else "Neo4j"
            topo_note = ""
            if ev["topology_hops"] is not None:
                topo_note = f", 拓扑距离: {ev['topology_hops']}跳, 拓扑分: {ev['topology_score']:+.2f}"
            context_parts_sorted.append(
                f"【证据{i}，来源：{source_name}，语义相关性：{ev['score']:.2f}"
                f"{topo_note}，综合得分：{ev['final_score']:.2f}】\n{ev['content']}"
            )

        context = "\n\n".join(context_parts_sorted) if context_parts_sorted else "未检索到任何证据。"
        return {"evidence": evidence, "context": context}

    def hybrid_search(self, query, device_id, top_k=5):
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_milvus = executor.submit(self.retrieve_from_milvus, query, top_k)
            future_neo4j = executor.submit(self.retrieve_from_neo4j, device_id)
            milvus_results = future_milvus.result()
            neo4j_results = future_neo4j.result()
        all_candidates = milvus_results + neo4j_results
        # 按 content 去重，避免同一文本被重复评估
        seen = set()
        unique_candidates = []
        for c in all_candidates:
            key = c["content"]
            if key not in seen:
                seen.add(key)
                unique_candidates.append(c)
        # 分离 Neo4j 和 Milvus 候选
        neo4j_candidates = [c for c in unique_candidates if c["source"] == "neo4j"]
        milvus_candidates = [c for c in unique_candidates if c["source"] == "milvus"]

        # Milvus 走 reranker + 拓扑验证
        raw = self.rerank_and_filter(query, milvus_candidates, device_id=device_id)

        # Neo4j 拓扑链路直接输出，不经过语义 reranker
        topology_chain = []
        for c in neo4j_candidates:
            chain = self._parse_topology_chain(c["content"])
            if chain:
                topology_chain.append(chain)

        # Milvus 结果拆分
        evidence = raw.get("evidence", [])
        semantic_hits = []
        filtered_out = []
        for ev in evidence:
            if ev.get("final_score", 0) > 0:
                semantic_hits.append(ev["content"])
            else:
                filtered_out.append(ev["content"])

        # 生成拓扑链路摘要
        evidence_snapshot = self._build_snapshot(topology_chain, device_id)

        return {
            "evidence_snapshot": evidence_snapshot,
            "topology_chain": topology_chain,
            "semantic_hits": semantic_hits,
            "filtered_out": filtered_out,
            "query": query,
            "device_id": device_id,
        }


# ==========================================
# 3. 极简的模拟调用测试
# ==========================================
if __name__ == '__main__':
    logging.info('HybridGraphRAG 模块加载成功。')
    logging.info('运行测试请使用: python test_hybrid.py')
