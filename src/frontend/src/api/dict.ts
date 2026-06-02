import request from '@/utils/http'

const DICT_BASE = '/api/v1/dicts'

/** 获取字典列表（分页） */
export function getDictList(params?: Api.SystemDict.DictSearchParams) {
  return request.get({
    url: DICT_BASE,
    params: {
      page: (params as any)?.current ?? (params as any)?.page ?? 1,
      page_size: (params as any)?.size ?? (params as any)?.page_size ?? 20,
      dict_type: (params as any)?.dict_type,
      search: (params as any)?.search,
    },
    keepFullResponse: true,
  })
}

/** 获取所有字典分类 */
export function getDictTypes() {
  return request.get<string[]>({
    url: `${DICT_BASE}/types`,
  })
}

/** 按类型获取全部字典项（不分页） */
export function getDictsByType(dictType: string) {
  return request.get<Api.SystemDict.DictItem[]>({
    url: `${DICT_BASE}/${dictType}/items`,
  })
}

/** 新增字典项 */
export function addDict(data: Api.SystemDict.DictPayload) {
  return request.post({
    url: DICT_BASE,
    data,
    showSuccessMessage: true,
    successMessage: '新增成功',
  })
}

/** 更新字典项 */
export function updateDict(id: number, data: Partial<Api.SystemDict.DictPayload>) {
  return request.put({
    url: `${DICT_BASE}/${id}`,
    data,
    showSuccessMessage: true,
    successMessage: '更新成功',
  })
}

/** 删除字典项 */
export function deleteDict(id: number) {
  return request.del({
    url: `${DICT_BASE}/${id}`,
    showSuccessMessage: true,
    successMessage: '删除成功',
  })
}
