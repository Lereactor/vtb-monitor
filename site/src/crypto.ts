/** The private part: same scheme as monitor/sitecrypto.py and the agents site —
 *  PBKDF2-SHA256 → AES-GCM-256. The password never leaves the browser. */
import type { Encrypted } from './types'

function fromB64(s: string): Uint8Array<ArrayBuffer> {
  const bin = atob(s)
  const out = new Uint8Array(new ArrayBuffer(bin.length))
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

function toB64(buf: ArrayBuffer): string {
  let bin = ''
  for (const byte of new Uint8Array(buf)) bin += String.fromCharCode(byte)
  return btoa(bin)
}

/** Extractable, so «запомнить на этом устройстве» can keep the key instead of the password. */
export async function deriveKey(password: string, enc: Encrypted): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt: fromB64(enc.salt), iterations: enc.iter },
    material,
    { name: 'AES-GCM', length: 256 },
    true,
    ['decrypt'],
  )
}

export async function decryptJson<T>(enc: Encrypted, key: CryptoKey): Promise<T> {
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: fromB64(enc.iv) }, key, fromB64(enc.ct))
  return JSON.parse(new TextDecoder().decode(plain)) as T
}

export async function exportKey(key: CryptoKey): Promise<string> {
  return toB64(await crypto.subtle.exportKey('raw', key))
}

export async function importKey(b64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', fromB64(b64), { name: 'AES-GCM' }, true, ['decrypt'])
}
