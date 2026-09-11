// Preload: 僅暴露最小必要介面，保持 contextIsolation 開啟
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  platform: process.platform,
  // 啟動畫面進度文字（main process -> splash.html）
  onStatus: (cb) => ipcRenderer.on('splash-status', (_event, msg) => cb(msg)),
});
