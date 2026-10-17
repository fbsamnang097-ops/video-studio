const { app, BrowserWindow, shell, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const PORT = 8765;
const DEV_URL = 'http://localhost:5173';
let backend;

function startBackend() {
  const venv = path.join(__dirname, '..', 'backend', '.venv');
  const py = process.env.PYTHON_BIN ||
    (process.platform === 'win32' ? path.join(venv, 'Scripts', 'python.exe') : path.join(venv, 'bin', 'python'));
  backend = spawn(py, [path.join(__dirname, '..', 'backend', 'main.py'), '--port', String(PORT),
    '--out', path.join(app.getPath('downloads'), 'VideoStudio')], { stdio: 'inherit' });
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
