from __future__ import annotations

import os
import tempfile
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np


class EmbeddingStore:
    """Store embeddings with owner-only directory and file permissions."""

    def __init__(self, root: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[2]
        configured_root = os.getenv("FACE_EMBEDDING_DIR")
        if root is not None:
            self.root = root
        elif configured_root:
            self.root = Path(configured_root)
        else:
            self.root = project_root / "db" / "users"

    def path_for(self, user_id: int) -> Path:
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        return self.root / str(user_id) / "license_embedding.npy"

    def save(self, user_id: int, embedding: np.ndarray) -> Path:
        path = self.path_for(user_id)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        path.parent.mkdir(exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".license_embedding.",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                np.save(file, embedding, allow_pickle=False)
            os.replace(temporary_name, path)
            os.chmod(path, 0o600)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return path

    def load(self, user_id: int) -> np.ndarray | None:
        path = self.path_for(user_id)
        if not path.exists():
            return None
        os.chmod(path, 0o600)
        return np.load(path, allow_pickle=False)

    def delete(self, user_id: int) -> bool:
        path = self.path_for(user_id)
        if not path.exists():
            return False
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return True


class NodeEmbeddingStore:
    """Store encrypted embeddings in the Node/PostgreSQL backend."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = os.getenv("INTERNAL_API_KEY", "").strip()
        self.device_id = os.getenv("KICKBOARD_DEVICE_ID", "").strip()
        self.timeout = float(os.getenv("NODE_EMBEDDING_TIMEOUT_SECONDS", "3"))

    def path_for(self, user_id: int) -> str:
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        return f"{self.base_url}/{user_id}"

    def _request(self, user_id: int, method: str, payload: dict | None = None):
        headers = {
            "Accept": "application/json",
            "X-Internal-Api-Key": self.api_key,
        }
        if method == "GET":
            headers["X-Device-Id"] = self.device_id
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = Request(self.path_for(user_id), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(
                f"Node embedding API returned HTTP {error.code}"
            ) from error
        except (URLError, OSError, ValueError) as error:
            raise RuntimeError("Node embedding API request failed") from error

    def save(self, user_id: int, embedding: np.ndarray) -> str:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        response = self._request(
            user_id,
            "PUT",
            {"embedding": vector.tolist(), "model_name": "buffalo_sc"},
        )
        if response is None or response.get("status") != "success":
            raise RuntimeError("Node embedding API did not save the embedding")
        return self.path_for(user_id)

    def load(self, user_id: int) -> np.ndarray | None:
        response = self._request(user_id, "GET")
        if response is None:
            return None
        data = response.get("data") or {}
        if data.get("model_name") != "buffalo_sc":
            raise RuntimeError("Stored face model does not match buffalo_sc")
        embedding = data.get("embedding")
        dimension = data.get("dimension")
        if not isinstance(embedding, list) or len(embedding) != dimension:
            raise RuntimeError("Node embedding API returned an invalid embedding")
        return np.asarray(embedding, dtype=np.float32)

    def delete(self, user_id: int) -> bool:
        response = self._request(user_id, "DELETE")
        if response is None:
            return False
        return bool((response.get("data") or {}).get("deleted"))


def _create_embedding_store():
    node_url = os.getenv("NODE_FACE_EMBEDDING_URL", "").strip()
    if node_url:
        return NodeEmbeddingStore(node_url)
    return EmbeddingStore()


embedding_store = _create_embedding_store()
