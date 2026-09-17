"""Project exclusion policy independent of Tk."""
import fnmatch
from pathlib import Path
from .config import EXCLUDED_FOLDERS, PREDEFINED_EXCLUDED_FILENAMES, TEXT_ENCODING
from .helpers import is_path_inside, rel_posix

class ExclusionPolicy:
    def __init__(self):
        self.respect_exclusions = True
        self.dynamic_patterns = set()
        self.gitignore_dirnames = set()
        self.gitignore_file_patterns = set()
        self.gitignore_path_patterns = set()
        self.disabled_rules = set()
        self.deleted_rules = set()
        self.gitignore_root = None

    def rule_key(self, source, pattern):
        # Imported rules belong to their project; built-ins and custom rules
        # retain the existing app-wide, session-only scope.
        scope = self.gitignore_root if source.startswith("gitignore_") else None
        return (scope, source, pattern)

    def rule_enabled(self, source, pattern):
        key = self.rule_key(source, pattern)
        return key not in self.disabled_rules and key not in self.deleted_rules

    def set_rule_enabled(self, source, pattern, enabled):
        key = self.rule_key(source, pattern)
        if enabled:
            self.disabled_rules.discard(key)
        else:
            self.disabled_rules.add(key)

    def delete_rule(self, source, pattern):
        key = self.rule_key(source, pattern)
        self.disabled_rules.discard(key)
        if source == "dynamic_user_pattern":
            self.dynamic_patterns.discard(pattern)
        else:
            self.deleted_rules.add(key)

    def add_pattern(self, pattern):
        self.dynamic_patterns.add(pattern)
        self.set_rule_enabled("dynamic_user_pattern", pattern, True)

    def load_gitignore(self, root: Path):
        self.gitignore_root = str(root.resolve())
        self.gitignore_dirnames.clear()
        self.gitignore_file_patterns.clear()
        self.gitignore_path_patterns.clear()

        gi = root / ".gitignore"
        if not gi.exists():
            return

        try:
            lines = gi.read_text(encoding=TEXT_ENCODING, errors="ignore").splitlines()
        except Exception:
            return

        for raw in lines:
            pattern = raw.strip()
            if not pattern or pattern.startswith("#") or pattern.startswith("!"):
                continue
            pattern = pattern.replace("\\", "/")
            if pattern.endswith("/"):
                value = pattern[:-1].strip("/")
                if value:
                    self.gitignore_dirnames.add(value)
            elif "/" in pattern:
                self.gitignore_path_patterns.add(pattern.strip("/"))
            else:
                self.gitignore_file_patterns.add(pattern)

    def collect_rules(self) -> list[dict]:
        rules = []
        rules.append({"rule_type": "toggle", "pattern": "respect_exclusions", "source": "ui", "active": int(self.respect_exclusions)})
        for pattern in sorted(EXCLUDED_FOLDERS):
            rules.append({"rule_type": "directory", "pattern": pattern, "source": "hardcoded_folder", "active": 1})
        for pattern in sorted(PREDEFINED_EXCLUDED_FILENAMES):
            rules.append({"rule_type": "filename", "pattern": pattern, "source": "predefined_filename", "active": 1})
        for pattern in sorted(self.dynamic_patterns):
            rules.append({"rule_type": "filename", "pattern": pattern, "source": "dynamic_user_pattern", "active": 1})
        for pattern in sorted(self.gitignore_dirnames):
            rules.append({"rule_type": "directory", "pattern": pattern, "source": "gitignore_dirname", "active": 1})
        for pattern in sorted(self.gitignore_file_patterns):
            rules.append({"rule_type": "filename", "pattern": pattern, "source": "gitignore_file_pattern", "active": 1})
        for pattern in sorted(self.gitignore_path_patterns):
            rules.append({"rule_type": "path", "pattern": pattern, "source": "gitignore_path_pattern", "active": 1})
        return [
            dict(rule, active=int(self.rule_enabled(rule["source"], rule["pattern"])))
            if rule["rule_type"] != "toggle" else rule
            for rule in rules
            if self.rule_key(rule["source"], rule["pattern"]) not in self.deleted_rules
        ]

    def should_exclude_path(self, path: Path, root: Path) -> tuple[bool, str | None]:
        if not self.respect_exclusions:
            return False, None

        try:
            p = path.resolve()
            r = root.resolve()
        except Exception:
            return False, None

        if p != r and not is_path_inside(p, r):
            return False, None

        name = p.name
        rel = rel_posix(p, r)

        if p.is_dir():
            if name in EXCLUDED_FOLDERS and self.rule_enabled("hardcoded_folder", name):
                return True, "hardcoded_folder"
            if name in self.gitignore_dirnames and self.rule_enabled("gitignore_dirname", name):
                return True, "gitignore_dirname"
            for pattern in self.gitignore_path_patterns:
                if not self.rule_enabled("gitignore_path_pattern", pattern):
                    continue
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel + "/", pattern) or fnmatch.fnmatch(rel + "/", pattern + "/"):
                    return True, "gitignore_path_pattern"
            return False, None

        for source, patterns in (("predefined_filename", PREDEFINED_EXCLUDED_FILENAMES),
                                 ("dynamic_user_pattern", self.dynamic_patterns)):
            for pattern in patterns:
                if self.rule_enabled(source, pattern) and fnmatch.fnmatch(name, pattern):
                    return True, "filename_pattern"
        for pattern in self.gitignore_file_patterns:
            if self.rule_enabled("gitignore_file_pattern", pattern) and fnmatch.fnmatch(name, pattern):
                return True, "gitignore_file_pattern"
        for pattern in self.gitignore_path_patterns:
            if self.rule_enabled("gitignore_path_pattern", pattern) and fnmatch.fnmatch(rel, pattern):
                return True, "gitignore_path_pattern"
        return False, None
