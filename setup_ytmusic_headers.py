import argparse
from pathlib import Path

from ytmusicapi import setup


def normalize_headers_text(headers_raw: str) -> str:
    lines = [line.strip() for line in headers_raw.splitlines() if line.strip()]
    if not lines:
        return ""

    # If headers are already in "key: value" format, keep them as-is.
    if any(": " in line for line in lines):
        return "\n".join(lines)

    # Convert "key\nvalue" pairs (common copy format) into "key: value".
    normalized: list[str] = []
    i = 0
    while i < len(lines):
        key = lines[i]
        value = lines[i + 1] if i + 1 < len(lines) else ""
        normalized.append(f"{key}: {value}")
        i += 2
    return "\n".join(normalized)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera browser.json de YouTube Music leyendo headers desde un archivo de texto."
    )
    parser.add_argument(
        "--headers-file",
        default="yt_headers.txt",
        help="Ruta al archivo con los request headers (default: yt_headers.txt).",
    )
    parser.add_argument(
        "--output",
        default="browser.json",
        help="Archivo de salida para autenticacion de ytmusicapi (default: browser.json).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    headers_path = Path(args.headers_file)

    if not headers_path.exists():
        raise FileNotFoundError(
            f"No existe {headers_path}. Crea el archivo y pega ahi los request headers."
        )

    headers_raw = headers_path.read_text(encoding="utf-8").strip()
    if not headers_raw:
        raise ValueError(f"El archivo {headers_path} esta vacio.")

    normalized_headers = normalize_headers_text(headers_raw)
    setup(filepath=args.output, headers_raw=normalized_headers)
    print(f"Listo. Se genero {args.output}")


if __name__ == "__main__":
    main()
