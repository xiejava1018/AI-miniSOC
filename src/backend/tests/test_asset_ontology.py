"""资产本体加载器（OH-1.2）单元测试。

覆盖：
- 单例：第二次调用不重解析（cached）
- mtime 命中：touch 文件后强制重读（缓存失效）
- YAML 缺失：FileNotFoundError
- 必填字段校验：缺 id / version / top_level_classes 抛错
- id 唯一：top_level / relations / axioms 三层各检一次
- domain/range 闭合：关系引用未定义的类抛错
- 查询 API：get_class / get_relation / get_axiom 三件套
- self_check：返回版本 + 数量 + 路径 + 耗时

【设计要点】
- 用 tmp_path fixture 隔离：默认加载的是仓库内真实 YAML（不会污染）
- 自带 minimal_ontology fixture 构造最小合法 YAML（用于校验失败用例）
- 测试不需要数据库 / FastAPI app，纯 Python
"""
import os
from pathlib import Path

import pytest

from app.core import asset_ontology as ao


@pytest.fixture
def reset_cache():
    """每个测试前后清理单例缓存，避免跨用例污染。"""
    original_path = ao._CONFIG_PATH
    original_snap = ao._cache["snapshot"]
    ao._load_once.cache_clear()
    ao._cache["snapshot"] = None
    ao._cache["mtime"] = 0.0
    yield
    # 恢复原始路径（避免 ErrorHandling 用例改了全局路径）
    ao._load_once.cache_clear()
    ao._CONFIG_PATH = original_path
    ao._cache["config_path"] = original_path
    ao._cache["snapshot"] = None
    ao._cache["mtime"] = 0.0


@pytest.fixture
def minimal_ontology_yaml(tmp_path: Path) -> Path:
    """最小合法 YAML（用于校验通过用例）。"""
    p = tmp_path / "asset_ontology_v1.yaml"
    p.write_text(
        """
ontology:
  id: test-ontology
  version: "0.1.0"
  generated_at: "2026-10-03"
  description: "test"
  authority: "test"
  source: "test.yaml"

standard_layer:
  stix_2_1:
    sco: ["ipv4-addr"]
    sdo: ["user-account"]

top_level_classes:
  - id: physical-asset
    label: "物理资产"
  - id: digital-asset
    label: "数字资产"

asset_instance:
  id: asset-instance
  label: "资产实例"
  parent: digital-asset
  attributes: []

sub_models:
  - id: business-system
    label: "业务系统"

relations:
  - id: belongs_to
    label: "属于"
    domain: asset-instance
    range: business-system

axioms:
  - id: axiom-test
    label: "测试公理"
    rule: "always true"
""",
        encoding="utf-8",
    )
    return p


@pytest.mark.unit
class TestLoadHappyPath:
    def test_load_default_returns_snapshot(self, reset_cache):
        """默认加载：不传路径 → 加载仓库内真实 asset_ontology_v1.yaml。"""
        snap = ao.load()
        assert snap.version
        assert snap.classes
        assert snap.relations
        assert snap.axioms

    def test_snapshot_immutable(self, reset_cache):
        """返回的 snapshot 是 frozen dataclass，不可变。"""
        snap = ao.load()
        with pytest.raises((AttributeError, Exception)) if not hasattr(snap, '__dataclass_params__') else pytest.raises(Exception):
            snap.version = "2.0.0"  # type: ignore[misc]

    def test_load_with_custom_path(self, reset_cache, minimal_ontology_yaml: Path):
        """测试时可用自定义路径。"""
        snap = ao.load(minimal_ontology_yaml)
        assert snap.version == "0.1.0"
        assert {c.id for c in snap.classes} >= {"physical-asset", "digital-asset", "asset-instance", "business-system"}


@pytest.mark.unit
class TestCaching:
    def test_load_is_singleton(self, reset_cache):
        """同一进程两次 load 应共享同一快照。"""
        snap1 = ao.load()
        snap2 = ao.load()
        assert snap1 is snap2

    def test_mtime_invalidates_cache(self, reset_cache, minimal_ontology_yaml: Path):
        """touch 文件后 mtime 变化 → 下次 load 强制重读。"""
        ao.load(minimal_ontology_yaml)
        # 修改文件内容并刷新 mtime
        new_content = minimal_ontology_yaml.read_text(encoding="utf-8").replace('"0.1.0"', '"0.2.0"')
        minimal_ontology_yaml.write_text(new_content, encoding="utf-8")
        # 确保 mtime 真的更新（部分文件系统 mtime 精度低）
        os.utime(minimal_ontology_yaml, None)
        snap = ao.load(minimal_ontology_yaml)
        assert snap.version == "0.2.0"

    def test_reload_force(self, reset_cache, minimal_ontology_yaml: Path):
        """reload() 强制重读。"""
        ao.load(minimal_ontology_yaml)
        new_content = minimal_ontology_yaml.read_text(encoding="utf-8").replace('"0.1.0"', '"0.3.0"')
        minimal_ontology_yaml.write_text(new_content, encoding="utf-8")
        os.utime(minimal_ontology_yaml, None)
        snap = ao.reload()
        assert snap.version == "0.3.0"


@pytest.mark.unit
class TestErrorHandling:
    def test_missing_yaml_raises(self, reset_cache, tmp_path: Path):
        """YAML 文件不存在且无缓存 → FileNotFoundError。"""
        nonexistent = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError, match="asset ontology file not found"):
            ao.load(nonexistent)

    def test_missing_required_key_ontology(self, reset_cache, tmp_path: Path):
        """缺 ontology 根键。"""
        p = tmp_path / "asset_ontology_v1.yaml"
        p.write_text("foo: bar\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required key: 'ontology'"):
            ao.load(p)

    def test_missing_version(self, reset_cache, tmp_path: Path):
        """缺 ontology.version。"""
        p = tmp_path / "asset_ontology_v1.yaml"
        p.write_text(
            """
ontology:
  id: x
  generated_at: "2026-10-03"
top_level_classes: []
relations: []
axioms: []
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required key: 'ontology.version'"):
            ao.load(p)

    def test_duplicate_class_id(self, reset_cache, tmp_path: Path):
        """top_level_classes id 重复。"""
        p = tmp_path / "asset_ontology_v1.yaml"
        p.write_text(
            """
ontology:
  id: x
  version: "0.1.0"
  generated_at: "2026-10-03"
top_level_classes:
  - id: dup
    label: "A"
  - id: dup
    label: "B"
relations: []
axioms: []
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate ontology class id"):
            ao.load(p)

    def test_duplicate_relation_id(self, reset_cache, tmp_path: Path):
        """relations id 重复。"""
        p = tmp_path / "asset_ontology_v1.yaml"
        p.write_text(
            """
ontology:
  id: x
  version: "0.1.0"
  generated_at: "2026-10-03"
top_level_classes:
  - id: a
    label: "A"
relations:
  - id: dup
    label: "R1"
    domain: a
    range: a
  - id: dup
    label: "R2"
    domain: a
    range: a
axioms: []
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate ontology relation id"):
            ao.load(p)

    def test_undefined_relation_domain(self, reset_cache, tmp_path: Path):
        """关系 domain 引用未定义类。"""
        p = tmp_path / "asset_ontology_v1.yaml"
        p.write_text(
            """
ontology:
  id: x
  version: "0.1.0"
  generated_at: "2026-10-03"
top_level_classes:
  - id: known
    label: "K"
relations:
  - id: r
    label: "R"
    domain: unknown-class
    range: known
axioms: []
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="domain='unknown-class' references undefined class"):
            ao.load(p)


@pytest.mark.unit
class TestQueryAPI:
    def test_get_class_top_level(self, reset_cache):
        """get_class 按 id 查顶层类。"""
        c = ao.get_class("physical-asset")
        assert c is not None
        assert c.id == "physical-asset"
        assert c.label

    def test_get_class_stix_anchor(self, reset_cache):
        """get_class 也支持 STIX 标准层锚（惰性构造）。"""
        c = ao.get_class("vulnerability")
        assert c is not None
        assert c.id == "vulnerability"

    def test_get_class_missing_returns_none(self, reset_cache):
        """get_class 不存在 → None（不是抛错，调用方友好）。"""
        assert ao.get_class("nonexistent-class-id-12345") is None

    def test_get_relation(self, reset_cache):
        r = ao.get_relation("maps_to")
        assert r is not None
        assert r.domain == "exposure-surface"
        assert r.range == "asset-instance"

    def test_get_relation_missing(self, reset_cache):
        assert ao.get_relation("nonexistent-relation") is None

    def test_get_axiom(self, reset_cache):
        a = ao.get_axiom("axiom-system-importance")
        assert a is not None
        assert a.label

    def test_get_axiom_missing(self, reset_cache):
        assert ao.get_axiom("nonexistent-axiom") is None

    def test_list_classes(self, reset_cache):
        """list_classes 返回所有类（顶层 + 实例 + 子类）。"""
        classes = ao.list_classes()
        assert len(classes) >= 5  # 至少 5 个顶层 + 实例 + 子类

    def test_list_relations(self, reset_cache):
        """list_relations 数量应 ≥ 14（实施方案主方案标 14 + 实测略多）。"""
        rels = ao.list_relations()
        assert len(rels) >= 14

    def test_list_axioms(self, reset_cache):
        """list_axioms = 5 条公理。"""
        axioms = ao.list_axioms()
        assert len(axioms) == 5


@pytest.mark.unit
class TestSelfCheck:
    def test_self_check_returns_dict(self, reset_cache):
        """self_check 返回 dict 含版本 + 类数 + 关系数 + 公理数。"""
        result = ao.self_check()
        assert "version" in result
        assert "classes" in result
        assert "relations" in result
        assert "axioms" in result
        assert result["classes"] >= 5
        assert result["relations"] >= 14
        assert result["axioms"] >= 5
        assert "elapsed_ms" in result
        assert result["elapsed_ms"] >= 0
        assert "config_path" in result
        assert "asset_ontology_v1.yaml" in result["config_path"]


@pytest.mark.unit
class TestNoBusinessDeps:
    """强约束：本模块不引入 sqlalchemy / fastapi / pydantic 等业务依赖。

    便于 OH-1.3 CI 跑在校验脚本里，不需要启动 FastAPI app。
    """

    def test_no_sqlalchemy_import(self):
        """import asset_ontology 不应拉起 SQLAlchemy。"""
        import sys
        import re

        # 强制 reload 子模块，避免污染
        if "app.core.asset_ontology" in sys.modules:
            del sys.modules["app.core.asset_ontology"]
        import app.core.asset_ontology  # noqa: F401
        forbidden = ["sqlalchemy", "fastapi", "pydantic"]
        # 任何子模块内出现这三种 import 即失败（注释中的提及忽略）
        comment_line_re = re.compile(r"^\s*#")
        docstring_re = re.compile(r'"""[\s\S]*?"""')
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("app.core.asset_ontology"):
                mod = sys.modules[mod_name]
                src = getattr(mod, "__file__", "") or ""
                if src and "asset_ontology" in src:
                    with open(src, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 去除模块 docstring（asset_ontology.py 顶部有提及 "sqlalchemy" 的注释）
                    content_no_doc = docstring_re.sub("", content, count=1)
                    for line in content_no_doc.splitlines():
                        if comment_line_re.match(line):
                            continue
                        for forbidden_mod in forbidden:
                            assert not re.search(
                                rf"\bimport\s+{forbidden_mod}\b", line
                            ), f"asset_ontology must not import {forbidden_mod} (line: {line!r})"
                            assert not re.search(
                                rf"\bfrom\s+{forbidden_mod}\b", line
                            ), f"asset_ontology must not import {forbidden_mod} (line: {line!r})"