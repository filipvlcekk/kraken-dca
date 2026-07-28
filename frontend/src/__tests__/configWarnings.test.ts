import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ConfigWarnings from '../components/ConfigWarnings.vue'

describe('ConfigWarnings', () => {
  it('renders setup mode and degraded validation errors', () => {
    const wrapper = mount(ConfigWarnings, {
      props: {
        configValid: false,
        validationErrors: {
          'dca_pairs.0.amount': 'Amount must be positive.',
        },
        setupMode: true,
      },
    })

    expect(wrapper.text()).toContain('Setup mode')
    expect(wrapper.text()).toContain('Amount must be positive.')
  })

  it('renders persistence and order-history write warnings', () => {
    const wrapper = mount(ConfigWarnings, {
      props: {
        configValid: true,
        validationErrors: {},
        configPersistenceError: 'Config could not be saved.',
        orderHistoryWarning: 'orders.csv is not writable.',
        setupMode: false,
      },
    })

    expect(wrapper.text()).toContain('Config could not be saved.')
    expect(wrapper.text()).toContain('orders.csv is not writable.')
  })

  it('renders degraded mode when saved config is invalid outside setup mode', () => {
    const wrapper = mount(ConfigWarnings, {
      props: {
        configValid: false,
        validationErrors: {
          config: 'Config YAML is malformed.',
        },
        setupMode: false,
      },
    })

    expect(wrapper.text()).toContain('Degraded config mode')
    expect(wrapper.text()).toContain('Config YAML is malformed.')
  })
})
