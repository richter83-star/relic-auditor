from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .detectors import classify_role, is_high_signal
from .models import FileRecord, ScanLimits
from .safety import (
    IGNORED_DIRECTORIES,
    JUNK_FILES,
    is_binary_name,
    is_safe_zip_member,
    likely_binary,
    redact_secrets,
)


class EstateScanner:
    def __init__(self, target: Path, limits: ScanLimits, include_hidden: bool = False):
        self.target = target.resolve()
        self.limits = limits
        self.include_hidden = include_hidden
        self.files: list[FileRecord] = []
        self.archives: list[dict[str, object]] = []
        self.ignored: list[dict[str, str]] = []
        self.warnings: list[str] = []
        self.samples: list[dict[str, object]] = []

    def scan(self) -> tuple[
        list[FileRecord],
        list[dict[str, object]],
        list[dict[str, str]],
        list[str],
        list[dict[str, object]],
    ]:
        if not self.target.exists():
            raise FileNotFoundError(f"Target does not exist: {self.target}")
        if not self.target.is_dir():
            raise NotADirectoryError(f"Target must be a folder: {self.target}")

        for root, directory_names, file_names in os.walk(self.target, topdown=True, followlinks=False):
            root_path = Path(root)
            kept_directories: list[str] = []
            for name in sorted(directory_names):
                path = root_path / name
                relative = self._relative(path)
                reason = self._directory_skip_reason(path, name)
                if reason:
                    self.ignored.append({"path": relative, "reason": reason, "kind": "directory"})
                else:
                    kept_directories.append(name)
            directory_names[:] = kept_directories

            for name in sorted(file_names):
                path = root_path / name
                relative = self._relative(path)
                if path.is_symlink():
                    self.ignored.append({"path": relative, "reason": "symbolic link", "kind": "file"})
                    continue
                if name in JUNK_FILES:
                    self.ignored.append({"path": relative, "reason": "known junk file", "kind": "file"})
                    continue
                if not self.include_hidden and name.startswith(".") and name != ".env.example":
                    self.ignored.append({"path": relative, "reason": "hidden file", "kind": "file"})
                    continue
                self._scan_file(path, relative)

        self.files.sort(key=lambda item: item.path)
        self.archives.sort(key=lambda item: str(item["path"]))
        self.ignored.sort(key=lambda item: (item["path"], item["kind"]))
        self.samples.sort(key=lambda item: str(item["path"]))
        return self.files, self.archives, self.ignored, sorted(self.warnings), self.samples

    def _scan_file(self, path: Path, relative: str) -> None:
        try:
            size = path.stat().st_size
        except OSError as exc:
            self.warnings.append(f"Could not stat {relative}: {exc}")
            return

        if path.suffix.lower() == ".zip":
            self._scan_zip(path, relative, size)
            return

        record = FileRecord(
            path=relative,
            size=size,
            extension=path.suffix.lower(),
            role=classify_role(relative),
        )
        if size > self.limits.max_file_bytes:
            record.warnings.append("file exceeds content inspection limit")
            self.files.append(record)
            return

        try:
            data = path.read_bytes()
        except OSError as exc:
            record.warnings.append(f"could not read: {exc}")
            self.files.append(record)
            return

        record.sha256 = hashlib.sha256(data).hexdigest()
        if not is_binary_name(relative) and not likely_binary(data):
            record.text = data.decode("utf-8", errors="replace")
            if is_high_signal(relative):
                self.samples.append(self._sample(relative, record.text, size, "filesystem"))
        self.files.append(record)

    def _scan_zip(self, path: Path, relative: str, size: int) -> None:
        archive: dict[str, object] = {
            "path": relative,
            "compressed_bytes": size,
            "status": "inspected",
            "members": 0,
            "safe_members": 0,
            "unsafe_members": [],
            "uncompressed_bytes": 0,
            "warnings": [],
        }
        try:
            with zipfile.ZipFile(path) as bundle:
                infos = sorted(bundle.infolist(), key=lambda info: info.filename)
                archive["members"] = len(infos)
                if len(infos) > self.limits.max_zip_members:
                    archive["status"] = "rejected"
                    archive["warnings"].append("member count exceeds safety limit")  # type: ignore[union-attr]
                    self.archives.append(archive)
                    return

                total = sum(info.file_size for info in infos)
                archive["uncompressed_bytes"] = total
                if total > self.limits.max_zip_uncompressed_bytes:
                    archive["status"] = "rejected"
                    archive["warnings"].append("uncompressed size exceeds safety limit")  # type: ignore[union-attr]
                    self.archives.append(archive)
                    return

                for info in infos:
                    if info.is_dir():
                        continue
                    safe, reason = is_safe_zip_member(info.filename)
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        safe, reason = False, "symbolic link member"
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > self.limits.max_zip_ratio:
                        safe, reason = False, "suspicious compression ratio"
                    if info.flag_bits & 0x1:
                        safe, reason = False, "encrypted member"
                    if not safe:
                        archive["unsafe_members"].append(  # type: ignore[union-attr]
                            {"path": info.filename, "reason": reason}
                        )
                        continue

                    archive["safe_members"] = int(archive["safe_members"]) + 1
                    virtual_path = f"{relative}!{info.filename.replace(chr(92), '/')}"
                    member = FileRecord(
                        path=virtual_path,
                        size=info.file_size,
                        extension=PurePosixPath(info.filename).suffix.lower(),
                        source="zip",
                        archive_path=relative,
                        role=classify_role(info.filename),
                    )
                    if (
                        info.file_size <= self.limits.max_file_bytes
                        and not is_binary_name(info.filename)
                        and self._zip_member_worth_reading(info.filename)
                    ):
                        try:
                            data = bundle.read(info)
                        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                            member.warnings.append(f"could not read member: {exc}")
                        else:
                            member.sha256 = hashlib.sha256(data).hexdigest()
                            if not likely_binary(data):
                                member.text = data.decode("utf-8", errors="replace")
                                if is_high_signal(info.filename):
                                    self.samples.append(
                                        self._sample(virtual_path, member.text, info.file_size, "zip")
                                    )
                    elif info.file_size > self.limits.max_file_bytes:
                        member.warnings.append("member exceeds content inspection limit")
                    self.files.append(member)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            archive["status"] = "invalid"
            archive["warnings"].append(str(exc))  # type: ignore[union-attr]
        self.archives.append(archive)

    def _directory_skip_reason(self, path: Path, name: str) -> str | None:
        if path.is_symlink():
            return "symbolic link"
        if name in IGNORED_DIRECTORIES:
            return "generated, dependency, cache, or VCS directory"
        if not self.include_hidden and name.startswith("."):
            return "hidden directory"
        return None

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.target).as_posix()

    def _sample(self, path: str, text: str, size: int, source: str) -> dict[str, object]:
        preview = redact_secrets(text[: self.limits.max_sample_bytes])
        return {
            "path": path,
            "source": source,
            "size": size,
            "preview": preview,
            "truncated": len(text.encode("utf-8")) > self.limits.max_sample_bytes,
        }

    @staticmethod
    def _zip_member_worth_reading(name: str) -> bool:
        pure = PurePosixPath(name)
        if any(part in IGNORED_DIRECTORIES for part in pure.parts):
            return False
        return is_high_signal(name) or pure.suffix.lower() in {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".json",
            ".toml",
            ".yaml",
            ".yml",
            ".md",
            ".txt",
        }
