"""pgvector 人脸特征向量存储: 单独存 PostgreSQL, 不混入 MySQL 业务库"""

from __future__ import annotations

import logging
import os

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from config import (
    PG_HOST,
    PG_PORT,
    PG_USER,
    PG_PASSWORD,
    PG_DATABASE,
    MATCH_THRESHOLD,
    EMPLOYEES_DIR,
)

logger = logging.getLogger(__name__)

TABLE_NAME = "face_embeddings"
EMBEDDING_DIM = 512


class VectorDB:
    """pgvector 人脸特征库: 存储 & 向量相似度搜索"""

    def __init__(self):
        self._conn = self._create_conn()
        self._ensure_db()
        self._init_table()

    @staticmethod
    def _create_conn(database: str | None = None) -> psycopg2.extensions.connection:
        kwargs = dict(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
        )
        if database:
            kwargs["dbname"] = database
        conn = psycopg2.connect(**kwargs)
        conn.autocommit = True
        return conn

    def _ensure_db(self):
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DATABASE,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {PG_DATABASE}")
        cur.close()
        self._conn.close()
        self._conn = self._create_conn(database=PG_DATABASE)
        register_vector(self._conn)

    def _ensure_conn(self):
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        except Exception:
            self._conn = self._create_conn(database=PG_DATABASE)
            register_vector(self._conn)

    def _init_table(self):
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id              SERIAL PRIMARY KEY,
                employee_name   VARCHAR(255) NOT NULL,
                embedding       vector({EMBEDDING_DIM}),
                angle           VARCHAR(10) NOT NULL,
                photo_path      VARCHAR(500),
                created_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_name
            ON {TABLE_NAME} (employee_name)
        """)
        cur.close()
        logger.info("pgvector 就绪: %s:%s/%s", PG_HOST, PG_PORT, PG_DATABASE)

    def _create_hnsw_index(self):
        self._ensure_conn()
        cur = self._conn.cursor()
        try:
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_embedding_hnsw
                ON {TABLE_NAME}
                USING hnsw (embedding vector_cosine_ops)
            """)
        except Exception:
            logger.warning("HNSW 索引创建失败, 可能是 pgvector 版本不支持")
        cur.close()

    def upsert_employee(
        self,
        name: str,
        embeddings: list[tuple[np.ndarray, str, str]],
    ) -> None:
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(f"DELETE FROM {TABLE_NAME} WHERE employee_name = %s", (name,))
        for embedding, angle, photo_path in embeddings:
            cur.execute(
                f"INSERT INTO {TABLE_NAME} (employee_name, embedding, angle, photo_path) "
                "VALUES (%s, %s, %s, %s)",
                (name, embedding.tolist(), angle, photo_path),
            )
        cur.close()
        logger.info("pgvector 写入: %s (%d 条向量)", name, len(embeddings))

    def search(self, embedding: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(
            f"SELECT employee_name, 1 - (embedding <=> %s::vector) AS similarity "
            f"FROM {TABLE_NAME} "
            "ORDER BY embedding <=> %s::vector "
            "LIMIT %s",
            (embedding.tolist(), embedding.tolist(), top_k),
        )
        rows = cur.fetchall()
        cur.close()
        return [(r[0], float(r[1])) for r in rows if float(r[1]) >= MATCH_THRESHOLD]

    def get_all_grouped(self) -> list[tuple[str, np.ndarray]]:
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(
            f"SELECT employee_name, AVG(embedding::vector)::vector "
            f"FROM {TABLE_NAME} GROUP BY employee_name"
        )
        rows = cur.fetchall()
        cur.close()
        result = []
        for name, emb in rows:
            if isinstance(emb, str):
                arr = np.fromstring(emb.strip("[]"), sep=",", dtype=np.float32)
            elif isinstance(emb, list):
                arr = np.array(emb, dtype=np.float32)
            else:
                arr = np.array(emb, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            result.append((name, arr))
        return result

    def list_employees(self) -> list[str]:
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(
            f"SELECT DISTINCT employee_name FROM {TABLE_NAME} ORDER BY employee_name"
        )
        rows = cur.fetchall()
        cur.close()
        return [r[0] for r in rows]

    def delete_employee(self, name: str) -> None:
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(f"DELETE FROM {TABLE_NAME} WHERE employee_name = %s", (name,))
        cur.close()
        photo_dir = os.path.join(EMPLOYEES_DIR, name)
        if os.path.exists(photo_dir):
            import shutil

            shutil.rmtree(photo_dir, ignore_errors=True)

    def __len__(self) -> int:
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(f"SELECT COUNT(DISTINCT employee_name) FROM {TABLE_NAME}")
        count = cur.fetchone()[0]
        cur.close()
        return count
