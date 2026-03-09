#!/usr/bin/env python3
"""
Wazuh API Proxy Service
自动处理JWT token刷新的代理服务
"""

from flask import Flask, request, jsonify, Response
import requests
import time
import logging
import os
from functools import wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('wazuh_proxy.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Wazuh配置
WAZUH_URL = os.getenv('WAZUH_URL', 'https://192.168.0.40:55000')
WAZUH_USER = os.getenv('WAZUH_USER', 'wazuh')
WAZUH_PASSWORD = os.getenv('WAZUH_PASSWORD', '')  # 从环境变量读取，不设置默认值
PROXY_PORT = int(os.getenv('PROXY_PORT', '5000'))
TOKEN_EXPIRE_BUFFER = int(os.getenv('TOKEN_EXPIRE_BUFFER', '60'))  # 提前60秒刷新token

# Token缓存
token_cache = {
    "token": None,
    "expires_at": 0,
    "last_refresh": 0
}

# 创建带重试的session
def create_session():
    """创建带重试策略的requests session"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = create_session()


def get_token(force_refresh=False):
    """
    获取或刷新JWT token
    使用HTTP Basic认证

    Args:
        force_refresh: 是否强制刷新token

    Returns:
        str: JWT token or None
    """
    current_time = time.time()

    # 检查token是否有效
    if not force_refresh and token_cache["token"]:
        if current_time < token_cache["expires_at"]:
            logger.debug(f"使用缓存的token，剩余有效期: {int(token_cache['expires_at'] - current_time)}秒")
            return token_cache["token"]

    # 获取新token - 使用HTTP Basic认证
    logger.info("正在获取新的JWT token...")
    try:
        response = session.post(
            f"{WAZUH_URL}/security/user/authenticate",
            auth=(WAZUH_USER, WAZUH_PASSWORD),  # HTTP Basic认证
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            # 从响应的data.token字段提取token
            data = response.json()
            if 'data' in data and 'token' in data['data']:
                token = data['data']['token']
                # 设置token过期时间（15分钟 = 900秒）
                token_cache["token"] = token
                token_cache["expires_at"] = current_time + 900 - TOKEN_EXPIRE_BUFFER
                token_cache["last_refresh"] = current_time
                logger.info(f"✅ Token获取成功，将在{int(900 - TOKEN_EXPIRE_BUFFER)}秒后刷新")
                return token
            else:
                logger.error(f"❌ 响应格式错误: {data}")
                return None
        else:
            logger.error(f"❌ 获取token失败，状态码: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
            return None

    except Exception as e:
        logger.error(f"❌ 获取token时发生错误: {str(e)}")
        return None


def handle_errors(f):
    """错误处理装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"处理请求时发生错误: {str(e)}")
            return jsonify({
                "error": "Internal server error",
                "message": str(e)
            }), 500
    return decorated_function


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    token_valid = token_cache["token"] and time.time() < token_cache["expires_at"]
    return jsonify({
        "status": "healthy",
        "token_valid": token_valid,
        "token_expires_at": token_cache["expires_at"],
        "wazuh_url": WAZUH_URL
    })


@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    """手动刷新token端点"""
    token = get_token(force_refresh=True)
    if token:
        return jsonify({
            "status": "success",
            "message": "Token refreshed successfully"
        })
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to refresh token"
        }), 500


@app.route('/token-info', methods=['GET'])
def token_info():
    """获取当前token信息"""
    current_time = time.time()
    return jsonify({
        "token_exists": token_cache["token"] is not None,
        "expires_at": token_cache["expires_at"],
        "time_remaining": max(0, int(token_cache["expires_at"] - current_time)) if token_cache["expires_at"] > 0 else 0,
        "last_refresh": token_cache["last_refresh"],
        "wazuh_url": WAZUH_URL
    })


@app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@handle_errors
def proxy_root():
    """代理根路径请求"""
    return proxy_path("")


@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@handle_errors
def proxy_path(path):
    """
    代理Wazuh API请求

    Args:
        path: API路径

    Returns:
        Response: 代理的响应
    """
    # 获取token
    token = get_token()
    if not token:
        return jsonify({
            "error": "Failed to authenticate with Wazuh API"
        }), 503

    # 构建目标URL
    url = f"{WAZUH_URL}/{path}"

    # 添加查询参数
    if request.query_string:
        url += f"?{request.query_string.decode()}"

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 记录请求
    logger.info(f"➡️  {request.method} {url}")

    # 转发请求
    try:
        resp = session.request(
            method=request.method,
            url=url,
            headers=headers,
            json=request.get_json() if request.method in ['POST', 'PUT', 'PATCH'] and request.get_json() else None,
            data=request.get_data() if request.method in ['POST', 'PUT', 'PATCH'] and not request.get_json() else None,
            verify=False,
            timeout=30,
            stream=True
        )

        logger.info(f"⬅️  {request.method} {url} - Status: {resp.status_code}")

        # 流式返回响应
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]

        return Response(
            resp.iter_content(chunk_size=1024),
            status=resp.status_code,
            headers=headers
        )

    except requests.exceptions.Timeout:
        logger.error(f"请求超时: {url}")
        return jsonify({"error": "Request timeout"}), 504
    except Exception as e:
        logger.error(f"请求失败: {str(e)}")
        return jsonify({"error": str(e)}), 502


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Wazuh API Proxy 服务启动")
    logger.info("=" * 60)
    logger.info(f"📡 监听端口: {PROXY_PORT}")
    logger.info(f"🔗 Wazuh URL: {WAZUH_URL}")
    logger.info(f"👤 Wazuh User: {WAZUH_USER}")
    logger.info("=" * 60)

    # 启动时预先获取token
    logger.info("正在初始化token...")
    if get_token():
        logger.info("✅ Token初始化成功")
    else:
        logger.warning("⚠️  Token初始化失败，将在首次请求时重试")

    # 启动Flask应用
    # 注意：生产环境建议使用gunicorn
    app.run(
        host='0.0.0.0',
        port=PROXY_PORT,
        debug=False,
        ssl_context=None  # 如需HTTPS，设置为('cert.pem', 'key.pem')
    )
