/**
 * OH-Q.2 组件挂载冒烟测试：验证 @vue/test-utils + jsdom + SFC transform 通路。
 *
 * 用内联 defineComponent 构造目标，避免依赖 Element Plus 等重组件
 * （真实业务组件的测试在后续按页面逐步补齐，此文件固化基础设施）。
 */
import { describe, it, expect } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'

const Counter = defineComponent({
  name: 'Counter',
  setup() {
    const count = ref(0)
    return () =>
      h('div', [
        h('span', { class: 'count' }, String(count.value)),
        h(
          'button',
          { class: 'inc', onClick: () => count.value++ },
          '+'
        ),
      ])
  },
})

describe('@vue/test-utils 组件挂载', () => {
  it('初始渲染', () => {
    const wrapper = mount(Counter)
    expect(wrapper.find('.count').text()).toBe('0')
  })

  it('点击触发状态更新', async () => {
    const wrapper = mount(Counter)
    await wrapper.find('.inc').trigger('click')
    await wrapper.find('.inc').trigger('click')
    expect(wrapper.find('.count').text()).toBe('2')
  })

  it('props 传递', () => {
    const Greeter = defineComponent({
      props: { name: String },
      setup: (p) => () => h('h1', `hi ${p.name}`),
    })
    const wrapper = mount(Greeter, { props: { name: 'soc' } })
    expect(wrapper.text()).toBe('hi soc')
  })
})
