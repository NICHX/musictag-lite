import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EmptyState from '@/components/EmptyState.vue'

describe('EmptyState', () => {
  it('渲染标题与描述', () => {
    const wrapper = mount(EmptyState, { props: { title: '空空如也', description: '还没有数据' } })
    expect(wrapper.text()).toContain('空空如也')
    expect(wrapper.text()).toContain('还没有数据')
  })

  it('未传描述时不渲染段落', () => {
    const wrapper = mount(EmptyState, { props: { title: '只有标题' } })
    expect(wrapper.find('p').exists()).toBe(false)
  })

  it('渲染默认插槽内容', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '标题' },
      slots: { default: '<button data-test="cta">操作</button>' },
    })
    expect(wrapper.find('[data-test="cta"]').exists()).toBe(true)
  })
})
