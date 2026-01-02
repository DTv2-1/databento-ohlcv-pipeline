#!/usr/bin/env python3
"""
Script automatizado completo para descargar videos del sitio de cursos
Combina Selenium para autenticación y yt-dlp para descargar videos HLS
"""

import subprocess
import os
import sys
from pathlib import Path
from tqdm import tqdm

# Configuración (rutas relativas a la carpeta scripts)
OUTPUT_DIR = "../output/videos"
M3U8_FILE = "../output/logs/all_m3u8_urls.txt"
COOKIES_FILE = "../output/logs/cookies.txt"

def download_video_with_ytdlp(m3u8_url, output_name, pbar=None):
    """
    Descargar un video HLS usando yt-dlp con barra de progreso
    """
    output_path = os.path.join(OUTPUT_DIR, output_name)
    
    # Si el archivo ya existe, saltarlo
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if pbar:
            pbar.write(f"⏭️  Ya existe: {output_name} ({size_mb:.1f} MB)")
        return True
    
    cmd = [
        "yt-dlp",
        m3u8_url,
        "-o", output_path,
        "--no-check-certificate",
        "-f", "best",
        "--merge-output-format", "mp4",
        "--progress",
        "--newline",
    ]
    
    # Agregar cookies si existen
    if os.path.exists(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Capturar output en tiempo real
        error_lines = []
        for line in process.stdout:
            line = line.strip()
            
            # Capturar errores
            if "ERROR" in line or "error" in line or "WARNING" in line:
                error_lines.append(line)
            
            if "[download]" in line and "%" in line:
                # Actualizar descripción de la barra con el progreso interno
                try:
                    if "ETA" in line:
                        parts = line.split()
                        percent_idx = next(i for i, p in enumerate(parts) if '%' in p)
                        percent = parts[percent_idx].replace('%', '')
                        if pbar:
                            pbar.set_postfix_str(f"{percent}%")
                except:
                    pass
        
        process.wait()
        
        if process.returncode == 0:
            if os.path.exists(output_path):
                size = os.path.getsize(output_path)
                size_mb = size / (1024 * 1024)
                if pbar:
                    pbar.write(f"✅ {output_name} ({size_mb:.1f} MB)")
                return True
            else:
                if pbar:
                    pbar.write(f"⚠️  {output_name} - Archivo no encontrado después de descarga")
                    if error_lines:
                        pbar.write(f"   Errores: {error_lines[-1][:100]}")
                return False
        else:
            if pbar:
                pbar.write(f"❌ {output_name} - Error en descarga (código: {process.returncode})")
                if error_lines:
                    pbar.write(f"   Error: {error_lines[-1][:150]}")
            return False
    except FileNotFoundError:
        if pbar:
            pbar.write("❌ yt-dlp no está instalado")
            pbar.write("\nPara instalarlo:")
            pbar.write("  brew install yt-dlp")
            pbar.write("  o")
            pbar.write("  pip3 install yt-dlp")
        return False
    except Exception as e:
        if pbar:
            pbar.write(f"❌ {output_name} - Excepción: {str(e)}")
            import traceback
            pbar.write(f"   Traceback: {traceback.format_exc()[:200]}")
        return False

def main():
    print("=" * 70)
    print("🎬 DESCARGADOR AUTOMATIZADO DE VIDEOS")
    print("=" * 70)
    
    # Crear directorio de salida
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Verificar que existe el archivo de URLs
    if not os.path.exists(M3U8_FILE):
        print("\n❌ Archivo all_m3u8_urls.txt no encontrado")
        print("\nPrimero debes ejecutar:")
        print("  python3 download_course_videos_selenium.py")
        print("\nEsto generará las URLs de video y cookies necesarias.")
        return
    
    # Verificar edad del archivo de URLs (tokens expiran en ~1 hora)
    import time
    file_age_seconds = time.time() - os.path.getmtime(M3U8_FILE)
    file_age_minutes = file_age_seconds / 60
    
    if file_age_minutes > 55:  # Más de 55 minutos
        print(f"\n⚠️  Las URLs tienen {file_age_minutes:.0f} minutos de antigüedad")
        print("   Los tokens JWT expiran después de ~60 minutos")
        print("\n🔄 Regenerando URLs con tokens frescos...")
        print("   Ejecutando: python3 download_course_videos_selenium.py\n")
        
        result = subprocess.run(
            ["python3", "download_course_videos_selenium.py"],
            cwd=os.path.dirname(__file__) or "."
        )
        
        if result.returncode != 0:
            print("\n❌ Error regenerando URLs")
            return
        
        print("\n✅ URLs regeneradas con tokens frescos")
    
    # Leer URLs m3u8
    with open(M3U8_FILE, 'r') as f:
        m3u8_urls = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]
    
    total_urls = len(m3u8_urls)
    print(f"\n📋 Encontradas {total_urls} URLs de video")
    
    if total_urls == 0:
        print("⚠️  No se encontraron URLs válidas")
        return
    
    print(f"\n💾 Los videos se guardarán en: {OUTPUT_DIR}")
    
    print("\n" + "=" * 70)
    print("📥 DESCARGANDO VIDEOS")
    print("=" * 70 + "\n")
    
    # Descargar con barra de progreso
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    with tqdm(total=total_urls, desc="Descargando", unit="video") as pbar:
        for idx, url in enumerate(m3u8_urls, 1):
            # Extraer nombre del video de la URL
            try:
                video_id = url.split('/videos/')[1].split('_')[0]
                output_name = f"video_{idx:03d}_{video_id}.mp4"
            except:
                output_name = f"video_{idx:03d}.mp4"
            
            # Verificar si ya existe
            output_path = os.path.join(OUTPUT_DIR, output_name)
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                pbar.write(f"⏭️  Ya existe: {output_name} ({size_mb:.1f} MB)")
                skipped_count += 1
                pbar.update(1)
                continue
            
            pbar.set_description(f"[{idx}/{total_urls}] {output_name[:30]}")
            
            result = download_video_with_ytdlp(url, output_name, pbar)
            
            if result:
                success_count += 1
            else:
                failed_count += 1
            
            pbar.update(1)
    
    print("\n" + "=" * 70)
    print("✅ PROCESO COMPLETADO")
    print("=" * 70)
    
    # Resumen
    print(f"\n📊 Resumen:")
    print(f"   ✅ Descargados: {success_count}")
    if skipped_count > 0:
        print(f"   ⏭️  Ya existían: {skipped_count}")
    if failed_count > 0:
        print(f"   ❌ Fallidos: {failed_count}")
    print(f"   📹 Total: {total_urls}")
    
    # Listar videos descargados
    if os.path.exists(OUTPUT_DIR):
        videos = list(Path(OUTPUT_DIR).glob("*.mp4"))
        if videos:
            total_size = sum(v.stat().st_size for v in videos) / (1024 * 1024 * 1024)
            print(f"\n💾 {len(videos)} videos en '{OUTPUT_DIR}' ({total_size:.2f} GB)")
        else:
            print(f"\n⚠️  No se encontraron videos en '{OUTPUT_DIR}'")

if __name__ == "__main__":
    main()
