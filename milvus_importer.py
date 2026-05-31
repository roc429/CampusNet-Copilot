#!/usr/bin/env python3
"""Milvus 知识库数据导入脚本。"""
import argparse
import json
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from FlagEmbedding import FlagModel
from pymilvus import MilvusClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

MILVUS_URI        = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "test_knowledge")
BGE_DIM           = 1024
BATCH_SIZE        = 32


def main():
    parser = argparse.ArgumentParser(description="Milvus 知识库导入")
    parser.add_argument("json_file", help="知识库 JSON 文件路径")
    parser.add_argument("--clear", action="store_true", help="导入前清空并重建集合")
    args = parser.parse_args()

    with open(args.json_file, encoding="utf-8") as f:
        entries = json.load(f)

    logging.info("从 %s 读取 %d 条知识条目", args.json_file, len(entries))

    client = MilvusClient(uri=MILVUS_URI)
    logging.info("Milvus 连接: %s", MILVUS_URI)

    if args.clear:
        if client.has_collection(MILVUS_COLLECTION):
            client.drop_collection(MILVUS_COLLECTION)
            logging.info("已删除旧集合: %s", MILVUS_COLLECTION)

    if not client.has_collection(MILVUS_COLLECTION):
        client.create_collection(
            collection_name=MILVUS_COLLECTION,
            dimension=BGE_DIM,
            metric_type="COSINE",
        )
        logging.info("已创建集合: %s (dim=%d)", MILVUS_COLLECTION, BGE_DIM)

    logging.info("加载 BGE-M3 嵌入模型...")
    model = FlagModel("BAAI/bge-m3", use_fp16=False)

    logging.info("开始编码并插入...")
    total = 0
    texts = [e["text"] for e in entries]

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        vectors = model.encode(batch).tolist()
        data = [
            {"id": i + j, "vector": vectors[j], "text": batch[j]}
            for j in range(len(batch))
        ]
        client.insert(collection_name=MILVUS_COLLECTION, data=data)
        total += len(batch)
        logging.info("进度: %d / %d", total, len(texts))

    logging.info("导入完成，共 %d 条", len(texts))


if __name__ == "__main__":
    main()