import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { HistoryImportItem, HistoryImportResponse } from '../api'
import OrderHistoryImportPanel from '../components/OrderHistoryImportPanel.vue'

const { importHistoryOrdersMock, previewHistoryImportMock } = vi.hoisted(() => ({
  importHistoryOrdersMock: vi.fn(),
  previewHistoryImportMock: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    importHistoryOrders: importHistoryOrdersMock,
    previewHistoryImport: previewHistoryImportMock,
  }
})

const readyTxid = 'ABC123-DEFGH-IJKLMN'
const readyTxidTwo = 'ZZ9999-ABCDE-QQQQQQ'
const duplicateReadyTxid = 'QQ1111-WERTY-ASDFGH'
const importedTxid = 'LMN789-PQRST-UVWXYZ'
const notFoundTxid = 'XYZ987-ABCDE-FGHIJK'

describe('OrderHistoryImportPanel', () => {
  beforeEach(() => {
    previewHistoryImportMock.mockReset()
    importHistoryOrdersMock.mockReset()
    previewHistoryImportMock.mockResolvedValue({
      ok: true,
      data: responseWithItems([]),
    })
    importHistoryOrdersMock.mockResolvedValue({
      ok: true,
      data: responseWithItems([], 0, 0),
    })
  })

  it('keeps preview disabled until a valid-looking txid is entered', async () => {
    const wrapper = mountPanel()
    await wrapper.get('button[aria-label="Import orders"]').trigger('click')

    const previewButton = () => wrapper.get<HTMLButtonElement>('button[aria-label="Preview import"]')

    expect(previewButton().element.disabled).toBe(true)

    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue('not-a-kraken-id')
    expect(previewButton().element.disabled).toBe(true)

    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(readyTxid)
    expect(previewButton().element.disabled).toBe(false)
  })

  it('rejects lowercase txids as invalid-looking', async () => {
    const wrapper = mountPanel()
    await wrapper.get('button[aria-label="Import orders"]').trigger('click')

    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(readyTxid.toLowerCase())

    const previewButton = wrapper.get<HTMLButtonElement>('button[aria-label="Preview import"]')
    expect(previewButton.element.disabled).toBe(true)

    await previewButton.trigger('click')

    expect(previewHistoryImportMock).not.toHaveBeenCalled()
  })

  it('parses newlines and commas into unique IDs', async () => {
    previewHistoryImportMock.mockResolvedValue({
      ok: true,
      data: responseWithItems([
        item(duplicateReadyTxid, 'ready'),
        item(readyTxid, 'ready'),
        item(readyTxidTwo, 'ready'),
      ]),
    })
    const wrapper = mountPanel()
    await wrapper.get('button[aria-label="Import orders"]').trigger('click')

    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(`
      ${duplicateReadyTxid}, ${readyTxid}
      ${duplicateReadyTxid}
      ${readyTxidTwo},ignored
    `)
    await wrapper.get('button[aria-label="Preview import"]').trigger('click')

    expect(previewHistoryImportMock).toHaveBeenCalledWith(
      [duplicateReadyTxid, readyTxid, readyTxidTwo],
      'csrf-test-token',
    )
  })

  it('groups preview results by status and selects ready rows by default', async () => {
    previewHistoryImportMock.mockResolvedValue({
      ok: true,
      data: responseWithItems([
        item(readyTxid, 'ready'),
        item(importedTxid, 'already_imported'),
        item(notFoundTxid, 'not_found'),
      ]),
    })
    const wrapper = mountPanel()
    await wrapper.get('button[aria-label="Import orders"]').trigger('click')
    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(`${readyTxid},${importedTxid},${notFoundTxid}`)
    await wrapper.get('button[aria-label="Preview import"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('ready')
    expect(wrapper.text()).toContain('already_imported')
    expect(wrapper.text()).toContain('not_found')
    expect(wrapper.text()).toContain(readyTxid)
    expect(wrapper.text()).toContain(importedTxid)
    expect(wrapper.text()).toContain(notFoundTxid)
    expect(wrapper.get<HTMLInputElement>(`input[aria-label="Select ${readyTxid}"]`).element.checked).toBe(true)
    expect(wrapper.find(`input[aria-label="Select ${importedTxid}"]`).exists()).toBe(false)
    expect(wrapper.find(`input[aria-label="Select ${notFoundTxid}"]`).exists()).toBe(false)
  })

  it('submits selected txids with all preview txids and the csrf token', async () => {
    previewHistoryImportMock.mockResolvedValue({
      ok: true,
      data: responseWithItems([
        item(readyTxid, 'ready'),
        item(readyTxidTwo, 'ready'),
        item(importedTxid, 'already_imported'),
      ]),
    })
    importHistoryOrdersMock.mockResolvedValue({
      ok: true,
      data: responseWithItems([item(readyTxidTwo, 'ready')], 1, 2),
    })
    const wrapper = mountPanel()
    await wrapper.get('button[aria-label="Import orders"]').trigger('click')
    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(`${readyTxid},${readyTxidTwo},${importedTxid}`)
    await wrapper.get('button[aria-label="Preview import"]').trigger('click')
    await flushPromises()

    await wrapper.get(`input[aria-label="Select ${readyTxid}"]`).setValue(false)
    await wrapper.get('button[aria-label="Import selected"]').trigger('click')
    await flushPromises()

    expect(importHistoryOrdersMock).toHaveBeenCalledWith(
      [readyTxid, readyTxidTwo, importedTxid],
      [readyTxidTwo],
      'csrf-test-token',
    )
    expect(wrapper.emitted('imported')).toEqual([[]])
    expect(wrapper.text()).toContain('Imported 1 order')
  })

  it('displays API errors without clearing preview data', async () => {
    previewHistoryImportMock.mockResolvedValueOnce({
      ok: true,
      data: responseWithItems([item(readyTxid, 'ready')]),
    })
    previewHistoryImportMock.mockResolvedValueOnce({
      ok: false,
      error: {
        code: 'kraken_error',
        message: 'Kraken rejected preview.',
      },
    })
    importHistoryOrdersMock.mockResolvedValue({
      ok: false,
      error: {
        code: 'import_failed',
        message: 'Import failed.',
      },
    })
    const wrapper = mountPanel()
    await wrapper.get('button[aria-label="Import orders"]').trigger('click')
    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(readyTxid)
    await wrapper.get('button[aria-label="Preview import"]').trigger('click')
    await flushPromises()

    await wrapper.get('button[aria-label="Import selected"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Import failed.')
    expect(wrapper.text()).toContain(readyTxid)

    await wrapper.get('button[aria-label="Preview import"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Kraken rejected preview.')
    expect(wrapper.text()).toContain(readyTxid)
  })
})

function mountPanel() {
  return mount(OrderHistoryImportPanel, {
    props: {
      csrfToken: 'csrf-test-token',
    },
  })
}

function item(txid: string, status: HistoryImportItem['status']): HistoryImportItem {
  return {
    txid,
    status,
    message: `${status} message`,
    row: null,
    target_file: null,
  }
}

function responseWithItems(
  items: HistoryImportItem[],
  importedCount = 0,
  skippedCount = 0,
): HistoryImportResponse {
  return {
    items,
    imported_count: importedCount,
    skipped_count: skippedCount,
  }
}
