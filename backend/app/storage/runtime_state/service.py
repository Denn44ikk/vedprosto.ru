from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


class RuntimeStateService:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _default_state(self) -> dict[str, Any]:
        return {
            "workspace": {
                "active_root_path": "",
                "roots": {},
            },
        }

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            if not self.state_path.exists():
                state = self._default_state()
                self._save_state(state)
                return state

            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                state = self._default_state()
                self._save_state(state)
                return state

            self._ensure_workspace_state(state)
            return state

    @staticmethod
    def _ensure_workspace_state(state: dict[str, Any]) -> None:
        workspace = state.get("workspace")
        if not isinstance(workspace, dict):
            workspace = {}
            state["workspace"] = workspace
        if "active_root_path" not in workspace or not isinstance(workspace.get("active_root_path"), str):
            workspace["active_root_path"] = ""
        if "roots" not in workspace or not isinstance(workspace.get("roots"), dict):
            workspace["roots"] = {}

    def _save_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            self.state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def ensure_workspace_root(self, root_path: str) -> None:
        with self._lock:
            state = self.get_state()
            self._ensure_workspace_state(state)
            roots = state["workspace"]["roots"]
            if root_path not in roots or not isinstance(roots.get(root_path), dict):
                roots[root_path] = {
                    "current_case_id": "",
                    "cases": {},
                }
                self._save_state(state)

    def get_active_case_root_path(self) -> str:
        with self._lock:
            state = self.get_state()
            return str(state["workspace"]["active_root_path"])

    def set_active_case_root_path(self, root_path: str) -> None:
        with self._lock:
            state = self.get_state()
            self._ensure_workspace_state(state)
            if root_path:
                roots = state["workspace"]["roots"]
                if root_path not in roots or not isinstance(roots.get(root_path), dict):
                    roots[root_path] = {
                        "current_case_id": "",
                        "cases": {},
                    }
            state["workspace"]["active_root_path"] = root_path
            self._save_state(state)

    def remove_workspace_root(self, root_path: str) -> None:
        with self._lock:
            state = self.get_state()
            self._ensure_workspace_state(state)
            roots = state["workspace"]["roots"]
            roots.pop(root_path, None)
            if str(state["workspace"].get("active_root_path", "")) == root_path:
                state["workspace"]["active_root_path"] = ""
            self._save_state(state)

    def get_current_case_id(self, root_path: str) -> str:
        with self._lock:
            state = self.get_state()
            root_state = state["workspace"]["roots"].get(root_path) or {}
            return str(root_state.get("current_case_id", ""))

    def set_current_case_id(self, root_path: str, case_id: str) -> None:
        with self._lock:
            state = self.get_state()
            self._ensure_workspace_state(state)
            roots = state["workspace"]["roots"]
            if root_path not in roots or not isinstance(roots.get(root_path), dict):
                roots[root_path] = {
                    "current_case_id": "",
                    "cases": {},
                }
            roots[root_path]["current_case_id"] = case_id
            self._save_state(state)

    def get_case_flags(self, root_path: str, case_id: str) -> dict[str, Any]:
        with self._lock:
            state = self.get_state()
            root_state = state["workspace"]["roots"].get(root_path) or {}
            cases = root_state.get("cases") if isinstance(root_state.get("cases"), dict) else {}
            case_state = cases.get(case_id) if isinstance(cases, dict) else {}
            return dict(case_state or {})

    def set_case_flag(self, root_path: str, case_id: str, key: str, value: Any) -> None:
        with self._lock:
            state = self.get_state()
            self._ensure_workspace_state(state)
            roots = state["workspace"]["roots"]
            if root_path not in roots or not isinstance(roots.get(root_path), dict):
                roots[root_path] = {
                    "current_case_id": "",
                    "cases": {},
                }
            root_state = roots[root_path]
            cases = root_state.get("cases")
            if not isinstance(cases, dict):
                cases = {}
                root_state["cases"] = cases
            if case_id not in cases or not isinstance(cases.get(case_id), dict):
                cases[case_id] = {}
            cases[case_id][key] = value
            self._save_state(state)
