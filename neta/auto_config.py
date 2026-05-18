# auto_config.py - 在 mininet> 中执行 pyexec auto_config.py
from mininet.net import Mininet

def config_network(net):
    # 配置网关
    gw = net.get('gw')
    gw.cmd('ifconfig gw-eth1:1 192.168.1.1 netmask 255.255.255.0')
    gw.cmd('ifconfig gw-eth1:2 192.168.2.1 netmask 255.255.255.0')
    gw.cmd('sysctl -w net.ipv4.ip_forward=1')
    
    # 配置教学区主机
    for i in range(1, 11):
        host = net.get('h{}'.format(i))
        host.cmd('ip route add default via 192.168.1.1')
    
    # 配置宿舍区主机
    for i in range(11, 21):
        host = net.get('h{}'.format(i))
        host.cmd('ip route add default via 192.168.2.1')
    
    print("✅ 所有主机路由配置完成！")

# 在 Mininet 中执行
config_network(net)