const { app, BrowserWindow, shell, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const PORT = 8765;
const DEV_URL = 'http://localhost:5173';
let backend;

function startBackend() {
  const packaged = app.isPackaged;
  const binDir = packaged
    ? path.join(process.resourcesPath, 'bin')
    : path.join(__dirname, '..', 'bin');

  // Put bundled ffmpeg/deno first on PATH so yt-dlp finds them
  const pathKey = Object.keys(process.env).find(k => k.toLowerCase() === 'path') || 'PATH';
  const env = { ...process.env, [pathKey]: binDir + path.delimiter + (process.env[pathKey] || '') };

  const args = ['--port', String(PORT), '--out', path.join(app.getPath('downloads'), 'VideoStudio')];
  let cmd, cmdArgs;
  if (packaged) {
    cmd = path.join(process.resourcesPath, 'backend', process.platform === 'win32' ? 'backend.exe' : 'backend');
    cmdArgs = args;
  } else {
    const venv = path.join(__dirname, '..', 'backend', '.venv');
    cmd = process.env.PYTHON_BIN ||
      (process.platform === 'win32' ? path.join(venv, 'Scripts', 'python.exe') : path.join(venv, 'bin', 'python'));
    cmdArgs = [path.join(__dirname, '..', 'backend', 'main.py'), ...args];
  }
  backend = spawn(cmd, cmdArgs, { env, windowsHide: true, stdio: packaged ? 'ignore' : 'inherit' });
  backend.on('error', (err) => dialog.showErrorBox('Backend failed to start', String(err)));
}

function waitForBackend(done, tries = 60) {
  http.get(`http://127.0.0.1:${PORT}/health`, () => done())
    .on('error', () => (tries > 0 ? setTimeout(() => waitForBackend(done, tries - 1), 500) : done()));
}

function createWindow() {
  const win = new BrowserWindow({ width: 1280, height: 860, minWidth: 980, minHeight: 640,
    backgroundColor: '#0B1220', webPreferences: { contextIsolation: true, preload: path.join(__dirname, 'preload.js') } });
  // Open external links (e.g. Telegram) in the user's default browser
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  if (app.isPackaged || process.env.NODE_ENV === 'production') {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  } else {
    win.loadURL(DEV_URL);
  }
}

ipcMain.handle('choose-folder', async (e, startPath) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  const r = await dialog.showOpenDialog(win, {
    title: 'Choose where to save downloads',
    defaultPath: startPath || app.getPath('downloads'),
    properties: ['openDirectory', 'createDirectory'],
  });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('open-folder', (e, folderPath) => shell.openPath(folderPath));

app.whenReady().then(() => { startBackend(); waitForBackend(createWindow); });
app.on('before-quit', () => backend && backend.kill());
app.on('window-all-closed', () => app.quit());
