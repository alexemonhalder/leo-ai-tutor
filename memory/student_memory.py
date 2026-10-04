"""Tiny persistent memory: who the student is, what they studied, what they
struggled with. Stored as JSON in data/ so it survives restarts."""

import json
import threading
import time
from pathlib import Path
from typing import Dict, List

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "student_memory.json"


class StudentMemory:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ---------- storage helpers ----------
    def _load(self) -> Dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: Dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _key(name: str) -> str:
        return name.strip().lower()

    # ---------- public API ----------
    def get(self, name: str) -> Dict:
        data = self._load()
        return data.get(
            self._key(name),
            {"name": name.strip(), "sessions": [], "weak_concepts": []},
        )

    def record_result(
        self, name: str, topic: str, level: str, score: int, total: int,
        weak_concepts: List[str],
    ) -> None:
        with self._lock:
            data = self._load()
            key = self._key(name)
            profile = data.get(
                key, {"name": name.strip(), "sessions": [], "weak_concepts": []}
            )
            profile["sessions"].append(
                {
                    "topic": topic,
                    "level": level,
                    "score": score,
                    "total": total,
                    "time": time.strftime("%Y-%m-%d %H:%M"),
                }
            )
            profile["sessions"] = profile["sessions"][-20:]
            # keep recent weak concepts; drop ones just answered correctly
            merged = list(dict.fromkeys(weak_concepts + profile["weak_concepts"]))
            profile["weak_concepts"] = merged[:10]
            data[key] = profile
            self._save(data)

    def clear_weak(self, name: str, concepts: List[str]) -> None:
        with self._lock:
            data = self._load()
            key = self._key(name)
            if key in data:
                data[key]["weak_concepts"] = [
                    c for c in data[key]["weak_concepts"] if c not in concepts
                ]
                self._save(data)

    def summary(self, name: str) -> str:
        """Short text injected into agent prompts."""
        p = self.get(name)
        if not p["sessions"]:
            return "New student, no history yet."
        recent = p["sessions"][-3:]
        history = "; ".join(
            f"{s['topic']} ({s['score']}/{s['total']})" for s in recent
        )
        weak = ", ".join(p["weak_concepts"][:5]) or "none"
        return f"Recent topics: {history}. Known weak concepts: {weak}."