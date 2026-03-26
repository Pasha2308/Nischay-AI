from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from shared.models.visual_baseline import BaselineEntry, VisualBaselineRegistry


class VisualBaselineRegistryManager:
    def __init__(self, registry_path: Path, baselines_dir: Path, target_url: str):
        self.registry_path = registry_path
        self.baselines_dir = baselines_dir
        self.target_url = target_url

    def load(self) -> VisualBaselineRegistry:
        if not self.registry_path.exists():
            return VisualBaselineRegistry(target_url=self.target_url)
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return VisualBaselineRegistry(**data)

    def save(self, registry: VisualBaselineRegistry) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        registry.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(registry.model_dump(), f, indent=2, default=str)

    @staticmethod
    def _key(page_id: str, viewport_name: str) -> str:
        return f"{page_id}__{viewport_name}"

    def get_baseline(self, registry: VisualBaselineRegistry, page_id: str, viewport_name: str) -> BaselineEntry | None:
        return registry.baselines.get(self._key(page_id, viewport_name))

    def get_baseline_image_path(self, entry: BaselineEntry) -> Path:
        return self.baselines_dir / entry.image_path

    def store_baseline(
        self,
        registry: VisualBaselineRegistry,
        page_id: str,
        viewport_name: str,
        viewport_width: int,
        viewport_height: int,
        source_image_path: Path,
        run_id: str,
    ) -> None:
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        rel_name = f"{page_id}__{viewport_name}.png"
        dest = self.baselines_dir / rel_name
        dest.write_bytes(source_image_path.read_bytes())
        h = hashlib.sha256(dest.read_bytes()).hexdigest()

        registry.baselines[self._key(page_id, viewport_name)] = BaselineEntry(
            page_id=page_id,
            viewport_name=viewport_name,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            image_path=rel_name,
            captured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            run_id=run_id,
            image_hash=h,
        )

