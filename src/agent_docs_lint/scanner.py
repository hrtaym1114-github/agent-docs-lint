from __future__ import annotations

from dataclasses import asdict, dataclass
from fnmatch import fnmatch
import re
from pathlib import Path
import tomllib
from typing import Iterable


DEFAULT_MODEL_NAMES = [
    "gpt-4",
    "gpt-4o",
    "claude-3-opus",
    "claude-3.5-sonnet",
    "o1-preview",
    "ChatGPT Plus",
]

DEFAULT_SCAN_GLOBS = [
    "AGENTS.md",
    "agents.md",
    "CLAUDE.md",
    "claude.md",
    "*/AGENTS.md",
    "*/agents.md",
    "*/CLAUDE.md",
    "*/claude.md",
    ".cursor/rules/**/*.md",
    ".cursor/rules/**/*.mdc",
    ".claude/rules/**/*.md",
    ".claude/rules/**/*.mdc",
    ".claude/agents/**/*.md",
    ".claude/agents/**/*.mdc",
    ".claude/skills/**/*.md",
    ".claude/skills/**/*.mdc",
    ".agents/skills/**/*.md",
    ".agents/skills/**/*.mdc",
    "agents/**/*.md",
    "agents/**/*.mdc",
]

AGENT_GLOBS = [
    ".claude/agents/**/*.md",
    ".claude/skills/**/SKILL.md",
    ".claude/skills/*.md",
    ".agents/skills/**/SKILL.md",
    ".agents/skills/*.md",
    "agents/*.md",
]

COMMAND_DIRS = [
    ".claude/commands",
    ".claude/skills",
    ".agents/skills",
    "agents",
]

PATH_EXTENSIONS = {
    ".md",
    ".mdc",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".py",
    ".sh",
}

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
SLASH_COMMAND_RE = re.compile(r"(?<![\w./-])/[A-Za-z][A-Za-z0-9_-]+")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Config:
    model_names: tuple[str, ...] = tuple(DEFAULT_MODEL_NAMES)
    ignore_paths: tuple[str, ...] = ()
    disable_rules: tuple[str, ...] = ()
    extra_scan_globs: tuple[str, ...] = ()


def load_config(root: Path, config_path: Path | None = None) -> Config:
    candidates = [config_path] if config_path else [
        root / "agent-docs-lint.toml",
        root / ".agent-docs-lint.toml",
    ]
    data: dict[str, object] = {}
    for candidate in candidates:
        if candidate and candidate.exists():
            with candidate.open("rb") as fh:
                data = tomllib.load(fh)
            break

    return Config(
        model_names=tuple(_list_value(data, "model_names", DEFAULT_MODEL_NAMES)),
        ignore_paths=tuple(_list_value(data, "ignore_paths", [])),
        disable_rules=tuple(_list_value(data, "disable_rules", [])),
        extra_scan_globs=tuple(_list_value(data, "extra_scan_globs", [])),
    )


def scan(path: str | Path, config_path: str | Path | None = None) -> list[Finding]:
    root = Path(path).resolve()
    config = load_config(root, Path(config_path).resolve() if config_path else None)
    scanner = Scanner(root, config)
    return scanner.run()


class Scanner:
    def __init__(self, root: Path, config: Config) -> None:
        self.root = root
        self.config = config
        self.disabled = set(config.disable_rules)

    def run(self) -> list[Finding]:
        files = self._scan_files()
        text_by_file = {file: _read_text(file) for file in files}
        findings: list[Finding] = []

        for file, text in text_by_file.items():
            if "dead_ref" not in self.disabled:
                findings.extend(self._dead_ref(file, text))
            if "broken_anchor" not in self.disabled:
                findings.extend(self._broken_anchor(file, text))
            if "model_name" not in self.disabled:
                findings.extend(self._model_name(file, text))

        if "unreferenced_agent" not in self.disabled:
            findings.extend(self._unreferenced_agent(text_by_file))

        return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule, finding.message))

    def _scan_files(self) -> list[Path]:
        files: set[Path] = set()
        for pattern in [*DEFAULT_SCAN_GLOBS, *self.config.extra_scan_globs]:
            for file in self.root.glob(pattern):
                if file.is_file() and not self._ignored(file):
                    files.add(file)
        return sorted(files)

    def _agent_files(self) -> list[Path]:
        files: set[Path] = set()
        for pattern in AGENT_GLOBS:
            for file in self.root.glob(pattern):
                if file.is_file() and not self._ignored(file):
                    if self._skip_agent_file(file):
                        continue
                    files.add(file)
        return sorted(files)

    def _skip_agent_file(self, file: Path) -> bool:
        if file.name.lower() == "readme.md" or file.stem.startswith("_"):
            return True
        rel_parts = file.relative_to(self.root).parts
        if len(rel_parts) >= 3 and rel_parts[:2] == (".claude", "agents"):
            return any(part in {"registries", "project-templates", "channels"} for part in rel_parts[2:-1])
        return False

    def _ignored(self, file: Path) -> bool:
        rel = _rel(file, self.root)
        return any(fnmatch(rel, pattern) or fnmatch(file.name, pattern) for pattern in self.config.ignore_paths)

    def _dead_ref(self, file: Path, text: str) -> list[Finding]:
        findings: list[Finding] = []
        seen: set[tuple[int, str]] = set()

        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in MARKDOWN_LINK_RE.finditer(line):
                target = _strip_angle_brackets(match.group(1))
                if _is_external_or_special(target) or target.startswith("#"):
                    continue
                path_part, _anchor = _split_anchor(target)
                if path_part and not self._path_exists(file, path_part):
                    key = (line_no, f"link:{path_part}")
                    if key not in seen:
                        findings.append(self._finding(file, line_no, "dead_ref", f"missing linked path: {path_part}"))
                        seen.add(key)

            for match in BACKTICK_RE.finditer(line):
                token = match.group(1).strip()
                if self._looks_path_like(token) and not self._path_exists(file, token):
                    key = (line_no, f"path:{token}")
                    if key not in seen:
                        findings.append(self._finding(file, line_no, "dead_ref", f"missing referenced path: {token}"))
                        seen.add(key)

            for match in SLASH_COMMAND_RE.finditer(line):
                command = match.group(0)[1:]
                if len(command) < 3:
                    continue
                if not self._command_exists(file, command):
                    key = (line_no, f"command:{command}")
                    if key not in seen:
                        findings.append(self._finding(file, line_no, "dead_ref", f"missing slash command target: /{command}"))
                        seen.add(key)

        return findings

    def _broken_anchor(self, file: Path, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in MARKDOWN_LINK_RE.finditer(line):
                target = _strip_angle_brackets(match.group(1))
                if _is_external_or_special(target):
                    continue
                path_part, anchor = _split_anchor(target)
                if not anchor:
                    continue
                target_file = file if not path_part else self._resolve_existing_path(file, path_part)
                if not target_file or not target_file.is_file():
                    continue
                anchors = _anchors_for(_read_text(target_file))
                if _slug(anchor) not in anchors:
                    findings.append(self._finding(file, line_no, "broken_anchor", f"missing anchor #{anchor} in {_display_target(path_part, target_file, self.root)}"))
        return findings

    def _model_name(self, file: Path, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            for model in self.config.model_names:
                if not model:
                    continue
                if re.search(rf"(?<![\w.-]){re.escape(model)}(?![\w.-])", line, flags=re.IGNORECASE):
                    findings.append(self._finding(file, line_no, "model_name", f"hard-coded model or plan name: {model}"))
        return findings

    def _unreferenced_agent(self, text_by_file: dict[Path, str]) -> list[Finding]:
        files = self._agent_files()
        findings: list[Finding] = []
        for agent_file in files:
            stem = self._agent_name(agent_file)
            mentioned = False
            for source_file, text in text_by_file.items():
                if source_file == agent_file:
                    continue
                if re.search(rf"(?<![\w-]){re.escape(stem)}(?![\w-])", text, flags=re.IGNORECASE):
                    mentioned = True
                    break
            if not mentioned:
                findings.append(self._finding(agent_file, 1, "unreferenced_agent", f"agent or skill file is not referenced by name: {stem}"))
        return findings

    def _agent_name(self, file: Path) -> str:
        if file.name == "SKILL.md":
            return file.parent.name
        return file.stem

    def _path_exists(self, file: Path, target: str) -> bool:
        return self._resolve_existing_path(file, target) is not None

    def _resolve_existing_path(self, file: Path, target: str) -> Path | None:
        target = target.strip()
        path_part, _anchor = _split_anchor(target)
        if not path_part:
            return file
        if _is_external_or_special(path_part):
            return None
        candidates = []
        target_path = Path(path_part)
        if target_path.is_absolute():
            candidates.append(self.root / path_part.lstrip("/"))
        else:
            candidates.extend([file.parent / target_path, self.root / target_path])
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if _is_relative_to(resolved, self.root) and resolved.exists():
                return resolved
        return None

    def _command_exists(self, file: Path, command: str) -> bool:
        if file.stem == command or file.parent.name == command:
            return True
        names = {command, f"{command}.md", f"{command}.mdc", f"{command}.sh"}
        for directory in COMMAND_DIRS:
            base = self.root / directory
            if not base.exists():
                continue
            for candidate in base.rglob("*"):
                if candidate.is_file() and (candidate.name in names or candidate.stem == command):
                    return True
        return False

    def _looks_path_like(self, token: str) -> bool:
        if not token or token.startswith(("-", "--")) or " " in token:
            return False
        if "<" in token or ">" in token:
            return False
        if _is_external_or_special(token) or token.startswith("#") or token.startswith("/"):
            return False
        path_part, _anchor = _split_anchor(token)
        if not path_part:
            return False
        suffix = Path(path_part).suffix.lower()
        return "/" in path_part or suffix in PATH_EXTENSIONS or path_part in {"AGENTS.md", "CLAUDE.md"}

    def _finding(self, file: Path, line: int, rule: str, message: str) -> Finding:
        return Finding(path=_rel(file, self.root), line=line, rule=rule, message=message)


def _list_value(data: dict[str, object], key: str, default: Iterable[str]) -> list[str]:
    value = data.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return value


def _read_text(file: Path) -> str:
    return file.read_text(encoding="utf-8", errors="replace")


def _rel(file: Path, root: Path) -> str:
    return file.relative_to(root).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_external_or_special(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith(("http://", "https://", "mailto:", "tel:", "ftp:"))


def _strip_angle_brackets(target: str) -> str:
    if target.startswith("<") and target.endswith(">"):
        return target[1:-1]
    return target


def _split_anchor(target: str) -> tuple[str, str]:
    path_part, sep, anchor = target.partition("#")
    return path_part, anchor if sep else ""


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"\s+", "-", value)
    return value.strip("-")


def _anchors_for(text: str) -> set[str]:
    anchors: set[str] = set()
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            anchors.add(_slug(match.group(2)))
    return anchors


def _display_target(path_part: str, target_file: Path, root: Path) -> str:
    return path_part or _rel(target_file, root)
