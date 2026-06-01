# TimesFM 预测、主动防御与 API 接口运行 README

本文档说明第二阶段中 TimesFM 持续预测、预测告警、主动防御执行器和 `/api/ops/predict` 接口的完整运行流程。

当前系统已经完成以下能力：

1. Ryu 控制器持续采集网络遥测数据，写入 `telemetry.csv`
2. TimesFM 读取遥测数据，预测 AP 负载和丢包率
3. 预测结果写入 `prediction.csv`
4. 风险触发后生成告警意图，写入 `alert_intents.jsonl`
5. 主动防御执行器读取告警，生成策略并调用 Ryu 下发流表
6. API 服务提供 `/api/ops/predict` 接口，供前端或 Qwen3 调用

---

## 一、目录约定

项目根目录：

```bash
/home/jowin/Desktop/neta
```

TimesFM 虚拟环境：

```bash
/home/jowin/Desktop/neta/phase2/timesfm/.venv
```

TimesFM 本地模型目录：

```bash
/home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch
```

核心代码文件：

```bash
/home/jowin/Desktop/neta/phase2/timesfm/device_map.py
/home/jowin/Desktop/neta/phase2/timesfm/timesfm_engine.py
/home/jowin/Desktop/neta/phase2/timesfm/run_timesfm_loop.py
/home/jowin/Desktop/neta/phase2/timesfm/defense_executor.py
/home/jowin/Desktop/neta/phase2/timesfm/api_server.py
```

数据文件：

```bash
/home/jowin/Desktop/neta/phase2/data/telemetry.csv
/home/jowin/Desktop/neta/phase2/data/prediction.csv
/home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl
/home/jowin/Desktop/neta/phase2/data/defense_status.jsonl
```

---

## 二、device_id 说明

系统统一使用 `device_id` 作为设备主键。

前端、Qwen3、Prometheus、Neo4j 和 API 都使用 `device_id`，Ryu 和 Mininet 执行时再由后端转换成 `dpid`、`port` 和 IP。

例如：

```text
AP-EXAM-302
    ↓
dpid = 6
port = 1
metric ap_load -> load
```

当前 AP 设备映射如下：

| device_id   | 含义           | dpid | port | role        |
| ----------- | ------------ | ---: | ---: | ----------- |
| AP-EXAM-301 | 301 考场 AP    |    5 |    1 | teaching_ap |
| AP-EXAM-302 | 302 考场 AP    |    6 |    1 | teaching_ap |
| AP-EXAM-303 | 303 考场 AP    |    7 |    1 | teaching_ap |
| AP-LIB-A1   | 图书馆 A1 AP    |    9 |    1 | dorm_ap     |
| AP-DORM-A1  | 宿舍 A 区 A1 AP |   10 |    1 | dorm_ap     |
| AP-DORM-A2  | 宿舍 A 区 A2 AP |   11 |    1 | dorm_ap     |

接口中的指标名：

| 外部 metric | 内部字段 | 含义       |
| --------- | ---- | -------- |
| ap_load   | load | AP 端口负载率 |
| ap_loss   | loss | AP 端口丢包率 |

---

## 三、运行前提

运行本文档流程前，应保证 Ryu 和 Mininet 已经正常启动，并且 `telemetry.csv` 正在持续生成。

Ryu 启动命令：

```bash
cd /home/jowin/Desktop/neta
ryu-manager --ofp-tcp-listen-port 6633 --wsapi-port 8080 phase2/flow_ai.py
```

Mininet 启动命令：

```bash
cd /home/jowin/Desktop/neta
sudo mn --custom campus.py --topo campus --controller=remote,ip=127.0.0.1,port=6633 --link=tc
```

进入 Mininet 后配置网关：

```bash
gw ip addr add 192.168.1.1/24 dev gw-eth0
gw ip addr add 192.168.2.1/24 dev gw-eth0
gw sysctl -w net.ipv4.ip_forward=1
gw iptables -F
gw iptables -P FORWARD ACCEPT
```

检查 Ryu 遥测文件：

```bash
head -n 3 /home/jowin/Desktop/neta/phase2/data/telemetry.csv
```

第一行应包含表头：

```text
timestamp,timestamp_iso,dpid,port,role,rx_bytes,tx_bytes,rx_packets,tx_packets,rx_dropped,tx_dropped,byte_delta,packet_delta,drop_delta,throughput_bps,port_bw_mbps,load,loss
```

持续观察遥测数据：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/telemetry.csv
```

---

## 四、清理旧输出文件

由于新的预测结果中已经加入 `device_id`、`device_name`、`zone_id`、`area_id` 等字段，运行前建议清理旧输出文件。

```bash
cd /home/jowin/Desktop/neta

rm -f /home/jowin/Desktop/neta/phase2/data/prediction.csv
rm -f /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl
rm -f /home/jowin/Desktop/neta/phase2/data/defense_status.jsonl
```

清理后不删除 `telemetry.csv`，因为它是 TimesFM 的输入数据。

---

## 五、启动 TimesFM 持续预测服务

打开一个新终端，执行：

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate
```

启动持续预测：

```bash
python phase2/timesfm/run_timesfm_loop.py \
  --model-id /home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch \
  --telemetry /home/jowin/Desktop/neta/phase2/data/telemetry.csv \
  --prediction /home/jowin/Desktop/neta/phase2/data/prediction.csv \
  --alert-file /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl \
  --interval 30 \
  --hour-seconds 5 \
  --horizon 24 \
  --min-context 3
```

参数说明：

| 参数               | 含义                         |
| ---------------- | -------------------------- |
| `--model-id`     | TimesFM 本地模型目录             |
| `--telemetry`    | Ryu 生成的遥测文件                |
| `--prediction`   | TimesFM 预测结果输出文件           |
| `--alert-file`   | TimesFM 预测告警输出文件           |
| `--interval`     | 每隔多少秒运行一轮预测                |
| `--hour-seconds` | 实验时间压缩参数，5 表示 5 秒作为一个预测时间步 |
| `--horizon`      | 预测未来多少个时间步                 |
| `--min-context`  | 最少历史上下文点数                  |

同时预测负载和丢包率时，使用：

```bash
python phase2/timesfm/run_timesfm_loop.py \
  --model-id /home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch \
  --telemetry /home/jowin/Desktop/neta/phase2/data/telemetry.csv \
  --prediction /home/jowin/Desktop/neta/phase2/data/prediction.csv \
  --alert-file /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl \
  --interval 30 \
  --hour-seconds 5 \
  --horizon 24 \
  --min-context 3 \
  --include-loss
```

正常输出示例：

```text
========== TimesFM 持续预测服务启动 ==========
模型路径: /home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch
遥测文件: /home/jowin/Desktop/neta/phase2/data/telemetry.csv
预测结果: /home/jowin/Desktop/neta/phase2/data/prediction.csv
预警文件: /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl

========== 新一轮 TimesFM 预测 ==========
[OK] device_id=AP-EXAM-302 name=302考场AP dpid=6 port=1 metric=ap_load risk=True risk_level=HIGH
[ALERT] 已生成预测告警: {...}
```

查看预测结果：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/prediction.csv
```

查看预测告警：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl
```

---

## 六、启动主动防御执行器

主动防御执行器负责读取：

```bash
/home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl
```

然后生成策略，经过语义校验和沙盒状态记录后，调用 Ryu：

```bash
http://127.0.0.1:8080/policy/apply
```

打开新终端，执行：

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate
```

启动主动防御执行器：

```bash
python phase2/timesfm/defense_executor.py \
  --alert-file /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl \
  --status-file /home/jowin/Desktop/neta/phase2/data/defense_status.jsonl \
  --ryu-api http://127.0.0.1:8080/policy/apply \
  --interval 5
```

正常状态流转如下：

```text
strategy_generating      策略生成中
strategy_generated       策略已生成
semantic_guard_checked   语义审计完成
sandbox_verifying        沙盒验证中
sandbox_verified         验证通过
policy_applied           已下发
```

查看主动防御状态：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/defense_status.jsonl
```

策略下发后，可以在 Mininet 中验证阻断效果。

例如 AP-EXAM-302 对应的疑似异常主机是 `192.168.1.11`，可以测试：

```bash
h2 ping -c 3 192.168.1.10
```

AP-LIB-A1 对应的疑似异常主机是 `192.168.2.10`，可以测试：

```bash
h11 ping -c 3 192.168.2.11
```

---

## 七、启动 API 接口服务

API 服务提供前端和 Qwen3 调用的统一预测接口。

打开新终端，执行：

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate
```

确认依赖已经安装：

```bash
uv pip install fastapi uvicorn requests
```

启动接口服务：

```bash
python phase2/timesfm/api_server.py
```

正常输出示例：

```text
Uvicorn running on http://0.0.0.0:8000
```

接口服务启动后，访问地址为：

```text
http://127.0.0.1:8000
```

---

## 八、接口测试

### 1. 健康检查

```bash
curl http://127.0.0.1:8000/health
```

正常返回示例：

```json
{
  "ok": true,
  "service": "timesfm_ops_api",
  "model_dir": "/home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch",
  "telemetry_file": "/home/jowin/Desktop/neta/phase2/data/telemetry.csv"
}
```

---

### 2. 查询设备映射

```bash
curl http://127.0.0.1:8000/api/ops/devices
```

该接口返回当前系统支持的设备列表和 `device_id -> dpid/port` 映射关系。

重点设备包括：

```text
AP-EXAM-301
AP-EXAM-302
AP-EXAM-303
AP-LIB-A1
AP-DORM-A1
AP-DORM-A2
```

---

### 3. 调用 TimesFM 预测接口

接口地址：

```text
POST /api/ops/predict
```

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/ops/predict \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "AP-EXAM-302",
    "metric": "ap_load",
    "horizon": 12,
    "hour_seconds": 5,
    "min_context": 3,
    "return_history_points": 24,
    "auto_write_alert": true
  }'
```

请求字段说明：

| 字段                      | 含义                             |
| ----------------------- | ------------------------------ |
| `device_id`             | 统一设备 ID，例如 `AP-EXAM-302`       |
| `metric`                | 外部指标名，例如 `ap_load` 或 `ap_loss` |
| `horizon`               | 预测未来多少个时间步                     |
| `hour_seconds`          | 实验时间压缩参数                       |
| `min_context`           | 最少历史上下文点数                      |
| `return_history_points` | 返回给前端的历史点数量                    |
| `auto_write_alert`      | 风险为 HIGH 时是否写入告警文件             |

正常返回示例：

```json
{
  "request_id": "pred-1780045000123",
  "timestamp": 1780045000.123,
  "timestamp_iso": "2026-05-29T17:00:00",
  "device_id": "AP-EXAM-302",
  "device_name": "302考场AP",
  "zone_id": "ZONE-TEACH",
  "area_id": "302",
  "metric": "ap_load",
  "internal_metric": "load",
  "dpid": 6,
  "port": 1,
  "horizon": 12,
  "history": [0.12, 0.14, 0.16],
  "forecast": [0.18, 0.19, 0.20],
  "upper_bound": [0.21, 0.22, 0.23],
  "lower_bound": [0.15, 0.16, 0.17],
  "risk": "HIGH",
  "alert": "未来12个时间步：AP-EXAM-302(302考场AP)预计过载，建议触发主动防御",
  "defense_status": "strategy_generating",
  "evidence_snapshot": {
    "history_last_value": 0.16,
    "history_ci_low": 0.02,
    "history_ci_high": 0.17,
    "threshold": 0.8,
    "trend": {
      "label": "rising"
    },
    "alert_written": true
  }
}
```

返回字段说明：

| 字段                  | 含义                         |
| ------------------- | -------------------------- |
| `history`           | 历史负载或丢包率                   |
| `forecast`          | TimesFM 点预测结果              |
| `upper_bound`       | 预测上界，来自 q90                |
| `lower_bound`       | 预测下界，来自 q10                |
| `risk`              | 风险等级，`LOW`、`MEDIUM`、`HIGH` |
| `alert`             | 给前端展示的告警文本                 |
| `defense_status`    | 主动防御状态                     |
| `evidence_snapshot` | 证据快照，包含阈值、趋势、历史置信区间等       |

---

### 4. 查询主动防御状态

接口地址：

```text
GET /api/ops/defense/status
```

查询全部最近状态：

```bash
curl "http://127.0.0.1:8000/api/ops/defense/status?limit=10"
```

查询某个设备状态：

```bash
curl "http://127.0.0.1:8000/api/ops/defense/status?device_id=AP-EXAM-302&limit=10"
```

正常返回示例：

```json
{
  "ok": true,
  "data": [
    {
      "timestamp": 1780045000.123,
      "timestamp_iso": "2026-05-29T17:00:00",
      "alert_id": "xxx",
      "stage": "strategy_generating",
      "status_cn": "策略生成中",
      "device_id": "AP-EXAM-302"
    },
    {
      "timestamp": 1780045001.456,
      "timestamp_iso": "2026-05-29T17:00:01",
      "alert_id": "xxx",
      "stage": "sandbox_verified",
      "status_cn": "验证通过",
      "device_id": "AP-EXAM-302"
    },
    {
      "timestamp": 1780045002.789,
      "timestamp_iso": "2026-05-29T17:00:02",
      "alert_id": "xxx",
      "stage": "policy_applied",
      "status_cn": "已下发",
      "device_id": "AP-EXAM-302"
    }
  ]
}
```

---

## 九、完整运行顺序

完整运行时建议至少打开 5 个终端。

### 终端 1：Ryu 控制器

```bash
cd /home/jowin/Desktop/neta
ryu-manager --ofp-tcp-listen-port 6633 --wsapi-port 8080 phase2/flow_ai.py
```

### 终端 2：Mininet 拓扑

```bash
cd /home/jowin/Desktop/neta
sudo mn --custom campus.py --topo campus --controller=remote,ip=127.0.0.1,port=6633 --link=tc
```

Mininet 内配置网关：

```bash
gw ip addr add 192.168.1.1/24 dev gw-eth0
gw ip addr add 192.168.2.1/24 dev gw-eth0
gw sysctl -w net.ipv4.ip_forward=1
gw iptables -F
gw iptables -P FORWARD ACCEPT
```

制造持续流量：

```bash
h12 iperf -s &
h11 iperf -c 192.168.2.11 -u -b 20M -t 600 -i 1 &

h2 iperf -s &
h1 iperf -c 192.168.1.11 -u -b 20M -t 600 -i 1 &
```

### 终端 3：TimesFM 持续预测

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate

python phase2/timesfm/run_timesfm_loop.py \
  --model-id /home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch \
  --telemetry /home/jowin/Desktop/neta/phase2/data/telemetry.csv \
  --prediction /home/jowin/Desktop/neta/phase2/data/prediction.csv \
  --alert-file /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl \
  --interval 30 \
  --hour-seconds 5 \
  --horizon 24 \
  --min-context 3
```

### 终端 4：主动防御执行器

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate

python phase2/timesfm/defense_executor.py \
  --alert-file /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl \
  --status-file /home/jowin/Desktop/neta/phase2/data/defense_status.jsonl \
  --ryu-api http://127.0.0.1:8080/policy/apply \
  --interval 5
```

### 终端 5：API 接口服务

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate

python phase2/timesfm/api_server.py
```

### 终端 6：观察数据

查看遥测：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/telemetry.csv
```

查看预测：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/prediction.csv
```

查看告警：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl
```

查看主动防御状态：

```bash
tail -f /home/jowin/Desktop/neta/phase2/data/defense_status.jsonl
```

---

## 十、验收检查项

完成运行后，应验证以下内容：

1. `telemetry.csv` 持续写入 Ryu 遥测数据
2. `prediction.csv` 持续写入 TimesFM 预测结果
3. `alert_intents.jsonl` 在风险触发时写入预测告警
4. `defense_status.jsonl` 记录主动防御状态流转
5. `/api/ops/devices` 可以返回设备映射
6. `/api/ops/predict` 可以返回历史曲线、预测曲线、上下界和风险等级
7. `/api/ops/defense/status` 可以返回策略生成、沙盒验证和下发状态
8. Ryu `/policy/apply` 可以接收主动防御策略
9. Mininet 中对应主机通信可以被临时阻断
10. `device_id` 已经统一使用组长要求的命名体系

---

## 十一、常见问题

### 1. `prediction.csv` 没有数据

检查 TimesFM 持续预测是否正在运行：

```bash
ps aux | grep run_timesfm_loop.py
```

检查输入文件是否有表头：

```bash
head -n 3 /home/jowin/Desktop/neta/phase2/data/telemetry.csv
```

### 2. `telemetry.csv` 缺少字段

说明旧文件没有表头。停掉 Ryu 后删除旧遥测文件，再重新启动 Ryu：

```bash
rm -f /home/jowin/Desktop/neta/phase2/data/telemetry.csv
```

重新启动 Ryu 和 Mininet 后再检查：

```bash
head -n 3 /home/jowin/Desktop/neta/phase2/data/telemetry.csv
```

### 3. API 报模型路径错误

检查模型文件：

```bash
ls -lh /home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch
```

目录中应包含：

```text
config.json
model.safetensors
README.md
```

### 4. 主动防御没有下发

检查 Ryu REST 接口：

```bash
curl http://127.0.0.1:8080/health
```

检查防御执行器是否启动：

```bash
ps aux | grep defense_executor.py
```

检查告警文件是否有内容：

```bash
tail -n 5 /home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl
```

### 5. 接口启动失败

确认依赖安装在 TimesFM 虚拟环境中：

```bash
cd /home/jowin/Desktop/neta
source phase2/timesfm/.venv/bin/activate
uv pip install fastapi uvicorn requests
```

重新启动：

```bash
python phase2/timesfm/api_server.py
```

---

## 十二、当前数据流总结

```text
Mininet 校园网
    ↓
Ryu 控制器采集端口统计
    ↓
telemetry.csv
    ↓
TimesFM 持续预测
    ↓
prediction.csv
    ↓
alert_intents.jsonl
    ↓
defense_executor.py
    ↓
策略生成、语义审计、沙盒状态记录
    ↓
Ryu /policy/apply
    ↓
OpenFlow 主动防御流表下发
    ↓
defense_status.jsonl
    ↓
前端 / Qwen3 通过 API 查询预测和防御状态
```

API 入口：

```text
POST /api/ops/predict
GET  /api/ops/devices
GET  /api/ops/defense/status
```

至此，TimesFM 预测结果、预测告警、主动防御状态和前端接口传输链路均已打通。
