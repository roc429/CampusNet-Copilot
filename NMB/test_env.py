from FlagEmbedding import FlagModel
from pymilvus import MilvusClient

print("--- 1. 正在加载 BGE-M3 模型 (首次运行会自动下载) ---")
# 这里的 use_fp16=False 对没有高端显卡的普通电脑更友好
model = FlagModel('BAAI/bge-m3', use_fp16=False)

# 我们准备存入的一条校园网运维知识
text = "302考场考试系统卡顿，通常是因为接入层交换机端口丢包或AP负载过高。"
print(f"正在将文本转化为向量: '{text}'")
vector = model.encode(text).tolist()

print("\n--- 2. 正在连接 Milvus Lite ---")
# 这里会自动在当前目录生成一个 milvus_demo.db 文件，不需要安装额外的数据库软件！
client = MilvusClient(uri="http://localhost:19530")

collection_name = "test_knowledge"

# 如果存在旧集合就删掉，保持干净
if client.has_collection(collection_name):
    client.drop_collection(collection_name)

# 创建一个集合（类似于关系型数据库里的表）
client.create_collection(
    collection_name=collection_name,
    dimension=1024 # BGE-M3 输出的向量维度是 1024
)

print("\n--- 3. 正在将向量存入 Milvus ---")
data = [
    {"id": 1, "vector": vector, "text": text}
]
client.insert(collection_name=collection_name, data=data)

print("\n🎉 恭喜！BGE-M3 与 Milvus Lite 环境配置与数据插入全部成功！")