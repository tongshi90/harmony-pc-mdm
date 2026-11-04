"""启动入口: python run.py

开发请优先使用 start.ps1（会先清理 8080 旧进程再启动）。
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=["app"],
    )
