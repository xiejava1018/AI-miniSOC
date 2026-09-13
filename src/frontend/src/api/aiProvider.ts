import request from '@/utils/http'

const BASE = '/api/v1/ai-providers'

/** AI Provider 列表 */
export function getAIProviderList(params?: any) {
  return request.get({ url: BASE, params, keepFullResponse: true })
}

/** 场景目录（多选渲染用） */
export function getAIScenes() {
  return request.get({ url: `${BASE}/scenes` })
}

export function getAIProvider(id: number) {
  return request.get({ url: `${BASE}/${id}` })
}

export function addAIProvider(data: any) {
  return request.post({ url: BASE, data, showSuccessMessage: true, successMessage: '新增成功' })
}

export function updateAIProvider(id: number, data: any) {
  return request.put({ url: `${BASE}/${id}`, data, showSuccessMessage: true, successMessage: '更新成功' })
}

export function deleteAIProvider(id: number) {
  return request.del({ url: `${BASE}/${id}`, showSuccessMessage: true, successMessage: '删除成功' })
}

export function setDefaultAIProvider(id: number) {
  return request.post({ url: `${BASE}/${id}/set-default`, showSuccessMessage: true })
}

/** 测试连接：{id} 或 {draft} */
export function testAIProvider(payload: { id?: number; draft?: any }) {
  return request.post({ url: `${BASE}/test`, data: payload })
}
