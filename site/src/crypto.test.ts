import { describe, expect, it } from 'vitest'
import { decryptJson, deriveKey, exportKey, importKey } from './crypto'
import enc from './__fixtures__/enc.json'
import type { Encrypted } from './types'

// enc.json is written by Python (monitor/sitecrypto.py) with password «test»:
// this proves the VPS and the browser use the same scheme.
describe('crypto', () => {
  it('decrypts what Python encrypted', async () => {
    const key = await deriveKey('test', enc as Encrypted)
    expect(await decryptJson(enc as Encrypted, key)).toEqual({ hello: 'мир' })
  })

  it('rejects a wrong password', async () => {
    const key = await deriveKey('wrong', enc as Encrypted)
    await expect(decryptJson(enc as Encrypted, key)).rejects.toThrow()
  })

  it('a remembered key still decrypts', async () => {
    const key = await importKey(await exportKey(await deriveKey('test', enc as Encrypted)))
    expect(await decryptJson(enc as Encrypted, key)).toEqual({ hello: 'мир' })
  })
})
