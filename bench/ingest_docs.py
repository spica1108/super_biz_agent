"""把 aiops-docs 入库到 Milvus（复用项目的分割与向量化服务）。

用法（项目根目录）：
    .venv/Scripts/python.exe bench/ingest_docs.py [目录路径，默认 aiops-docs]
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "aiops-docs"

    from app.services.vector_index_service import vector_index_service

    result = vector_index_service.index_directory(target)
    print(result.to_dict())
