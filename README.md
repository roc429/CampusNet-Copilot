# CampusNet-Copilot
本项目是针对“中国高校计算机大赛-网络技术挑战赛”开发的拓扑感知型校园网智能运维系统 。系统通过集成 Qwen3 推理决策大脑、TimesFM 时序预测引擎及 SDN 数字孪生沙盒，实现了从“被动响应”向“预警式防御”的范式转变 。

1. 编译与部署指南
1.1 环境依赖
后端：Python 3.10+ (核心框架：FastAPI, LangGraph) 
数据库：Neo4j (图谱), Milvus (向量), PostgreSQL (元数据)  
仿真环境：Mininet 2.3.0+, Ryu 控制器 
协议栈：Model Context Protocol (MCP)

1.2 快速启动
项目采用 Docker 容器化部署以确保环境一致性：
```Bash
# 1. 配置环境变量 (包含 Qwen3 API Key)
cp .env.example .env

# 2. 启动基础数据库与工具总线 (MCP Servers)
docker-compose up -d neo4j milvus postgres mcp-servers

# 3. 编译并启动后端 Agent 引擎
pip install -r requirements.txt
python main.py
```

2. 统一接口规范 (API Specification)
为了实现“意图驱动”的解耦架构，系统所有核心交互均通过统一的智能体网关进行 。

2.1 任务分发接口

端点：POST /v1/agent/task   
功能：接收自然语言查询，通过多智能体协作流进行诊断或预警 。
请求体 (JSON)：
```JSON
{
  "query": "预测明天的出口链路拥塞风险", // 用户自然语言输入 [cite: 923]
  "user_role": "admin", // 用户权限标识 (用于安全护栏审计) [cite: 714]
  "context": {
    "location": "核心机房", // 初始空间上下文 [cite: 892]
    "session_id": "uuid-12345"
  }
}
```

2.2 响应协议
核心字段：必须包含 thinking_process (推理链) 与 evidence_snapshot (证据快照) 。
双回路确认：若涉及网络变更，返回体中需包含 simulation_id 以供效果回溯 。

3. SDN 数字孪生验证说明
对于任何高危网络变更指令，系统强制进入 “双回路验证” 流程 ：
内回路 (语义审计)：通过 NeMo Guardrails 对拟执行指令进行逻辑合规性校验 。  
外回路 (物理验证)：指令在 Mininet + Ryu 构建的 1:1 映射仿真网络中预执行，通过 Prometheus 监测流量特征 。
资源申请：在 Slurm 或仿真调度中需指定：
```Bash
#SBATCH --gres=sdn_sandbox:1 # 申请单套 SDN 仿真容器资源 [cite: 858]
```
