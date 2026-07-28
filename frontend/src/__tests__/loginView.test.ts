import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LoginView from '../components/LoginView.vue'

describe('LoginView', () => {
  it('submits the password through a login event', async () => {
    const wrapper = mount(LoginView, {
      props: {
        loading: false,
        error: null,
      },
    })

    await wrapper.get('input[aria-label="Web UI password"]').setValue('secret-password')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('login')).toEqual([['secret-password']])
  })

  it('displays failed login errors and disables submit while loading', async () => {
    const wrapper = mount(LoginView, {
      props: {
        loading: true,
        error: 'Invalid password.',
      },
    })

    expect(wrapper.text()).toContain('Invalid password.')
    expect(wrapper.get<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true)
  })
})
