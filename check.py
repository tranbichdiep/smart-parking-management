#!/usr/bin/env python3
"""Tạo báo cáo thống kê cho toàn bộ thư mục dự án (phục vụ đồ án tốt nghiệp).

- Đếm dòng code (bỏ dòng trống), file mã nguồn, lớp, gói (python/node/java/go/rust).
- Tính dung lượng mã nguồn và dung lượng toàn bộ repo.
- Liệt kê các sản phẩm đóng gói (artifact) kèm dung lượng.
- In báo cáo dạng bảng và lưu JSON ở project_stats.json.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

EXCLUDE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    ".vscode",
    ".idea",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".cache",
    "target",
    "out",
}

# Map module hiển thị -> đường dẫn tương ứng (cho phép module lồng nhau)
MODULE_ALIASES = {
    "database": Path("software/database"),
}

# Các dạng file “đóng gói / sản phẩm build” phổ biến
ARTIFACT_EXTS = {".zip", ".whl", ".jar", ".war", ".bin", ".hex", ".elf", ".exe", ".apk"}
ARTIFACT_SUFFIXES = [".tar.gz", ".tar.bz2", ".tar.xz"]

# Các loại file được coi là mã nguồn
SOURCE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".kt",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".hh",
    ".cs",
    ".go",
    ".rs",
    ".php",
    ".rb",
    ".swift",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".ino",
}

# Regex đếm lớp cho các ngôn ngữ không phải Python
CLASS_REGEX = {
    ".js": r"\bclass\s+\w+",
    ".ts": r"\bclass\s+\w+",
    ".jsx": r"\bclass\s+\w+",
    ".tsx": r"\bclass\s+\w+",
    ".java": r"\b(class|interface|enum)\s+\w+",
    ".kt": r"\b(class|object|interface)\s+\w+",
    ".cs": r"\b(class|interface|struct)\s+\w+",
    ".cpp": r"\bclass\s+\w+",
    ".cc": r"\bclass\s+\w+",
    ".cxx": r"\bclass\s+\w+",
    ".hpp": r"\bclass\s+\w+",
    ".hh": r"\bclass\s+\w+",
    ".h": r"\bclass\s+\w+",
    ".php": r"\bclass\s+\w+",
    ".swift": r"\b(class|struct|enum)\s+\w+",
    ".rb": r"\bclass\s+\w+",
}

LANGUAGE_LABELS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JSX",
    ".tsx": "TSX",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".hh": "C/C++ Header",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".md": "Markdown",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".xml": "XML",
    ".ino": "Arduino",
}


def human(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.2f} {u}"
        f /= 1024.0
    return f"{f:.2f} EB"


def should_skip_dir(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if should_skip_dir(p.parent):
            continue
        yield p


def count_loc(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def count_classes(path: Path) -> int:
    ext = path.suffix.lower()
    if ext == ".py":
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            return sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
        except Exception:
            return 0

    pattern = CLASS_REGEX.get(ext)
    if not pattern:
        return 0

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return len(re.findall(pattern, text))


def scan_path(root: Path) -> Dict[str, object]:
    if not root.exists():
        return {
            "exists": False,
            "all_files": 0,
            "total_size_bytes": 0,
            "source_files": 0,
            "source_size_bytes": 0,
            "loc": 0,
            "classes": 0,
            "per_extension": {},
        }

    total_size = 0
    source_size = 0
    source_files = 0
    loc = 0
    classes = 0
    per_ext: Dict[str, Dict[str, int]] = {}
    all_files = 0

    for file_path in iter_files(root):
        all_files += 1
        try:
            size = file_path.stat().st_size
        except OSError:
            continue

        total_size += size
        ext = file_path.suffix.lower()

        if ext in SOURCE_EXTS:
            source_size += size
            source_files += 1

            file_loc = count_loc(file_path)
            loc += file_loc

            per_ext.setdefault(ext, {"files": 0, "loc": 0, "size_bytes": 0})
            per_ext[ext]["files"] += 1
            per_ext[ext]["loc"] += file_loc
            per_ext[ext]["size_bytes"] += size

            classes += count_classes(file_path)

    return {
        "exists": True,
        "all_files": all_files,
        "total_size_bytes": total_size,
        "source_files": source_files,
        "source_size_bytes": source_size,
        "loc": loc,
        "classes": classes,
        "per_extension": per_ext,
    }


def discover_modules(root: Path) -> Dict[str, Path]:
    modules: Dict[str, Path] = {name: root / rel for name, rel in MODULE_ALIASES.items()}
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name in EXCLUDE_DIRS:
            continue
        modules.setdefault(child.name, child)
    return modules


def discover_packages(root: Path) -> Dict[str, int]:
    python_pkg = set()
    node_pkg = set()
    java_pkg = set()
    go_pkg = set()
    rust_pkg = set()

    for p in iter_files(root):
        name = p.name
        if name == "__init__.py":
            python_pkg.add(str(p.parent))
        elif name == "package.json":
            node_pkg.add(str(p.parent))
        elif name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
            java_pkg.add(str(p.parent))
        elif name == "go.mod":
            go_pkg.add(str(p.parent))
        elif name == "Cargo.toml":
            rust_pkg.add(str(p.parent))

    combined = python_pkg | node_pkg | java_pkg | go_pkg | rust_pkg
    return {
        "python": len(python_pkg),
        "node": len(node_pkg),
        "java": len(java_pkg),
        "go": len(go_pkg),
        "rust": len(rust_pkg),
        "total": len(combined),
    }


def find_artifacts(root: Path) -> List[Tuple[str, int]]:
    artifacts: List[Tuple[str, int]] = []
    for p in iter_files(root):
        name = p.name.lower()
        suf = p.suffix.lower()
        if (suf in ARTIFACT_EXTS) or any(name.endswith(s) for s in ARTIFACT_SUFFIXES):
            try:
                artifacts.append((str(p), p.stat().st_size))
            except OSError:
                continue

    artifacts.sort(key=lambda x: x[1], reverse=True)
    return artifacts


def language_rows(per_ext: Dict[str, Dict[str, int]]) -> List[Tuple[str, int, int, str]]:
    rows = []
    for ext, data in per_ext.items():
        label = LANGUAGE_LABELS.get(ext, ext)
        rows.append((label, data["files"], data["loc"], human(data["size_bytes"])))

    rows.sort(key=lambda x: x[2], reverse=True)
    return rows


def print_table(title: str, headers: List[str], rows: List[Iterable[object]]) -> None:
    if title:
        print(f"\n{title}")
    str_rows = [[str(cell) for cell in row] for row in rows]
    header_row = [str(h) for h in headers]
    col_widths = [len(h) for h in header_row]
    for row in str_rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(cell))

    def fmt_row(row_data: Iterable[str]) -> str:
        return " | ".join(cell.ljust(col_widths[idx]) for idx, cell in enumerate(row_data))

    print(fmt_row(header_row))
    print("-+-".join("-" * w for w in col_widths))
    for row in str_rows:
        print(fmt_row(row))


def main() -> None:
    repo = Path(".").resolve()
    summary = scan_path(repo)
    modules = discover_modules(repo)
    module_stats = {name: scan_path(path) for name, path in modules.items()}
    packages = discover_packages(repo)
    artifacts = [{"path": p, "size_bytes": s, "size_human": human(s)} for p, s in find_artifacts(repo)]

    result = {
        "repo": str(repo),
        "summary": summary,
        "modules": module_stats,
        "packages": packages,
        "artifacts": artifacts,
        "language_rows": language_rows(summary["per_extension"]),
    }

    print("== Thống kê dự án ==")

    package_detail = ", ".join(
        f"{k}={v}" for k, v in packages.items() if k != "total" and v > 0
    ) or "không phát hiện"
    artifact_size_total = sum(a["size_bytes"] for a in artifacts)

    print_table(
        "Bảng tóm tắt",
        ["Chỉ số", "Giá trị"],
        [
            ("Đường dẫn repo", result["repo"]),
            ("Kích thước toàn bộ", human(summary["total_size_bytes"])),
            ("Kích thước mã nguồn", human(summary["source_size_bytes"])),
            ("Số file mã nguồn", summary["source_files"]),
            ("Số dòng code", summary["loc"]),
            ("Số lớp", summary["classes"]),
            ("Số gói", f"{packages['total']} ({package_detail})"),
            ("Số artifact", f"{len(artifacts)} (tổng {human(artifact_size_total)})"),
        ],
    )

    module_rows = []
    for name, stats in module_stats.items():
        module_rows.append(
            (
                name,
                "có" if stats["exists"] else "không",
                human(stats["total_size_bytes"]),
                stats["source_files"],
                stats["loc"],
                stats["classes"],
            )
        )
    if module_rows:
        print_table(
            "Bảng module",
            ["Module", "Tồn tại", "Dung lượng", "File mã nguồn", "LOC", "Lớp"],
            module_rows,
        )

    lang_rows = language_rows(summary["per_extension"])
    if lang_rows:
        print_table("Ngôn ngữ (theo LOC)", ["Ngôn ngữ", "File", "LOC", "Dung lượng"], lang_rows)

    artifact_rows = [(a["size_human"], a["path"]) for a in artifacts]
    if artifact_rows:
        print_table("Sản phẩm đóng gói (lớn nhất trước)", ["Kích thước", "Đường dẫn"], artifact_rows)
    else:
        print("\nSản phẩm đóng gói: chưa có (cần build để tạo artifact).")

    Path("project_stats.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
    print("\nSaved: project_stats.json")

if __name__ == "__main__":
    main()
