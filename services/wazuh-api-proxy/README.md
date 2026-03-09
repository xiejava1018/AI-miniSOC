# Wazuh API 代理服务

自动处理JWT token刷新的Wazuh API代理服务，解决Grafana Infinity插件中JWT token过期的问题。

## 功能特点

- ✅ **自动token刷新**：在token过期前自动刷新，无需手动干预
- ✅ **透明代理**：完全透明转发所有Wazuh API请求
- ✅ **健康检查**：提供/health端点监控服务状态
- ✅ **日志记录**：完整的请求日志和错误追踪
- ✅ **错误处理**：优雅的错误处理和重试机制
- ✅ **易于部署**：支持systemd服务自动启动

## 快速开始

### 1. 安装依赖

```bash
cd /home/xiejava/AIproject/AI-miniSOC/services/wazuh-api-proxy

# 安装Python依赖
pip3 install -r requirements.txt

# 或使用虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置（如果需要修改默认值）
vim .env
```

### 3. 启动服务

#### 方式1：直接启动（测试）
```bash
python3 wazuh_proxy.py
```

#### 方式2：使用Gunicorn（推荐生产环境）
```bash
gunicorn -w 4 -b 0.0.0.0:5000 wazuh_proxy:app
```

#### 方式3：使用systemd服务（自动启动）
```bash
# 安装服务
sudo ./install.sh

# 启动服务
sudo systemctl start wazuh-proxy

# 设置开机自启
sudo systemctl enable wazuh-proxy

# 查看状态
sudo systemctl status wazuh-proxy

# 查看日志
sudo journalctl -u wazuh-proxy -f
```

## API端点

### 代理Wazuh API

所有Wazuh API请求都会被透明转发：

```bash
# 获取agents列表
curl http://localhost:5000/agents?limit=20

# 获取agents状态汇总
curl http://localhost:5000/agents/summary/status

# 获取告警
curl http://localhost:5000/alerts?limit=10
```

### 管理端点

#### 健康检查
```bash
curl http://localhost:5000/health
```

响应示例：
```json
{
  "status": "healthy",
  "token_valid": true,
  "token_expires_at": 1773061234.56,
  "wazuh_url": "https://192.168.0.40:55000"
}
```

#### Token信息
```bash
curl http://localhost:5000/token-info
```

响应示例：
```json
{
  "token_exists": true,
  "expires_at": 1773061234.56,
  "time_remaining": 780,
  "last_refresh": 1773060456.78,
  "wazuh_url": "https://192.168.0.40:55000"
}
```

#### 手动刷新Token
```bash
curl -X POST http://localhost:5000/refresh-token
```

## 在Grafana Infinity中配置

### 创建数据源

1. 在Grafana中进入 **Configuration** → **Data sources**
2. 点击 **Add data source**
3. 选择 **Infinity**

### 配置参数

```
Name: Wazuh API Proxy
Type: REST API

URL: http://192.168.0.30:5000
```

### 认证配置

```
Authentication: None
（代理服务会自动处理token）
```

### 高级配置

```
Custom HTTP Headers: (无需添加)
Skip TLS Verify: ✅ (如果使用HTTPS)
```

### 示例查询

#### Agents状态统计
```
Type: REST API
URL: /agents/summary/status
Root Data: data.connection

Fields:
  - active: $.active
  - disconnected: $.disconnected
  - total: $.total
```

#### Agents列表
```
Type: REST API
URL: /agents?limit=20
Root Data: data.affected_items

Columns:
  - ID: $.id
  - Name: $.name
  - IP: $.ip
  - Status: $.status
  - OS: $.os.name
```

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WAZUH_URL` | https://192.168.0.40:55000 | Wazuh API地址 |
| `WAZUH_USER` | wazuh | Wazuh API用户名 |
| `WAZUH_PASSWORD` | * | Wazuh API密码 |
| `PROXY_PORT` | 5000 | 代理服务监听端口 |
| `TOKEN_EXPIRE_BUFFER` | 60 | Token提前刷新时间（秒） |

### Token刷新策略

- JWT token默认有效期为15分钟（900秒）
- 代理服务会在token过期前60秒自动刷新
- 提前刷新时间可通过`TOKEN_EXPIRE_BUFFER`环境变量配置

## 日志

服务日志保存在当前目录的`wazuh_proxy.log`文件中。

```bash
# 实时查看日志
tail -f wazuh_proxy.log

# 查看最近100行
tail -n 100 wazuh_proxy.log
```

如果使用systemd服务：

```bash
# 查看服务日志
sudo journalctl -u wazuh-proxy -f

# 查看最近100行
sudo journalctl -u wazuh-proxy -n 100
```

## 故障排查

### 服务无法启动

1. 检查端口是否被占用：
```bash
sudo lsof -i :5000
```

2. 检查Python依赖是否安装：
```bash
pip3 list | grep -E "Flask|requests"
```

3. 查看日志文件：
```bash
tail -f wazuh_proxy.log
```

### Token获取失败

1. 验证Wazuh API凭证：
```bash
curl -k -X POST 'https://192.168.0.40:55000/security/user/authenticate?raw=true' \
  -H 'Content-Type: application/json' \
  -d '{"username":"wazuh","password":"YOUR_PASSWORD"}'
```

2. 检查网络连接：
```bash
curl -k https://192.168.0.40:55000/
```

3. 检查服务健康状态：
```bash
curl http://localhost:5000/health
```

### Grafana无法连接

1. 确认服务正在运行：
```bash
curl http://localhost:5000/health
```

2. 检查防火墙：
```bash
sudo ufw status
sudo ufw allow 5000/tcp
```

3. 确认Grafana可以访问代理服务器（如果是远程）

## 安全建议

1. **使用HTTPS**：生产环境建议为代理服务启用HTTPS
2. **限制访问**：使用防火墙或Nginx限制访问来源
3. **定期更新**：保持依赖包最新版本
4. **监控日志**：定期检查访问日志，发现异常行为

## 性能优化

### 使用Gunicorn

生产环境建议使用Gunicorn部署：

```bash
# 安装
pip3 install gunicorn

# 启动（4个worker进程）
gunicorn -w 4 -b 0.0.0.0:5000 wazuh_proxy:app

# 或使用systemd服务（自动启动）
sudo systemctl start wazuh-proxy
```

### 配置Nginx反向代理

```nginx
server {
    listen 80;
    server_name wazuh-proxy.local;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 维护

### 重启服务

```bash
# 如果使用systemd
sudo systemctl restart wazuh-proxy

# 如果直接运行
# Ctrl+C 停止，然后重新运行
python3 wazuh_proxy.py
```

### 停止服务

```bash
# 如果使用systemd
sudo systemctl stop wazuh-proxy

# 如果直接运行
# Ctrl+C 停止
```

### 卸载服务

```bash
# 停止并禁用systemd服务
sudo systemctl stop wazuh-proxy
sudo systemctl disable wazuh-proxy
sudo rm /etc/systemd/system/wazuh-proxy.service
sudo systemctl daemon-reload
```

## 技术栈

- **Flask**: 轻量级Web框架
- **requests**: HTTP客户端库
- **gunicorn**: WSGI HTTP服务器
- **systemd**: 服务管理

## 许可证

MIT License

## 作者

xiejava

## 相关项目

- [AI-miniSOC](https://github.com/xiejava1018/AI-miniSOC) - AI驱动的微型安全运营中心
- [Wazuh](https://documentation.wazuh.com/) - 开源安全平台

---

**最后更新**: 2026-03-09
**版本**: v1.0.0
