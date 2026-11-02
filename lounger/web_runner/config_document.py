"""A format-independent JSON tree API backed by the project's existing YAML file."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .storage import Problem

_WRITE_LOCK = threading.Lock()


def _kind(value):
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string" if isinstance(value, str) else "readonly"


def _key(node):
    return yaml.safe_load(yaml.serialize(node))


def _child(node, part):
    if isinstance(node, MappingNode):
        matches = [(key, value) for key, value in node.value if _key(key) == part]
        if len(matches) != 1:
            raise ValueError("配置项不存在或键名重复")
        return matches[0]
    if isinstance(node, SequenceNode) and type(part) is int and 0 <= part < len(node.value):
        return None, node.value[part]
    raise ValueError("配置路径不存在")


def _after_value(text, node):
    if isinstance(node, (MappingNode, SequenceNode)) and not node.flow_style and node.value:
        return _after_value(text, node.value[-1][1] if isinstance(node, MappingNode) else node.value[-1])
    if isinstance(node, ScalarNode) and node.style in ("|", ">"):
        return node.end_mark.index - node.end_mark.column
    return _after_line(text, node.end_mark)


def _after_line(text, mark):
    if mark.column == 0:
        return mark.index
    newline = text.find("\n", mark.index)
    return len(text) if newline == -1 else newline + 1


def _replace(text, node, value):
    replacement = yaml.safe_dump(value, allow_unicode=True, sort_keys=False, default_flow_style=True, width=10**9)
    replacement = replacement.removesuffix("...\n").rstrip("\n")
    replacement = replacement.replace("\n", "\n" + " " * node.start_mark.column)
    block = isinstance(node, (MappingNode, SequenceNode)) and not node.flow_style
    block = block or isinstance(node, ScalarNode) and node.style in ("|", ">")
    if block or node.end_mark.column == 0:
        replacement += "\n" + " " * node.end_mark.column
    return text[:node.start_mark.index] + replacement + text[node.end_mark.index:]


@dataclass
class ConfigDocument:
    path: Path
    text: str
    data: object

    @classmethod
    def load(cls, root):
        path = Path(root) / "config" / "config.yaml"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        try:
            data = yaml.safe_load(text) if text.strip() else {}
            if data is None and yaml.compose(text) is None:
                data = {}
        except yaml.YAMLError:
            raise ValueError("配置文件无法解析，请检查语法后刷新") from None
        return cls(path, text, data)

    @property
    def revision(self):
        return hashlib.sha256(self.text.encode()).hexdigest()

    def environments(self):
        """Optional single-file convention used by the runner environment selector."""
        if not isinstance(self.data, dict) or "environment" not in self.data:
            return []
        environments = self.data.get("environments")
        return [name for name in environments if isinstance(name, str)] if isinstance(environments, dict) else []

    def environment(self, selected=None):
        names = self.environments()
        if not names and not selected:
            return ""
        selected = selected or self.data.get("environment")
        if not isinstance(selected, str) or selected not in names:
            raise ValueError("请选择 config/config.yaml 中已定义的环境")
        return selected

    def view(self):
        def node(value, path, label, ancestors=frozenset()):
            kind = _kind(value)
            result = {"path": path, "label": str(label), "kind": kind}
            if kind in ("object", "array"):
                if id(value) in ancestors:
                    return {**result, "kind": "readonly", "value": "循环引用"}
                children = value.items() if kind == "object" else enumerate(value)
                result["children"] = [
                    node(child, [*path, key], key, ancestors | {id(value)})
                    for key, child in children
                    if key is None or isinstance(key, (str, int, float, bool))
                ]
            else:
                result["value"] = value if kind != "readonly" else str(value)
            return result

        return {"revision": self.revision, "exists": self.path.is_file(),
                "tree": node(self.data, [], "全部配置")}

    def mutate(self, action, path, value, revision, key=None):
        if action not in ("set", "add", "delete") or not isinstance(path, list) or len(path) > 64:
            raise ValueError("无效的配置操作")
        if any(part is not None and not isinstance(part, (str, int, float, bool)) for part in path):
            raise ValueError("无效的配置路径")
        if not isinstance(revision, str) or not revision:
            raise ValueError("请刷新配置后再保存")
        # Reject NaN/Infinity and non-JSON values before touching the file.
        json.dumps(value, allow_nan=False)
        with _WRITE_LOCK:
            current = self.load(self.path.parent.parent)
            if revision != current.revision:
                raise Problem("config_conflict", "配置已被其他窗口修改，请刷新后重试", 409)
            data = copy.deepcopy(current.data)
            tree = yaml.compose(current.text)
            target, container = tree, data
            parent: Any = None
            parent_data: Any = None
            key_node = None
            for part in path:
                parent, parent_data = target, container
                key_node, target = _child(target, part)
                container = container[part]

            def shared(node, wanted, ancestors=frozenset()):
                if node is wanted:
                    return 1
                if id(node) in ancestors:
                    return 0
                descendants = [n for pair in node.value for n in pair] if isinstance(node, MappingNode) else (
                    node.value if isinstance(node, SequenceNode) else []
                )
                return sum(shared(n, wanted, ancestors | {id(node)}) for n in descendants)

            # Editing through an alias would silently change several locations.
            ancestor = tree
            for part in path:
                if shared(tree, ancestor) > 1:
                    raise ValueError("此项共享了其他位置的值，请先拆开共享引用")
                ancestor = _child(ancestor, part)[1]
            if target is not None and shared(tree, target) > 1:
                raise ValueError("此项共享了其他位置的值，请先拆开共享引用")

            if action == "set":
                if target is None:
                    text = current.text + ("\n" if current.text and not current.text.endswith("\n") else "")
                    text += yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
                else:
                    text = _replace(current.text, target, value)
                if path:
                    parent_data[path[-1]] = value
                else:
                    data = value
            elif action == "add":
                addition: dict[str, Any] | list[Any]
                if isinstance(container, dict):
                    if not isinstance(key, str) or not key.strip() or len(key) > 256 or key in container:
                        raise ValueError("键名不能为空、重复或过长")
                    container[key] = value
                    addition = {key: value}
                elif isinstance(container, list):
                    container.append(value)
                    addition = [value]
                else:
                    raise ValueError("只能在分组或列表中新增配置")
                if target is None:
                    text = current.text + ("\n" if current.text and not current.text.endswith("\n") else "")
                    text += yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
                elif target.flow_style or not target.value:
                    text = _replace(current.text, target, container)
                else:
                    offset = _after_value(current.text, target)
                    indent = target.value[0][0].start_mark.column if isinstance(target, MappingNode) else target.start_mark.column
                    addition_text = yaml.safe_dump(addition, allow_unicode=True, sort_keys=False)
                    addition_text = "".join(" " * indent + line for line in addition_text.splitlines(keepends=True))
                    prefix = "" if offset == 0 or current.text[offset - 1] == "\n" else "\n"
                    text = current.text[:offset] + prefix + addition_text + current.text[offset:]
            else:
                if not path:
                    raise ValueError("不能删除整个配置文档")
                del parent_data[path[-1]]
                if parent.flow_style or len(parent.value) == 1:
                    text = _replace(current.text, parent, parent_data)
                else:
                    start = (key_node or target).start_mark
                    offset = start.index - start.column
                    end = _after_value(current.text, target)
                    text = current.text[:offset] + current.text[end:]

            try:
                parsed = yaml.safe_load(text)
            except yaml.YAMLError:
                raise ValueError("无法保留当前结构，请先在文件中整理此项后重试") from None
            if parsed != data:
                raise ValueError("此结构无法安全编辑，原配置未修改")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as file:
                    temporary = Path(file.name)
                    os.chmod(temporary, stat.S_IMODE(self.path.stat().st_mode) if self.path.exists() else 0o600)
                    file.write(text)
                    file.flush()
                    os.fsync(file.fileno())
                latest = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
                if latest != current.text:
                    raise Problem("config_conflict", "配置已被其他窗口修改，请刷新后重试", 409)
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return {"saved": True, "revision": hashlib.sha256(text.encode()).hexdigest()}
