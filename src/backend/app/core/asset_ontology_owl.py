"""OWL 导出（OH-1.5）

把 ``OntologySnapshot``（OH-1.2 加载器产物）序列化为 OWL/XML。

设计红线：
  - **不引入 rdflib 重依赖**：导出结构简单（类层次 + 对象属性 + 数据属性 +
    公理注释），直接拼 OWL/XML 字符串；通过转义保证合法。
  - **纯只读**：不读数据库业务数据，只消费内存中的本体快照。
  - **不伪造推理语义**：subClassOf 由 OntologyClass.parent 映射；ObjectProperty
    的 domain/range 来自 Relation；无对应 RDF 定义的字段（filter 等平台映射）
    不写进 OWL——它们是实现细节，不是本体语义。
"""
from __future__ import annotations

import logging
from typing import List
from xml.sax.saxutils import escape, quoteattr

from app.core import asset_ontology
from app.core.asset_ontology import OntologySnapshot

logger = logging.getLogger(__name__)

# 平台本体命名空间
NAMESPACE = "https://xiejava.dpdns.org/ontology/asset#"

# 本体属性 type → xsd 数据类型
_XSD_MAP = {
    "string": "xsd:string",
    "integer": "xsd:integer",
    "uuid": "xsd:string",
    "timestamp": "xsd:dateTime",
    "boolean": "xsd:boolean",
    "enum": "xsd:string",
    "float": "xsd:decimal",
}


def export_owl(snapshot: OntologySnapshot | None = None) -> str:
    snap = snapshot or asset_ontology.load()
    lines: List[str] = []
    add = lines.append

    add('<?xml version="1.0" encoding="UTF-8"?>')
    add('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
    add('         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"')
    add('         xmlns:owl="http://www.w3.org/2002/07/owl#"')
    add('         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"')
    add(f'         xml:base="{NAMESPACE}"')
    add(f'         xmlns="asset:{NAMESPACE}">')

    # 本体头
    add(f'  <owl:Ontology rdf:about="{NAMESPACE}">')
    add(f'    <owl:versionInfo>{escape(snap.version)}</owl:versionInfo>')
    if snap.description:
        add(f'    <rdfs:comment>{escape(snap.description)}</rdfs:comment>')
    add('  </owl:Ontology>')

    # 声明类（含 subClassOf 层次）
    for oc in snap.classes:
        add(f'  <owl:Class rdf:about="{NAMESPACE}{escape(oc.id)}">')
        add(f'    <rdfs:label>{escape(oc.label)}</rdfs:label>')
        if oc.description:
            add(f'    <rdfs:comment>{escape(oc.description)}</rdfs:comment>')
        if oc.parent:
            add(f'    <rdfs:subClassOf rdf:resource="{NAMESPACE}{escape(oc.parent)}"/>')
        add('  </owl:Class>')

    # 对象属性（关系：domain/range）
    for rel in snap.relations:
        add(f'  <owl:ObjectProperty rdf:about="{NAMESPACE}{escape(rel.id)}">')
        add(f'    <rdfs:label>{escape(rel.label)}</rdfs:label>')
        if rel.description:
            add(f'    <rdfs:comment>{escape(rel.description)}</rdfs:comment>')
        add(f'    <rdfs:domain rdf:resource="{NAMESPACE}{escape(rel.domain)}"/>')
        add(f'    <rdfs:range rdf:resource="{NAMESPACE}{escape(rel.range)}"/>')
        add('  </owl:ObjectProperty>')

    # 数据属性（asset-instance.attributes）
    for oc in snap.classes:
        for attr in oc.attributes:
            aid = attr.get("id")
            if not aid:
                continue
            xsd = _XSD_MAP.get(attr.get("type", "string"), "xsd:string")
            add(f'  <owl:DatatypeProperty rdf:about="{NAMESPACE}{escape(aid)}">')
            if attr.get("description"):
                add(f'    <rdfs:comment>{escape(attr["description"])}</rdfs:comment>')
            add(f'    <rdfs:domain rdf:resource="{NAMESPACE}{escape(oc.id)}"/>')
            add(f'    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#{xsd.split(":")[1]}"/>')
            add('  </owl:DatatypeProperty>')

    # 公理作为注释（不强制转 SWRL——避免过度承诺形式化推理）
    for ax in snap.axioms:
        add(f'  <!-- Axiom {escape(ax.id)}: {escape(ax.label)} :: {escape(ax.rule)} -->')

    add('</rdf:RDF>')
    return "\n".join(lines)
