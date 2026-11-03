/* 后端地址配置：电脑上跑的政治助手服务（Windows 拉 E:\workspace\政治助手\server.py）
 * 真机上要用电脑的局域网 IP（电脑上 ipconfig 看 IPv4 地址），同一 WiFi 才能连。
 * 目前预填 192.168.4.12；家里换了 WiFi 或改了网段，改这里一行即可。 */
module.exports = {
  LAN_IP: '192.168.4.12',
  PORT: 8686,
  NOTE: '开发者工具里自动走 http://127.0.0.1；真机走 http://局域网IP',
};
