"""Tests for extract_params utility."""

import dataclasses
import enum

from antomnievo.common.utils.param_utils import extract_params


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


@dataclasses.dataclass
class NestedConfig:
    model: str = "gpt-4"
    timeout: int = 60
    api_key: str | None = None


class SimpleComponent:
    def __init__(self, name: str, concurrency: int, api_key: str | None = None):
        self.name = name
        self.concurrency = concurrency
        self.api_key = api_key


class ComponentWithDataclass:
    def __init__(self, label: str, config: NestedConfig):
        self.label = label
        self._config = config


class ComponentWithEnum:
    def __init__(self, mode: Color, count: int):
        self.mode = mode
        self.count = count


class ComponentWithPrivateAttrs:
    def __init__(self):
        self._sem = object()
        self._internal = [1, 2, 3]
        self.visible = True


def test_simple_attrs():
    obj = SimpleComponent(name="test", concurrency=4, api_key="sk-secret")
    params = extract_params(obj)
    assert params == {"name": "test", "concurrency": 4, "api_key": "***"}


def test_none_secret_not_masked():
    obj = SimpleComponent(name="test", concurrency=2, api_key=None)
    params = extract_params(obj)
    assert params["api_key"] is None


def test_nested_dataclass_via_private_attr():
    config = NestedConfig(model="claude", timeout=120, api_key="secret123")
    obj = ComponentWithDataclass(label="proposer", config=config)
    params = extract_params(obj)
    assert params["label"] == "proposer"
    assert params["config"]["model"] == "claude"
    assert params["config"]["timeout"] == 120
    assert params["config"]["api_key"] == "***"


def test_enum_serialized_as_value():
    obj = ComponentWithEnum(mode=Color.RED, count=5)
    params = extract_params(obj)
    assert params == {"mode": "red", "count": 5}


def test_private_non_dataclass_skipped():
    obj = ComponentWithPrivateAttrs()
    params = extract_params(obj)
    assert params == {"visible": True}


def test_dataclass_directly():
    config = NestedConfig(model="sonnet", timeout=30, api_key="key123")
    params = extract_params(config)
    assert params == {"model": "sonnet", "timeout": 30, "api_key": "***"}


def test_list_preserved():
    class WithList:
        def __init__(self):
            self.items = [1, 2, 3]
            self.tags = ["a", "b"]

    params = extract_params(WithList())
    assert params == {"items": [1, 2, 3], "tags": ["a", "b"]}
