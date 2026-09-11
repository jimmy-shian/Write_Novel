// AI Novel Factory - Electron main process (僅包裝用)
// 職責：啟動 Python 無頭後端 sidecar -> 等就緒 -> 開獨立視窗載入本機 URL
// 不開瀏覽器；使用者資料一律放在 %USERPROFILE%\.ai-novel-factory，與 EXE 位置無關。
const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

const USER_DIR_NAME = '.ai-novel-factory';
let backendProc = null;
let mainWindow = null;
let splash = null;
let isQuitting = false; // 正常退出中（關視窗/結束 App）時不跳錯誤框

function userDir() {
  const dir = path.join(app.getPath('home'), USER_DIR_NAME);
  fs.mkdirSync(dir, { recursive: true });
  fs.mkdirSync(path.join(dir, 'gold_rules'), { recursive: true });
  return dir;
}

function logLine(stream, line) {
  try {
    fs.appendFileSync(path.join(userDir(), 'backend.log'), `[${new Date().toISOString()}] ${line}\n`);
  } catch (_) { /* ignore */ }
}

function sidecarPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend', 'AI_Novel_Factory_Backend.exe');
  }
  // 未包裝 dev 測試用：指向本地 PyInstaller onedir 產物
  return path.join(__dirname, '..', 'dist-packages', 'AI_Novel_Factory_Backend', 'AI_Novel_Factory_Backend.exe');
}

function isPortAvailable(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(false));
    srv.listen(port, '127.0.0.1', () => {
      srv.close(() => resolve(true));
    });
  });
}

async function pickFreePort() {
  // 優先使用固定 Port 8000，確保瀏覽器 localStorage Origin 保持一致；若佔用則動態分配
  if (await isPortAvailable(8000)) {
    return 8000;
  }
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
  });
}

function waitForBackend(port, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const probe = () => {
      const req = http.get({ host: '127.0.0.1', port, path: '/', timeout: 2000 }, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve();
        retry();
      });
      req.on('error', retry);
      req.on('timeout', () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (backendProc && backendProc.exitCode !== null) {
        return reject(new Error(`後端行程已退出 (exit code ${backendProc.exitCode})，請查看使用者目錄下的 backend.log`));
      }
      if (Date.now() > deadline) return reject(new Error('後端啟動逾時（60 秒），請查看使用者目錄下的 backend.log'));
      setTimeout(probe, 500);
    };
    probe();
  });
}

function startBackend(port, dir) {
  const exe = sidecarPath();
  if (!fs.existsSync(exe)) {
    throw new Error(`找不到後端程式：${exe}`);
  }
  const env = {
    ...process.env,
    APP_PORT: String(port),
    DB_PATH: path.join(dir, 'novel_factory.db'),
    GOLD_RULES_DIR: path.join(dir, 'gold_rules'),
  };
  backendProc = spawn(exe, ['--port', String(port)], {
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backendProc.stdout.on('data', (d) => logLine('out', d.toString().trimEnd()));
  backendProc.stderr.on('data', (d) => logLine('err', d.toString().trimEnd()));
  backendProc.on('exit', (code) => {
    // 正常退出（使用者關視窗 / App 結束）時後端本來就會被殺掉，不視為錯誤
    if (isQuitting) return;
    if (mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox('AI Novel Factory', `後端服務已停止 (exit code ${code})，請查看 ${dir} 下的 backend.log`);
    }
  });
}

function createWindow(targetUrl) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    autoHideMenuBar: true,
    title: 'AI Novel Factory',
    show: false, // 等載入完成再顯示，避免白屏閃爍
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      partition: 'persist:ai-novel-factory',
    },
  });
  mainWindow.loadURL(targetUrl);
  mainWindow.once('ready-to-show', () => {
    if (splash && !splash.isDestroyed()) splash.close();
    splash = null;
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
  });
  mainWindow.on('closed', () => { mainWindow = null; });
}

// 啟動畫面：App 一起來就先顯示，避免後端準備期看起來像沒反應
function createSplash() {
  splash = new BrowserWindow({
    width: 440,
    height: 320,
    resizable: false,
    minimizable: false,
    maximizable: false,
    autoHideMenuBar: true,
    title: 'AI Novel Factory - 啟動中',
    center: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  splash.loadFile(path.join(__dirname, 'splash.html'));
  splash.on('closed', () => { splash = null; });
}

function setSplashStatus(msg) {
  try {
    if (splash && !splash.isDestroyed()) splash.webContents.send('splash-status', msg);
  } catch (_) { /* ignore */ }
}

function closeSplash() {
  try {
    if (splash && !splash.isDestroyed()) splash.close();
  } catch (_) { /* ignore */ }
  splash = null;
}

function stopBackend() {
  if (backendProc && backendProc.exitCode === null) {
    try { backendProc.kill(); } catch (_) { /* ignore */ }
  }
  backendProc = null;
}

async function start() {
  const gotLock = app.requestSingleInstanceLock();
  if (!gotLock) { app.quit(); return; }
  app.on('second-instance', () => {
    const win = mainWindow || splash;
    if (win && !win.isDestroyed()) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  await app.whenReady();
  createSplash(); // 先顯示啟動畫面
  const dir = userDir();

  // 開發模式：不啟後端，直接連 vite dev server（一般開發仍用瀏覽器即可，此分支僅備用）
  if (process.env.ELECTRON_DEV) {
    // 注意：dev 下後端請另開 start.bat；此處僅載入前端頁面
    setSplashStatus('正在連接開發伺服器…');
    createWindow(`http://127.0.0.1:${process.env.ELECTRON_DEV_PORT || 5173}/`);
    return;
  }

  try {
    setSplashStatus('正在準備使用者資料目錄…');
    const port = await pickFreePort();
    setSplashStatus('正在啟動後端服務…');
    startBackend(port, dir);
    setSplashStatus('後端啟動中，請稍候…');
    await waitForBackend(port);
    setSplashStatus('正在載入主畫面…');
    createWindow(`http://127.0.0.1:${port}/`);
  } catch (err) {
    closeSplash();
    dialog.showErrorBox('AI Novel Factory 啟動失敗', `${err.message}\n\n使用者資料目錄：${dir}`);
    stopBackend();
    app.quit();
  }
}

app.on('window-all-closed', () => {
  isQuitting = true;
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

start();
