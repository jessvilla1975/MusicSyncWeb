# Sync Spotify -> YouTube Music

Script para copiar canciones de una playlist de Spotify a una playlist de YouTube Music.

## 1) Instalar Python y dependencias

En PowerShell, dentro de esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Configurar YouTube Music 

1. Inicia sesion en [YouTube Music](https://music.youtube.com).
2. Abre DevTools (`F12`) -> pestaña **Network**.
3. Recarga la pagina y elige una request de `music.youtube.com` tipo `browse` o `next`.
4. Copia los **Request Headers** y pegalos en `yt_headers.txt`.

Genera `browser.json` desde ese archivo:

```powershell
.\.venv\Scripts\python .\setup_ytmusic_headers.py --headers-file ".\yt_headers.txt" --output "browser.json"
```

## 3) Ejecutar sincronización 

```powershell
.\.venv\Scripts\python .\sync_playlist.py --spotify-source web --spotify-playlist-id "SPOTIFY_PLAYLIST_ID_O_URL" --yt-playlist-name "Neon light" --yt-auth "browser.json"
```

Puedes pasar:
- ID de Spotify (`37i9dQZF...`)
- URI (`spotify:playlist:...`)
- URL completa (`https://open.spotify.com/playlist/...`)

## 4) Ejemplo para tu prueba

ejemplo de caso:
- Spotify playlist: `Neon Light`
- YouTube Music playlist: `Neon light`

Si ya tienes URL de ambas, puedes usar:

```powershell
.\.venv\Scripts\python .\sync_playlist.py `
  --spotify-source web `
  --spotify-playlist-id "https://open.spotify.com/playlist/1InG8FtY6Ttd2rmMYxZDL9?si=SLYdzmBdQAKYfjq5BKghIQ" `
  --yt-playlist-name "Neon light" `
  --yt-playlist-id "PLftScjM5U6SXh8wS268Uslc9WpiLaSFYA" `
  --yt-auth "browser.json"
```

## 5) Ejemplo para otra playlist

Solo cambia la URL/ID de Spotify y el nombre destino de YouTube Music:

```powershell
.\.venv\Scripts\python .\sync_playlist.py `
  --spotify-source web `
  --spotify-playlist-id "https://open.spotify.com/playlist/TU_PLAYLIST_ID" `
  --yt-playlist-name "Mi nueva playlist YT" `
  --yt-auth "browser.json"
```

## 6) Interfaz web local 

Ejecuta con doble clic `run_app.bat` o desde terminal:
<img width="1920" height="1214" alt="Image" src="https://github.com/user-attachments/assets/3eb2d058-a243-4155-a63a-d068ee3c68ed" />
```powershell
.\run_app.bat
```

La app abre `http://127.0.0.1:5000` y te permite:
- Pegar headers para generar `browser.json`
- Pegar URL/ID de playlist Spotify
- Elegir nombre/ID de playlist destino en YouTube Music
- Ejecutar la sincronizacion desde botones

## 7) Crear ejecutable (.exe)

Para generar un ejecutable local:

```powershell
.\build_exe.bat
```

El archivo queda en:
- `dist\MusicSyncWebApp.exe`

## Notas

- El script evita duplicados en YouTube Music.
- Si no encuentra una canción, la reporta y continúa.
- Esta primera versión sincroniza solo de Spotify -> YouTube Music.
- `--spotify-source web` usa scraping de playlist publica de Spotify, sin Premium ni Spotify Developer API.
- Si `browser.json` expira, vuelve a generarlo con `setup_ytmusic_headers.py`.
- El modo scraping depende del HTML de Spotify y puede romperse si Spotify cambia su web.
