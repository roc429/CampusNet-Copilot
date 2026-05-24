import os
import warnings
from dotenv import load_dotenv  # 引入环境变量读取工具
from FlagEmbedding import FlagModel, FlagReranker
from pymilvus import MilvusClient
from neo4j import GraphDatabase

# ==========================================
# 0. 环境初始化配置
# ==========================================
# 自动寻找并加载项目目录下的 .env 文件到系统的环境变量中
load_dotenv()

# 屏蔽 HuggingFace 底层的唠叨警告
warnings.filterwarnings("ignore", category=FutureWarning)


# ==========================================
# 1. 资源管理器 (单例模式 + 环境变量注入)
# ==========================================
class ResourceManager:
    _embed_model = None
    _reranker = None
    _milvus_client = None
    _neo4j_driver = None

    @classmethod
    def get_embed_model(cls):
        if cls._embed_model is None:
            print("⏳ [ResourceManager] 首次加载 BGE-M3 嵌入模型到内存...")
            cls._embed_model = FlagModel('BAAI/bge-m3', use_fp16=False)
        return cls._embed_model

    @classmethod
    def get_reranker(cls):
        if cls._reranker is None:
            print("⏳ [ResourceManager] 首次加载 BGE-M3 重排序模型到内存...")
            cls._reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=False)
        return cls._reranker

    @classmethod
    def get_milvus_client(cls):
        if cls._milvus_client is None:
            # 【改变】不再写死，而是从环境变量读取。如果没读到，默认用 localhost
            uri = os.getenv("MILVUS_URI", "http://localhost:19530")
            print(f"🔗 [ResourceManager] 首次建立 Milvus 连接 ({uri})...")
            cls._milvus_client = MilvusClient(uri=uri)
        return cls._milvus_client

    @classmethod
    def get_neo4j_driver(cls):
        if cls._neo4j_driver is None:
            # 【改变】账号密码全部从环境变量安全读取
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            pwd = os.getenv("NEO4J_PWD", "password")
            print(f"🔗 [ResourceManager] 首次建立 Neo4j 连接池 ({uri})...")
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

        # 不再需要从参数传密码了，ResourceManager 自己会去环境变量找
        self.neo4j_driver = ResourceManager.get_neo4j_driver()

        # 业务参数也解耦：集合名称和打分阈值都从环境变量读
        self.collection_name = os.getenv("MILVUS_COLLECTION", "test_knowledge")
        self.score_threshold = float(os.getenv("RERANK_THRESHOLD", "-2.0"))

    def retrieve_from_milvus(self, query, top_k=3):
        print(f"\n[Milvus 检索] 正在查找 '{query}' 相关的语义经验...")
        query_vector = self.embed_model.encode(query).tolist()
        try:
            results = self.milvus_client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                limit=top_k,
                output_fields=["text"]
            )
            milvus_context = [hit["entity"]["text"] for hits in results for hit in hits]
            print(f"  -> Milvus 命中 {len(milvus_context)} 条语义记录。")
            return milvus_context
        except Exception as e:
            print(f"  -> Milvus 检索出错: {e}")
            return []

    def retrieve_from_neo4j(self, device_id):
        print(f"[Neo4j 检索] 正在查找设备 '{device_id}' 的多跳物理拓扑...")
        cypher_query = """
        MATCH (start {deviceID: $device_id})-[r]-(connected_node)
        RETURN start.deviceID AS Source, type(r) AS Relation, connected_node.name AS Target
        LIMIT 5
        """
        neo4j_context = []
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(cypher_query, device_id=device_id)
                for record in result:
                    path_desc = f"物理拓扑路径: 设备 {record['Source']} 通过 {record['Relation']} 关联到 {record['Target']}。"
                    neo4j_context.append(path_desc)
            print(f"  -> Neo4j 命中 {len(neo4j_context)} 条拓扑链路。")
            return neo4j_context
        except Exception as e:
            print(f"  -> Neo4j 检索出错: {e}")
            return []

    def rerank_and_filter(self, query, milvus_candidates, neo4j_candidates):
        print("\n[BGE-M3 重排序] 正在进行全局评估与幻觉过滤...")
        all_candidates = milvus_candidates + neo4j_candidates
        if not all_candidates:
            print("  -> 未检索到任何候选证据。")
            return "未检索到任何证据。"

        sentence_pairs = [[query, candidate] for candidate in all_candidates]
        scores = self.reranker.compute_score(sentence_pairs)
        if isinstance(scores, float): scores = [scores]

        scored_candidates = list(zip(all_candidates, scores))
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        final_evidence = []
        for candidate, score in scored_candidates:
            # 【改变】使用环境变量里的阈值判断
            is_kept = score > self.score_threshold
            print(f"  -> 评估链路: {candidate}")
            print(f"     相关性得分: {score:.2f}  |  状态: {'✅ 保留' if is_kept else '❌ 剔除 (分数过低)'}")
            if is_kept:
                final_evidence.append(candidate)

        return "\n".join(final_evidence)

    def hybrid_search(self, query, device_id):
        milvus_results = self.retrieve_from_milvus(query)
        neo4j_results = self.retrieve_from_neo4j(device_id)
        return self.rerank_and_filter(query, milvus_results, neo4j_results)


# ==========================================
# 3. 极简的模拟调用测试 (再也没有明文密码了！)
# ==========================================
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(" 🚀 智网学伴 Hybrid GraphRAG 启动测试 ")
    print("=" * 50)

    # 初始化时无需传递任何账号密码，对象会自动去读 .env
    retriever = HybridGraphRAG()

    res = retriever.hybrid_search("302考场考试系统卡顿，是不是AP负载太高导致的？", "AP-EXAM-302")

    print("\n🎯 最终提交给大模型的无幻觉证据快照：\n" + "-" * 40)
    print(res)
    print("-" * 40)