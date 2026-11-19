'use strict';
// Optional "stay signed in" for this browser only.
// The shared password is AES-GCM-wrapped locally with a non-extractable CryptoKey.
// Both the wrapped password and the local key remain in IndexedDB, not in GitHub.
(() => {
  const DB = 'unsere-zeit-geraeteanmeldung';
  const STORE = 'credentials';
  const ID = 'shared-calendar';

  function transaction(mode, action) {
    return new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) return reject(new Error('Gerätespeicher nicht verfügbar'));
      const opening = indexedDB.open(DB, 1);
      opening.onupgradeneeded = () => {
        if (!opening.result.objectStoreNames.contains(STORE)) {
          opening.result.createObjectStore(STORE);
        }
      };
      opening.onerror = () => reject(opening.error || new Error('Gerätespeicher nicht verfügbar'));
      opening.onsuccess = () => {
        const db = opening.result;
        let settled = false;
        let answer;
        try {
          const tx = db.transaction(STORE, mode);
          const request = action(tx.objectStore(STORE));
          request.onsuccess = () => { answer = request.result; };
          tx.oncomplete = () => { settled = true; db.close(); resolve(answer); };
          tx.onabort = () => { if (!settled) { settled = true; db.close(); reject(tx.error || new Error('Speicherfehler')); } };
          tx.onerror = () => { /* onabort rejects */ };
        } catch (error) {
          db.close();
          reject(error);
        }
      };
    });
  }

  async function save(password) {
    if (!window.crypto?.subtle) throw new Error('Sichere Gerätespeicherung nicht verfügbar');
    const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encrypted = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv }, key, new TextEncoder().encode(password)
    );
    await transaction('readwrite', store => store.put({
      version: 1, key, iv: Array.from(iv),
      encrypted: Array.from(new Uint8Array(encrypted))
    }, ID));
  }

  async function load() {
    if (!window.crypto?.subtle) return null;
    const record = await transaction('readonly', store => store.get(ID));
    if (!record) return null;
    if (record.version !== 1 || !record.key ||
        !Array.isArray(record.iv) || !Array.isArray(record.encrypted)) {
      throw new Error('Ungültige lokale Anmeldung');
    }
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: new Uint8Array(record.iv) },
      record.key, new Uint8Array(record.encrypted)
    );
    return new TextDecoder().decode(plaintext);
  }

  async function clear() {
    await transaction('readwrite', store => store.delete(ID));
  }

  window.UnsereZeitRemember = Object.freeze({ save, load, clear });
})();
