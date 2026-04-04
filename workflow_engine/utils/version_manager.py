from pathlib import Path
from typing import List, Optional, Tuple
import re
import time
import shutil
import json
import os


class ImageVersionManager:
    """Manages versioned storage for slide images"""

    MAX_VERSIONS = int(os.getenv("MAX_IMAGE_VERSIONS", "10"))  # Configurable via environment variables

    @staticmethod
    def get_next_version_number(img_dir: Path, page_idx: int) -> int:
        """Scans the directory for existing versions and returns the next version number"""
        pattern = f"page_{page_idx:03d}_v*.png"
        existing = list(img_dir.glob(pattern))
        if not existing:
            return 1

        version_nums = []
        for f in existing:
            match = re.search(r'_v(\d+)\.png$', f.name)
            if match:
                version_nums.append(int(match.group(1)))

        return max(version_nums) + 1 if version_nums else 1

    @staticmethod
    def save_versioned_image(
        img_dir: Path,
        page_idx: int,
        new_image_path: str,
        prompt: str = ""
    ) -> Tuple[str, int]:
        """
        Saves a new version and updates the current pointer.

        Args:
            img_dir: Image directory path
            page_idx: Page index
            new_image_path: New image path
            prompt: User's edit prompt

        Returns:
            (versioned_path, version_number): A tuple of (versioned_path, version_number)
        """
        # Check if it's the first edit (original version needs to be kept)
        current_path = img_dir / f"page_{page_idx:03d}.png"
        version_num = ImageVersionManager.get_next_version_number(img_dir, page_idx)

        # Special case: If this is version 1, save the current image as v001 first
        if version_num == 1 and current_path.exists():
            v001_path = img_dir / f"page_{page_idx:03d}_v001.png"
            shutil.copy2(current_path, v001_path)
            # Save metadata for the original version
            ImageVersionManager._save_version_metadata(
                img_dir, page_idx, 1, "Initial generation"
            )
            version_num = 2  # The new edit becomes v002

        # Save as a versioned file
        versioned_name = f"page_{page_idx:03d}_v{version_num:03d}.png"
        versioned_path = img_dir / versioned_name
        shutil.copy2(new_image_path, versioned_path)

        # Update the current pointer (copy instead of symlink for Windows compatibility)
        shutil.copy2(new_image_path, current_path)

        # Clean up old versions that exceed the limit
        ImageVersionManager._cleanup_old_versions(img_dir, page_idx)

        # Save metadata
        ImageVersionManager._save_version_metadata(
            img_dir, page_idx, version_num, prompt
        )

        return str(versioned_path), version_num

    @staticmethod
    def _cleanup_old_versions(img_dir: Path, page_idx: int):
        """Delete versions that exceed the MAX_VERSIONS limit"""
        pattern = f"page_{page_idx:03d}_v*.png"
        versions = sorted(img_dir.glob(pattern))

        if len(versions) > ImageVersionManager.MAX_VERSIONS:
            to_delete = versions[:-ImageVersionManager.MAX_VERSIONS]
            for old_file in to_delete:
                old_file.unlink()
                # Also delete the corresponding metadata
                meta_file = old_file.with_suffix('.json')
                if meta_file.exists():
                    meta_file.unlink()

    @staticmethod
    def _save_version_metadata(
        img_dir: Path,
        page_idx: int,
        version_num: int,
        prompt: str
    ):
        """Save the metadata JSON for this version"""
        meta_file = img_dir / f"page_{page_idx:03d}_v{version_num:03d}.json"
        metadata = {
            "version": version_num,
            "page_index": page_idx,
            "prompt": prompt,
            "timestamp": int(time.time())
        }
        meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    @staticmethod
    def get_version_history(img_dir: Path, page_idx: int) -> List[dict]:
        """Retrieve all versions and metadata for the page"""
        pattern = f"page_{page_idx:03d}_v*.png"
        versions = sorted(img_dir.glob(pattern))

        history = []
        for img_file in versions:
            meta_file = img_file.with_suffix('.json')
            if meta_file.exists():
                try:
                    metadata = json.loads(meta_file.read_text())
                except json.JSONDecodeError:
                    # Fall back if metadata is missing or corrupted
                    match = re.search(r'_v(\d+)\.png$', img_file.name)
                    version_num = int(match.group(1)) if match else 0
                    metadata = {
                        "version": version_num,
                        "page_index": page_idx,
                        "prompt": "",
                        "timestamp": int(img_file.stat().st_mtime)
                    }
            else:
                # Fall back if metadata is missing
                match = re.search(r'_v(\d+)\.png$', img_file.name)
                version_num = int(match.group(1)) if match else 0
                metadata = {
                    "version": version_num,
                    "page_index": page_idx,
                    "prompt": "",
                    "timestamp": int(img_file.stat().st_mtime)
                }

            metadata["image_path"] = str(img_file)
            history.append(metadata)

        return history

    @staticmethod
    def revert_to_version(
        img_dir: Path,
        page_idx: int,
        target_version: int
    ) -> Optional[str]:
        """Revert the current image to a specific version"""
        versioned_file = img_dir / f"page_{page_idx:03d}_v{target_version:03d}.png"

        if not versioned_file.exists():
            return None

        current_path = img_dir / f"page_{page_idx:03d}.png"
        shutil.copy2(versioned_file, current_path)

        return str(current_path)
