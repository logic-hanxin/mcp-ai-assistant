"""
启动 Web 服务

用法:
    python -m assistant.web.run
    python -m assistant.web.run --port 8000 --host 0.0.0.0
"""

import argparse
import uvicorn
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="AI助手 Web 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    args = parser.parse_args()

    # 导入 app 时会自动注册 /onebot 路由
    from assistant.web.api import app  # noqa: F401
    import assistant.web.onebot  # noqa: F401

    print(f"[启动] AI助手 QQ 机器人服务 http://{args.host}:{args.port}")
    print(f"[配置] NapCat 上报地址请设为: http://127.0.0.1:{args.port}/onebot")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
