import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { REDACTED_SECRET, type SecretMetadata } from '../api'
import CredentialEditor from '../components/CredentialEditor.vue'

const fileSecrets = {
  public_key: { configured: true, source: 'file' },
  private_key: { configured: true, source: 'file' },
} satisfies Record<string, SecretMetadata>

describe('CredentialEditor', () => {
  it('shows file credentials as redacted', () => {
    const wrapper = mount(CredentialEditor, {
      props: {
        apiConfig: {
          public_key: REDACTED_SECRET,
          private_key: REDACTED_SECRET,
        },
        secrets: fileSecrets,
      },
    })

    expect(wrapper.text()).toContain('Public API key')
    expect(wrapper.text()).toContain('Private API key')
    expect(wrapper.text()).toContain('Configured in config.yaml')
    expect(wrapper.text()).toContain('Redacted')
  })

  it('shows env credential source and status', () => {
    const wrapper = mount(CredentialEditor, {
      props: {
        apiConfig: {
          public_key: null,
          private_key: null,
        },
        secrets: {
          public_key: { configured: true, source: 'env' },
          private_key: { configured: false, source: null },
        },
      },
    })

    expect(wrapper.text()).toContain('Environment variable configured')
    expect(wrapper.text()).toContain('Not configured')
  })

  it('requires explicit replacement before sending a new secret', async () => {
    const wrapper = mount(CredentialEditor, {
      props: {
        apiConfig: {
          public_key: REDACTED_SECRET,
          private_key: REDACTED_SECRET,
        },
        secrets: fileSecrets,
      },
    })

    expect(wrapper.find('[aria-label="New public API key"]').exists()).toBe(false)

    await wrapper.get('button[aria-label="Replace public API key"]').trigger('click')
    await wrapper.get('[aria-label="New public API key"]').setValue('NEW_PUBLIC')
    await wrapper.get('button[aria-label="Save public API key"]').trigger('click')

    expect(wrapper.emitted('replace-public-key')).toEqual([['NEW_PUBLIC']])
  })

  it('can clear file credentials and never emits the redacted sentinel as a replacement', async () => {
    const wrapper = mount(CredentialEditor, {
      props: {
        apiConfig: {
          public_key: REDACTED_SECRET,
          private_key: REDACTED_SECRET,
        },
        secrets: fileSecrets,
      },
    })

    await wrapper.get('button[aria-label="Replace public API key"]').trigger('click')
    await wrapper.get('[aria-label="New public API key"]').setValue(REDACTED_SECRET)
    await wrapper.get('button[aria-label="Save public API key"]').trigger('click')
    await wrapper.get('button[aria-label="Clear private API key"]').trigger('click')

    expect(wrapper.emitted('replace-public-key')).toBeUndefined()
    expect(wrapper.emitted('clear-file-private-key')).toEqual([[]])
  })
})
