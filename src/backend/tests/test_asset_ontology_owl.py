"""OH-1.5 OWL 导出单测（纯函数，无需 DB）。"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from app.core import asset_ontology
from app.core.asset_ontology_owl import NAMESPACE, export_owl


def _owl():
    return export_owl(asset_ontology.load())


class TestExportOWL:
    def test_is_valid_xml(self):
        root = ET.fromstring(_owl())
        assert root.tag.endswith("RDF")

    def test_contains_classes(self):
        owl = _owl()
        assert "owl:Class" in owl
        assert NAMESPACE + "asset-instance" in owl

    def test_subclass_hierarchy(self):
        # asset-instance parent=digital-asset
        owl = _owl()
        assert "rdfs:subClassOf" in owl
        assert NAMESPACE + "digital-asset" in owl

    def test_object_property_domain_range(self):
        owl = _owl()
        assert "owl:ObjectProperty" in owl
        assert "rdfs:domain" in owl and "rdfs:range" in owl

    def test_datatype_property(self):
        owl = _owl()
        assert "owl:DatatypeProperty" in owl
        # uuid 属性被导出
        assert NAMESPACE + "uuid" in owl

    def test_axioms_as_comments(self):
        owl = _owl()
        assert "Axiom" in owl

    def test_version_info(self):
        snap = asset_ontology.load()
        assert snap.version in _owl()
