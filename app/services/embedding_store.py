from __future__ import annotations

import os
import tempfile
from pathlib import Path

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


embedding_store = EmbeddingStore()
