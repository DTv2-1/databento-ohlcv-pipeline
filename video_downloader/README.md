# Descargador de Videos - Marc Zell Klein Course

Scripts para descargar videos del sitio de cursos https://members.marczellklein.com

## 📋 Requisitos

### Software necesario:
```bash
# 1. Python 3.11+
python3 --version

# 2. Dependencias de Python
pip3 install selenium beautifulsoup4 requests lxml

# 3. ChromeDriver
brew install --cask chromedriver

# 4. yt-dlp (para descargar videos HLS)
brew install yt-dlp
```

## 🚀 Uso Rápido

### Opción 1: Proceso completo automático

1. **Ejecuta el script de Selenium** (abre navegador, hace login, captura URLs):
```bash
python3 download_course_videos_selenium.py
```

2. **Descarga el video** con las URLs capturadas:
```bash
python3 download_videos_auto.py
```

### Opción 2: Descarga manual con yt-dlp

Si prefieres más control:

```bash
# 1. Ejecuta el script de Selenium
python3 download_course_videos_selenium.py

# 2. Descarga usando la URL directamente
M3U8_URL=$(head -1 m3u8_urls.txt)
yt-dlp "$M3U8_URL" -o "downloaded_videos/mi_video.mp4" --no-check-certificate
```

## 📁 Estructura de Archivos

```
video_downloader/
├── README.md                              # Este archivo
├── run.sh                                 # Script bash para ejecutar todo
│
├── scripts/                               # Scripts de Python
│   ├── download_course_videos_selenium.py # Script principal (Selenium)
│   ├── download_videos_auto.py            # Script automático de descarga
│   ├── download_hls_video.py              # Helper para videos HLS
│   └── download_course_videos.py          # Versión inicial (deprecated)
│
├── output/                                # Todos los archivos generados
│   ├── videos/                            # Videos descargados (.mp4)
│   ├── screenshots/                       # Screenshots del proceso (.png)
│   ├── html/                              # Páginas HTML para debug
│   └── logs/                              # Logs y configuración
│       ├── m3u8_urls.txt                  # URLs de videos capturadas
│       ├── cookies.json                   # Cookies (formato JSON)
│       └── cookies.txt                    # Cookies (formato Netscape)
│
└── docs/                                  # Documentación adicional (vacío)
```

## 🔍 Cómo Funciona

### Script de Selenium (`download_course_videos_selenium.py`)

1. **Inicia Chrome** con Selenium
2. **Login automático** con las credenciales proporcionadas
3. **Navega a la sección APEX**:
   - Hace clic en la tarjeta "APEX"
   - Hace clic en "Start Course"
4. **Captura URLs de video**:
   - Busca elementos `<video>` en la página
   - Analiza los logs de red de Chrome
   - Extrae URLs de archivos `.m3u8` (HLS manifest)
5. **Guarda información**:
   - URLs m3u8 → `m3u8_urls.txt`
   - Cookies → `cookies.json` y `cookies.txt`
   - Screenshots → `step*.png`
   - HTML → `*.html`

### Videos HLS

Los videos usan **HLS (HTTP Live Streaming)**:
- El video se divide en múltiples segmentos pequeños (`.ts`)
- Un archivo manifest (`.m3u8`) lista todos los segmentos
- `yt-dlp` descarga todos los segmentos y los une en un MP4

## 📹 Descargar Más Videos

Para descargar otros videos del curso:

1. **Modifica la URL del curso** en el script:
```python
# En download_course_videos_selenium.py, línea ~12:
COURSE_URL = "https://members.marczellklein.com/courses/library-v2"
```

2. **O navega manualmente**:
   - El script navega a APEX automáticamente
   - Para otros cursos, modifica la función `navigate_to_apex()`
   - O captura la URL del video que quieres y ejecútala directo con yt-dlp

## 🛠️ Solución de Problemas

### Error: "chromedriver not found"
```bash
brew install --cask chromedriver
# Si hay problemas de permisos:
xattr -d com.apple.quarantine /opt/homebrew/bin/chromedriver
```

### Error: "yt-dlp not found"
```bash
brew install yt-dlp
# O con pip:
pip3 install yt-dlp
```

### El video no se descarga completamente
- Verifica que el token en la URL m3u8 no haya expirado (suelen durar 1 hora)
- Re-ejecuta el script de Selenium para obtener un nuevo token
- Usa cookies: `yt-dlp URL --cookies cookies.txt`

### El navegador se cierra muy rápido
- Cambia `headless=False` para ver el navegador
- Agrega más tiempo de espera: `time.sleep(10)`

### Login falla
- Verifica las credenciales en el script
- Revisa los screenshots generados: `step*.png`
- Revisa el HTML: `page_source_*.html`

## 🔒 Seguridad

- Las credenciales están en el código (solo para uso personal)
- Las cookies tienen tokens de sesión temporales
- No compartas los archivos `cookies.txt` o `cookies.json`
- Los tokens expiran después de ~1 hora

## 💡 Tips

### Descargar en mejor calidad
```bash
yt-dlp "$M3U8_URL" -f bestvideo+bestaudio --merge-output-format mp4
```

### Descargar solo audio
```bash
yt-dlp "$M3U8_URL" -x --audio-format mp3
```

### Ver formatos disponibles
```bash
yt-dlp "$M3U8_URL" -F
```

### Descargar con subtítulos
```bash
yt-dlp "$M3U8_URL" --write-subs --sub-lang en
```

### Descargar lista completa de videos
Si tienes una lista de URLs en un archivo:
```bash
yt-dlp -a m3u8_urls.txt --cookies cookies.txt -o "downloaded_videos/%(title)s.%(ext)s"
```

## 📝 Notas

- Los videos están protegidos con tokens de autenticación
- Cada token expira después de un tiempo
- Necesitas re-ejecutar el script de Selenium para obtener nuevos tokens
- Los videos se descargan en la mejor calidad disponible (generalmente 720p)

## ✅ Ejemplo Completo

```bash
# 1. Instalar dependencias
brew install chromedriver yt-dlp
pip3 install selenium beautifulsoup4 requests

# 2. Descargar un video
python3 download_course_videos_selenium.py
python3 download_videos_auto.py

# 3. Verificar
ls -lh downloaded_videos/

# 4. Reproducir
open downloaded_videos/apex_welcome_video.mp4
```

## 🎯 Resultado

Después de ejecutar los scripts, tendrás:
- ✅ Video descargado en `downloaded_videos/`
- ✅ Formato MP4 compatible con cualquier reproductor
- ✅ Calidad HD (720p típicamente)
- ✅ Listo para ver offline

---

**Nota**: Este script es para uso personal únicamente. Respeta los términos de servicio del sitio.
