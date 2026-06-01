import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getDictTypes, getDictsByType } from '@/api/dict'

export const useDictStore = defineStore('dictStore', () => {
  /** 字典缓存：{ dict_type: DictItem[] } */
  const cache = ref<Record<string, Api.SystemDict.DictItem[]>>({})
  /** 是否已加载 */
  const loaded = ref(false)

  /**
   * 加载所有字典数据（登录后调用一次）
   */
  async function loadAll() {
    try {
      const types = await getDictTypes()
      if (Array.isArray(types) && types.length > 0) {
        const batch = await Promise.all(
          types.map(async (type) => {
            const items = await getDictsByType(type)
            return { type, items: Array.isArray(items) ? items : [] }
          })
        )
        const newCache: Record<string, Api.SystemDict.DictItem[]> = {}
        for (const { type, items } of batch) {
          newCache[type] = items
        }
        cache.value = newCache
      }
      loaded.value = true
    } catch (e) {
      console.warn('[dictStore] 加载字典失败', e)
    }
  }

  /**
   * 按类型加载（懒加载）
   */
  async function loadByType(dictType: string) {
    try {
      const items = await getDictsByType(dictType)
      cache.value = { ...cache.value, [dictType]: Array.isArray(items) ? items : [] }
    } catch (e) {
      console.warn(`[dictStore] 加载字典 ${dictType} 失败`, e)
    }
  }

  /**
   * 刷新某类型缓存（增删改后调用）
   */
  async function refreshType(dictType: string) {
    await loadByType(dictType)
  }

  /** 获取原始字典项列表 */
  const getDict = computed(
    () => (dictType: string) => cache.value[dictType] || []
  )

  /** 获取选项列表 { label, value, color }[] */
  const getOptions = computed(
    () =>
      (dictType: string): { label: string; value: string; color?: string }[] => {
        const items = cache.value[dictType] || []
        return items.map((item) => ({
          label: item.dict_label,
          value: item.dict_code,
          color: item.color || undefined,
        }))
      }
  )

  /** 获取 code → label 映射 */
  const getLabelMap = computed(
    () =>
      (dictType: string): Record<string, string> => {
        const items = cache.value[dictType] || []
        const map: Record<string, string> = {}
        for (const item of items) {
          map[item.dict_code] = item.dict_label
        }
        return map
      }
  )

  /** 获取 code → color 映射 */
  const getColorMap = computed(
    () =>
      (dictType: string): Record<string, string | undefined> => {
        const items = cache.value[dictType] || []
        const map: Record<string, string | undefined> = {}
        for (const item of items) {
          map[item.dict_code] = item.color || undefined
        }
        return map
      }
  )

  return {
    cache,
    loaded,
    loadAll,
    loadByType,
    refreshType,
    getDict,
    getOptions,
    getLabelMap,
    getColorMap,
  }
})
