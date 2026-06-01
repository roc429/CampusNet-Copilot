#!/bin/bash

# 启动脚本 - 完整校园网 SDN

echo "=== 启动 Ryu 控制器 ==="
cd ~/Desktop/neta
gnome-terminal --tab --title="Ryu Controller" -- bash -c "ryu-manager flow.py; exec bash"

sleep 3

echo "=== 启动 Mininet 网络 ==="
sudo mn --custom campus.py --topo campus \
        --controller=remote,ip=127.0.0.1,port=6633 \
        --link=tc \
        --mac \
        --switch=ovsk,protocols=OpenFlow13

echo "=== 网络已启动 ==="