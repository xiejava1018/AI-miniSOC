import request from '@/utils/http'

const BASE = '/api/v1/assets/ontology'

export interface OntologyClassRow {
  class_id: string
  label: string
  mapped_to: 'orm' | 'graph' | 'unmapped'
  model_name?: string | null
  table?: string | null
  filter?: string | null
  graph_node_types?: string[]
  unresolved?: string[]
  instance_count?: number | null
}

export interface OntologyAlignment {
  classes: OntologyClassRow[]
  orm_class_count: number
  graph_class_count: number
  unmapped_count: number
  red_line: string
}

export interface OntologyValidateResult {
  valid: boolean
  problems: Array<{
    class_id: string
    kind: 'unresolved_model' | 'unknown_column'
    detail: string
  }>
  checked_classes: number
}

export function getOntologyAlignment() {
  return request.get<OntologyAlignment>({ url: `${BASE}/alignment` })
}

export function validateOntology() {
  return request.get<OntologyValidateResult>({ url: `${BASE}/validate` })
}
