"""连通性测试模块

为配置中心提供数据源、大模型、告警渠道的连通性检测能力。
每个检测函数返回统一结构: {"success": bool, "message": str, "latency_ms": int}
"""

import time
from typing import Optional

import httpx


def _result(success: bool, message: str, latency_ms: int) -> dict:
    return {"success": success, "message": message, "latency_ms": latency_ms}


def _normalize_host(host: str, port: int, use_ssl: bool = False) -> str:
    """拼接 host:port 并补全 scheme"""
    scheme = "https" if use_ssl else "http"
    host = (host or "").strip()
    if host.startswith(("http://", "https://")):
        return host if port in (0, None) else f"{host.rstrip('/')}"
    return f"{scheme}://{host}:{port}"


async def test_elasticsearch(
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    use_ssl: bool = False,
) -> dict:
    """测试 Elasticsearch 连通性"""
    from elasticsearch import AsyncElasticsearch

    start = time.time()
    url = _normalize_host(host, port, use_ssl)
    client = None
    try:
        kwargs = {"hosts": [url], "request_timeout": 8, "verify_certs": False}
        if username and password:
            kwargs["basic_auth"] = (username, password)
        client = AsyncElasticsearch(**kwargs)
        info = await client.info()
        version = info.get("version", {}).get("number", "unknown")
        cluster = info.get("cluster_name", "")
        return _result(True, f"连接成功 (ES {version}, 集群: {cluster})", int((time.time() - start) * 1000))
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


async def test_mysql(
    host: str,
    port: int,
    username: Optional[str],
    password: Optional[str],
    database: str = "aiops",
) -> dict:
    """测试 MySQL 连通性"""
    import aiomysql

    start = time.time()
    conn = None
    try:
        conn = await aiomysql.connect(
            host=host,
            port=int(port),
            user=username or "",
            password=password or "",
            db=database,
            connect_timeout=8,
        )
        async with conn.cursor() as cur:
            await cur.execute("SELECT VERSION()")
            row = await cur.fetchone()
            ver = row[0] if row else "unknown"
        return _result(True, f"连接成功 (MySQL {ver})", int((time.time() - start) * 1000))
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


async def test_redis(
    host: str,
    port: int,
    password: Optional[str] = None,
    db: int = 0,
) -> dict:
    """测试 Redis 连通性"""
    from redis.asyncio import Redis as AsyncRedis

    start = time.time()
    client = None
    try:
        client = AsyncRedis(
            host=host, port=int(port), password=password or None,
            db=db, socket_connect_timeout=8,
        )
        pong = await client.ping()
        info = await client.info(section="server")
        ver = info.get("redis_version", "unknown") if isinstance(info, dict) else "unknown"
        return _result(
            True if pong else False,
            f"连接成功 (Redis {ver})" if pong else "PING 未返回 PONG",
            int((time.time() - start) * 1000),
        )
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


async def test_llm(api_base: str, api_key: str, model: str) -> dict:
    """测试大模型连通性（发送极简对话请求）"""
    from openai import AsyncOpenAI
    from openai import NotFoundError

    start = time.time()
    if not api_base:
        return _result(False, "API地址不能为空", 0)
    try:
        client = AsyncOpenAI(base_url=api_base, api_key=api_key or "empty", timeout=20)
        # 先尝试获取模型列表，失败再走最小对话请求
        try:
            models = await client.models.list()
            names = [m.id for m in models.data][:5]
            names_str = ", ".join(names) if names else "(空)"
            msg = f"连接成功，可用模型: {names_str}"
            return _result(True, msg, int((time.time() - start) * 1000))
        except Exception:
            pass
        resp = await client.chat.completions.create(
            model=model or "qwen3",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return _result(True, f"连接成功，模型回复: {reply[:50]}", int((time.time() - start) * 1000))
    except NotFoundError as e:
        # 404 通常表示路径或模型名称不存在
        err_body = getattr(e, "body", {}) or {}
        detail = err_body.get("message", "") if isinstance(err_body, dict) else str(err_body)
        hint = ""
        if model:
            hint = f"，请检查模型名称 '{model}' 是否正确（该服务 /v1/models 接口不可用，无法自动枚举模型）"
        return _result(
            False,
            f"连接失败: 404 Not Found{hint}。原始响应: {detail or e}"[:300],
            int((time.time() - start) * 1000),
        )
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))


async def test_dingtalk(webhook_url: str, secret: Optional[str] = None) -> dict:
    """测试钉钉机器人连通性"""
    import hmac
    import hashlib
    import base64
    import urllib.parse

    start = time.time()
    if not webhook_url:
        return _result(False, "Webhook URL 不能为空", 0)

    # 如果配置了加密密钥，生成签名 URL
    url = webhook_url
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "text",
        "text": {"content": "[AIOPS] 连通性测试 ✓"},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            data = {}
            try:
                data = resp.json()
            except Exception:
                pass
            ok = resp.status_code == 200 and data.get("errcode", 0) == 0
            msg = "发送成功" if ok else f"响应异常: {data.get('errmsg') or resp.status_code}"
            return _result(ok, msg, int((time.time() - start) * 1000))
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))


async def test_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: Optional[str] = None,
    smtp_pass: Optional[str] = None,
    from_addr: Optional[str] = None,
    to_addrs=None,
    use_ssl: bool = True,
    send_test: bool = False,
) -> dict:
    """测试邮件 SMTP 连通性（默认只验证登录，不实际发信）"""
    import smtplib
    from email.mime.text import MIMEText

    start = time.time()
    if not smtp_host:
        return _result(False, "SMTP地址不能为空", 0)
    server = None
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port or 465), timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port or 25), timeout=10)
            server.ehlo()
            server.starttls()

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        if send_test and from_addr and to_addrs:
            msg = MIMEText("[AIOPS] 连通性测试 ✓", "plain", "utf-8")
            msg["Subject"] = "AIOPS 连通性测试"
            msg["From"] = from_addr
            recipients = to_addrs if isinstance(to_addrs, list) else [to_addrs]
            msg["To"] = ",".join(recipients)
            server.sendmail(from_addr, recipients, msg.as_string())
            return _result(True, "登录并测试发送成功", int((time.time() - start) * 1000))

        return _result(True, "SMTP 登录验证成功", int((time.time() - start) * 1000))
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


async def test_webhook(url: str, method: str = "POST", headers: Optional[dict] = None) -> dict:
    """测试通用 Webhook 连通性"""
    start = time.time()
    if not url:
        return _result(False, "URL 不能为空", 0)
    headers = headers or {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if (method or "POST").upper() == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(
                    url,
                    json={"text": "[AIOPS] 连通性测试", "msgtype": "text"},
                    headers=headers,
                )
            ok = 200 <= resp.status_code < 300
            return _result(ok, f"响应状态: {resp.status_code}", int((time.time() - start) * 1000))
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))


async def test_prometheus(
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    use_ssl: bool = False,
) -> dict:
    """测试 Prometheus 连通性"""
    start = time.time()
    scheme = "https" if use_ssl else "http"
    if host.startswith(("http://", "https://")):
        base_url = host.rstrip("/")
    else:
        base_url = f"{scheme}://{host}:{port}"

    auth = (username, password) if username and password else None

    try:
        async with httpx.AsyncClient(timeout=10, auth=auth) as client:
            # 1. 健康检查
            health_resp = await client.get(f"{base_url}/-/healthy")
            if health_resp.status_code != 200:
                return _result(False, f"Prometheus 不健康 (HTTP {health_resp.status_code})", int((time.time() - start) * 1000))

            # 2. 查询版本信息
            build_resp = await client.get(f"{base_url}/api/v1/status/buildinfo")
            version = "unknown"
            if build_resp.status_code == 200:
                build_data = build_resp.json()
                version = build_data.get("data", {}).get("version", "unknown")

            # 3. 获取 target 数量
            targets_resp = await client.get(f"{base_url}/api/v1/targets")
            target_count = 0
            up_count = 0
            if targets_resp.status_code == 200:
                targets = targets_resp.json().get("data", {}).get("activeTargets", [])
                target_count = len(targets)
                up_count = sum(1 for t in targets if t.get("health") == "up")

            msg = f"连接成功 (Prometheus {version}, {up_count}/{target_count} targets UP)"
            return _result(True, msg, int((time.time() - start) * 1000))
    except Exception as e:
        return _result(False, f"连接失败: {e}", int((time.time() - start) * 1000))
