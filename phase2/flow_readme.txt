第二阶段 Ryu 控制器功能与测试汇总

本文记录第二阶段中 Ryu 控制器的功能实现和测试结果。
本阶段在第一阶段三层校园网拓扑基础上，完成了遥测采集、实时指标计算、REST 接口开放和主动防御流表下发，为后续 TimesFM 预测引擎、Qwen3 策略生成和沙盒验证提供控制器基础。

本文以 phase2/flow_ai.py 为第二阶段控制器文件。
如果实际文件名是 flow.py，把命令中的 phase2/flow_ai.py 替换为 flow.py 即可。


一、功能汇总与测试方式

1. 基础 SDN 转发功能

控制器保留第一阶段的 MAC 学习交换功能。
交换机接入 Ryu 后，控制器会安装 table-miss 流表。未知流量会先上送控制器，控制器根据源 MAC 和入端口学习转发表。目的 MAC 已知时单播转发，未知时泛洪转发。

该功能保证第一阶段的校园网拓扑在第二阶段控制器下仍然可以正常通信。

测试方式如下。

先清理 Mininet 残留。

    sudo mn -c

启动 Ryu 控制器。

    ryu-manager --ofp-tcp-listen-port 6633 --wsapi-port 8080 phase2/flow_ai.py

启动 Mininet。

    sudo mn --custom campus.py --topo campus --controller=remote,ip=127.0.0.1,port=6633 --link=tc

测试同网段连通性。

    h1 ping -c 3 192.168.1.11
    h11 ping -c 3 192.168.2.11
    web ping -c 3 192.168.3.101

测试结果：
同网段主机通信正常，说明控制器的基础二层转发功能正常。


2. 三层校园网兼容功能

第二阶段 Ryu 控制器不替代 gw 做三层路由。
教学区、宿舍区、数据中心之间的跨网段通信仍然依赖第一阶段中的网关主机 gw。

因此，完整三层校园网测试时需要继续配置 gw 的多网段 IP，并开启 IP 转发。

配置方式如下。

    gw ip addr add 192.168.1.1/24 dev gw-eth0
    gw ip addr add 192.168.2.1/24 dev gw-eth0
    gw sysctl -w net.ipv4.ip_forward=1
    gw iptables -F
    gw iptables -P FORWARD ACCEPT

查看网关地址。

    gw ip addr show gw-eth0

应看到以下三个地址。

    192.168.3.1
    192.168.1.1
    192.168.2.1

测试跨网段通信。

    h1 ping -c 3 192.168.2.10
    h1 ping -c 3 192.168.3.100
    h11 ping -c 3 192.168.3.101

测试结果：
跨网段通信正常，说明第二阶段控制器兼容第一阶段的三层校园网配置。


3. 交换机接入状态管理功能

控制器会维护当前已接入的 OpenFlow 交换机列表。
本拓扑中一共有 16 台交换机，对应 s1 到 s16，DPID 为 1 到 16。

Ryu 控制器提供 /health 接口，用于查看控制器状态和交换机接入情况。

测试方式如下。

    curl http://127.0.0.1:8080/health

正常返回中应包含如下内容。

    {
      "ok": true,
      "switches": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]
    }

测试结果：
16 台交换机全部接入 Ryu，说明控制器和 Mininet 拓扑连接正常。


4. 遥测采集功能

控制器会周期性向所有交换机发送端口统计请求，采集端口级网络状态数据。

采集字段包括：

    rx_bytes
    tx_bytes
    rx_packets
    tx_packets
    rx_dropped
    tx_dropped

控制器会把采集结果写入：

    phase2/data/telemetry.csv

查看遥测文件。

    tail -f phase2/data/telemetry.csv

正常情况下，文件会持续新增数据。
字段中可以看到交换机编号、端口号、角色、收发字节数、收发包数、负载率和丢包率等内容。

测试结果：
telemetry.csv 持续写入数据，说明端口遥测采集功能正常。


5. 交换机角色识别功能

控制器会根据第一阶段拓扑结构识别交换机角色，并写入遥测数据。

角色映射如下。

    s1              core
    s2 s3 s4        aggregation
    s5-s8           teaching_ap
    s9-s12          dorm_ap
    s13-s16         data_access

在 telemetry.csv 中可以看到类似内容。

    6,1,teaching_ap
    9,1,dorm_ap
    13,1,data_access

测试方式如下。

    tail -f phase2/data/telemetry.csv

测试结果：
遥测数据中已经正确出现 core、aggregation、teaching_ap、dorm_ap、data_access 等角色，说明角色识别正常。


6. 端口负载和丢包率计算功能

控制器在采集原始端口统计数据后，会进一步计算以下指标：

    byte_delta
    packet_delta
    drop_delta
    throughput_bps
    port_bw_mbps
    load
    loss

其中：

    load = 当前端口吞吐量 / 当前端口带宽
    loss = 当前周期丢包增量 / 当前周期包总量

端口带宽按照 campus.py 中的链路参数估算。
例如接入交换机上联口按 100 Mbps 或 1000 Mbps 计算，主机接入口按 10 Mbps 计算。

制造教学区流量。

    h2 iperf -s &
    h1 iperf -c 192.168.1.11 -t 20 -i 1

制造宿舍区流量。

    h12 iperf -s &
    h11 iperf -c 192.168.2.11 -t 20 -i 1

查看负载变化。

    tail -f phase2/data/telemetry.csv

测试结果：
运行 iperf 后，相关交换机端口的 load 明显变化，说明吞吐量和负载率计算正常。当前测试中 loss 为 0，说明实验环境中未出现明显丢包。


7. 实时遥测查询接口

控制器提供 /telemetry/latest 接口，用于查询每个交换机端口的最新遥测状态。

测试方式如下。

    curl http://127.0.0.1:8080/telemetry/latest

返回内容包括：

    dpid
    port
    role
    rx_bytes
    tx_bytes
    rx_packets
    tx_packets
    throughput_bps
    load
    loss

测试结果：
接口可以正常返回最新遥测指标，说明外部模块可以通过 REST 接口读取实时网络状态。


8. 主动防御策略下发功能

控制器提供 /policy/apply 接口，用于接收外部模块生成的主动防御策略。
后续 Qwen3 生成的策略会通过该接口交给 Ryu 执行。

当前控制器支持以下动作：

    do_nothing
    drop_host
    protect_server
    rate_limit_host

其中 drop_host 和 protect_server 通过高优先级 OpenFlow 流表实现流量丢弃。
rate_limit_host 使用 OpenFlow meter 实现限速，是否可用取决于当前 OVS 版本是否支持 meter。

本次测试重点验证 drop_host。

先确认 h11 可以访问 h12。

    h11 ping -c 3 192.168.2.11

向 Ryu 下发主动防御策略。

    curl -X POST http://127.0.0.1:8080/policy/apply \
      -H "Content-Type: application/json" \
      -d '{
        "action": "drop_host",
        "reason": "test active defense",
        "dpid": 9,
        "priority": 200,
        "match": {
          "eth_type": 2048,
          "ipv4_src": "192.168.2.10"
        },
        "duration": 60
      }'

该策略含义如下。

    在 s9 上下发高优先级流表
    匹配 IPv4 源地址 192.168.2.10
    匹配后直接丢弃
    持续时间 60 秒

再次测试 h11 到 h12。

    h11 ping -c 3 192.168.2.11

预期结果：
通信被阻断。

查看 s9 流表。

    sh ovs-ofctl -O OpenFlow13 dump-flows s9

应看到匹配 192.168.2.10 的高优先级流表。

等待 60 秒后再次测试。

    h11 ping -c 3 192.168.2.11

预期结果：
通信恢复。

测试结果：
策略可以成功下发，指定主机流量可以被临时阻断，策略超时后通信恢复，说明主动防御流表下发功能正常。


9. 策略历史查询功能

控制器会记录最近下发过的策略，便于后续调试和验收展示。

测试方式如下。

    curl http://127.0.0.1:8080/policy/history

测试结果：
接口可以返回最近执行过的主动防御策略，说明策略记录功能正常。


二、完整测试流程

本次完整测试流程如下。

1. 清理 Mininet 残留。

    sudo mn -c

2. 启动第二阶段 Ryu 控制器。

    ryu-manager --ofp-tcp-listen-port 6633 --wsapi-port 8080 phase2/flow_ai.py

3. 启动 Mininet 校园网拓扑。

    sudo mn --custom campus.py --topo campus --controller=remote,ip=127.0.0.1,port=6633 --link=tc

4. 配置网关。

    gw ip addr add 192.168.1.1/24 dev gw-eth0
    gw ip addr add 192.168.2.1/24 dev gw-eth0
    gw sysctl -w net.ipv4.ip_forward=1
    gw iptables -F
    gw iptables -P FORWARD ACCEPT

5. 检查交换机接入。

    curl http://127.0.0.1:8080/health

6. 测试基础连通性。

    h1 ping -c 3 192.168.1.11
    h11 ping -c 3 192.168.2.11
    web ping -c 3 192.168.3.101

7. 测试跨网段连通性。

    h1 ping -c 3 192.168.2.10
    h1 ping -c 3 192.168.3.100
    h11 ping -c 3 192.168.3.101

8. 查看遥测数据。

    tail -f phase2/data/telemetry.csv

9. 制造教学区流量。

    h2 iperf -s &
    h1 iperf -c 192.168.1.11 -t 20 -i 1

10. 制造宿舍区流量。

    h12 iperf -s &
    h11 iperf -c 192.168.2.11 -t 20 -i 1

11. 查询实时遥测。

    curl http://127.0.0.1:8080/telemetry/latest

12. 下发主动防御策略。

    curl -X POST http://127.0.0.1:8080/policy/apply \
      -H "Content-Type: application/json" \
      -d '{
        "action": "drop_host",
        "reason": "test active defense",
        "dpid": 9,
        "priority": 200,
        "match": {
          "eth_type": 2048,
          "ipv4_src": "192.168.2.10"
        },
        "duration": 60
      }'

13. 验证阻断效果。

    h11 ping -c 3 192.168.2.11

14. 查看策略历史。

    curl http://127.0.0.1:8080/policy/history


三、测试通过结果

本次测试已经通过以下验证项：

    1. Ryu 控制器可以正常启动
    2. Mininet 中 16 台交换机可以全部接入 Ryu
    3. 第一阶段的同网段通信保持正常
    4. 配置 gw 后，三网段之间可以跨网段通信
    5. 控制器可以持续采集端口遥测数据
    6. telemetry.csv 可以持续写入 load 和 loss
    7. 运行 iperf 后，端口 load 指标可以发生变化
    8. /health 接口可以返回控制器状态
    9. /telemetry/latest 接口可以返回实时遥测数据
    10. /policy/apply 接口可以接收主动防御策略
    11. drop_host 策略可以成功阻断指定主机流量
    12. 策略超时后，通信可以自动恢复
    13. /policy/history 接口可以查看策略执行记录


四、阶段结论

第二阶段 Ryu 控制器部分已经完成并通过测试。
该控制器在第一阶段三层校园网拓扑基础上，新增了端口遥测采集、负载率计算、丢包率计算、REST 状态查询、策略接收和主动防御流表下发能力。

控制器能够持续生成 telemetry.csv，为 TimesFM 零样本时序预测提供 AP 负载和丢包率数据。同时，控制器已经具备接收外部策略并转化为 OpenFlow 流表的能力，可以作为后续 Qwen3 策略生成和沙盒验证模块的执行入口。

因此，当前 Ryu 控制器已经满足第二阶段中 SDN 控制和遥测回采部分的要求，后续可以继续接入 TimesFM 预测引擎、Qwen3 策略生成模块和双回路沙盒验证模块。
