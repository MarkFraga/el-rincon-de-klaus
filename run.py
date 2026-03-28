import sys
import os
import shutil
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Set ffmpeg path from imageio_ffmpeg if system ffmpeg not found
if not shutil.which("ffmpeg"):
    try:
        import imageio_ffmpeg
        ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except ImportError:
        pass


def check_requirements():
    if not shutil.which("ffmpeg"):
        try:
            import imageio_ffmpeg
            print("  [OK] ffmpeg (via imageio-ffmpeg)")
        except ImportError:
            print("  [ERROR] ffmpeg no encontrado. Instala: pip install imageio-ffmpeg")
            sys.exit(1)
    else:
        print("  [OK] ffmpeg")

    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print("  [ERROR] .env no encontrado. Crea uno con tu GEMINI_API_KEY.")
        sys.exit(1)
    print("  [OK] .env configurado")
    print()


def main():
    print()
    print("  ======================================")
    print("    EL RINCON DE KLAUS")
    print("    Podcast Multi-Agente con IA")
    print("  ======================================")
    print()

    check_requirements()

    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"

    print(f"  Servidor iniciando en:")
    print(f"    PC:     http://localhost:8000")
    print(f"    iPhone: http://{local_ip}:8000")
    print()
    print("  En tu iPhone:")
    print(f"  1. Abre Safari -> http://{local_ip}:8000")
    print("  2. Toca Compartir -> 'Anadir a pantalla de inicio'")
    print("  3. Listo! La app aparecera como nativa")
    print()

    import uvicorn
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
