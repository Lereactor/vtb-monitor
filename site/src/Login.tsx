import { useState, type FormEvent } from 'react'
import { decryptJson, deriveKey, exportKey } from './crypto'
import { loadEncrypted } from './data'
import type { PrivateData } from './types'

export const KEY_STORAGE = 'vtb-live.key'

/** Password dialog: the key is derived in the browser (same password as the agents site);
 *  «запомнить» keeps the derived key, never the password, in this device's storage. */
export default function Login({ onDone, onClose }: {
  onDone: (key: CryptoKey, priv: PrivateData) => void
  onClose: () => void
}) {
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!password) return
    setBusy(true)
    setError(null)
    try {
      const enc = await loadEncrypted()
      const key = await deriveKey(password, enc)
      let priv: PrivateData
      try {
        priv = await decryptJson<PrivateData>(enc, key)
      } catch {
        setError('Неверный пароль')
        return
      }
      if (remember) {
        try {
          localStorage.setItem(KEY_STORAGE, await exportKey(key))
        } catch {
          // private mode: just don't remember
        }
      }
      onDone(key, priv)
    } catch {
      setError('Не удалось загрузить данные — попробуйте ещё раз')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal" onClick={onClose}>
      <form className="login" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
        <h2>Вход для команды</h2>
        <div className="small dim">Откроет вкладку «Техника» и сообщения в чат. Пароль — как у сайта агентов.</div>
        <input type="password" autoFocus autoComplete="current-password" placeholder="Пароль"
               value={password} onChange={(e) => setPassword(e.target.value)} />
        <label className="small dim">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> запомнить на этом устройстве
        </label>
        <button type="submit" disabled={!password || busy}>{busy ? 'Открываю…' : 'Войти'}</button>
        {error && <div className="login__error">{error}</div>}
      </form>
    </div>
  )
}
