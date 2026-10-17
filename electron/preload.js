const { contextBridge, ipcRenderer } = require('electron');

// Safe bridge: the web page can ask Electron to show a folder picker or open a folder.
contextBridge.exposeInMainWorld('api', {
  chooseFolder: (startPath) => ipcRenderer.invoke('choose-folder', startPath),
  openFolder: (folderPath) => ipcRenderer.invoke('open-folder', folderPath),
});
