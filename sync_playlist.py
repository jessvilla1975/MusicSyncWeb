import argparse
import json
import os
import re
from typing import Callable, Dict, List, Optional, Tuple

import requests
import spotipy
from rapidfuzz import fuzz
from spotipy.oauth2 import SpotifyOAuth, SpotifyPKCE
from spotipy.oauth2 import SpotifyClientCredentials
from ytmusicapi import YTMusic


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\(.*?\)|\[.*?\]", "", value)
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def build_spotify_client() -> spotipy.Spotify:
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    use_public_mode = os.getenv("SPOTIFY_PUBLIC_MODE", "1").strip() in {"1", "true", "yes"}

    if not client_id:
        raise RuntimeError("Falta SPOTIPY_CLIENT_ID.")

    # Public playlist mode: no user login, only app credentials.
    if use_public_mode:
        if not client_secret:
            raise RuntimeError(
                "En modo publico falta SPOTIPY_CLIENT_SECRET. "
                "Define SPOTIFY_PUBLIC_MODE=0 si quieres usar login de usuario."
            )
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        return spotipy.Spotify(auth_manager=auth_manager)

    scope = "playlist-read-private playlist-read-collaborative"
    # If client secret is unavailable, use PKCE flow (public client).
    if client_secret:
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=True,
            cache_path=".spotify_cache",
        )
    else:
        auth_manager = SpotifyPKCE(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=True,
            cache_path=".spotify_cache",
        )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    results = sp.playlist_items(
        playlist_id,
        additional_types=["track"],
        fields="items(track(name,artists(name),id,is_local)),next",
        limit=100,
    )

    while True:
        for item in results.get("items", []):
            track = item.get("track")
            if not track or track.get("is_local"):
                continue
            artists = [a["name"] for a in track.get("artists", []) if a.get("name")]
            items.append(
                {
                    "name": track.get("name", ""),
                    "artist": ", ".join(artists) if artists else "",
                    "spotify_id": track.get("id", ""),
                }
            )
        if not results.get("next"):
            break
        results = sp.next(results)
    return items


def get_playlist_tracks_from_web(playlist_id: str) -> List[Dict[str, str]]:
    response = requests.get(
        f"https://open.spotify.com/embed/playlist/{playlist_id}",
        timeout=20,
    )
    response.raise_for_status()
    html = response.text

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError("No se pudieron extraer datos de la playlist publica de Spotify.")

    payload = json.loads(match.group(1))
    items: List[Dict[str, str]] = []
    seen_uris = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            uri = node.get("uri")
            if isinstance(uri, str) and uri.startswith("spotify:track:") and uri not in seen_uris:
                title = str(node.get("title") or "").strip()
                artist = str(node.get("subtitle") or "").strip()
                if title:
                    seen_uris.add(uri)
                    items.append(
                        {
                            "name": title,
                            "artist": artist,
                            "spotify_id": uri.split(":")[-1],
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return items


def search_best_ytmusic_match(yt: YTMusic, title: str, artist: str) -> Optional[str]:
    query = f"{title} {artist}".strip()
    results = yt.search(query, filter="songs", limit=10)
    if not results:
        return None

    best_score = -1
    best_video_id = None
    title_n = normalize_text(title)
    artist_n = normalize_text(artist)

    for row in results:
        video_id = row.get("videoId")
        if not video_id:
            continue
        row_title = normalize_text(row.get("title", ""))
        artist_names = ", ".join([a.get("name", "") for a in row.get("artists", []) if a.get("name")])
        row_artist = normalize_text(artist_names)

        score_title = fuzz.ratio(title_n, row_title)
        score_artist = fuzz.ratio(artist_n, row_artist) if artist_n else 50
        score = int(score_title * 0.7 + score_artist * 0.3)

        if score > best_score:
            best_score = score
            best_video_id = video_id

    if best_score < 65:
        return None
    return best_video_id


def get_or_create_ytmusic_playlist(yt: YTMusic, name: str) -> str:
    for pl in yt.get_library_playlists(limit=500):
        if normalize_text(pl.get("title", "")) == normalize_text(name):
            return pl["playlistId"]
    return yt.create_playlist(name, description=f"Sincronizada desde Spotify: {name}")


def get_existing_video_ids(yt: YTMusic, playlist_id: str) -> set:
    playlist = yt.get_playlist(playlist_id, limit=10000)
    tracks = playlist.get("tracks", [])
    return {t.get("videoId") for t in tracks if t.get("videoId")}


def sync_spotify_to_ytmusic(
    spotify_playlist_id: str,
    ytmusic_playlist_name: str,
    ytmusic_playlist_id: Optional[str],
    ytmusic_auth_file: str,
    spotify_source: str,
    progress_callback: Optional[Callable[[str, Dict[str, str]], None]] = None,
) -> Tuple[int, int]:
    yt = YTMusic(ytmusic_auth_file)

    if spotify_source == "web":
        tracks = get_playlist_tracks_from_web(spotify_playlist_id)
    else:
        sp = build_spotify_client()
        tracks = get_playlist_tracks(sp, spotify_playlist_id)

    if not tracks:
        print("No se encontraron canciones en Spotify.")
        if progress_callback:
            progress_callback("done", {"added": "0", "not_found": "0", "total": "0"})
        return 0, 0

    if progress_callback:
        progress_callback("start", {"total": str(len(tracks))})

    yt_playlist_id = ytmusic_playlist_id or get_or_create_ytmusic_playlist(yt, ytmusic_playlist_name)
    existing_ids = get_existing_video_ids(yt, yt_playlist_id)

    added = 0
    not_found = 0

    for idx, track in enumerate(tracks, start=1):
        title = track["name"]
        artist = track["artist"]
        video_id = search_best_ytmusic_match(yt, title, artist)

        if not video_id:
            not_found += 1
            print(f"[{idx}/{len(tracks)}] No encontrada: {title} - {artist}")
            if progress_callback:
                progress_callback(
                    "not_found",
                    {
                        "index": str(idx),
                        "total": str(len(tracks)),
                        "title": title,
                        "artist": artist,
                    },
                )
            continue

        if video_id in existing_ids:
            print(f"[{idx}/{len(tracks)}] Ya existe: {title} - {artist}")
            if progress_callback:
                progress_callback(
                    "exists",
                    {
                        "index": str(idx),
                        "total": str(len(tracks)),
                        "title": title,
                        "artist": artist,
                    },
                )
            continue

        yt.add_playlist_items(yt_playlist_id, [video_id])
        existing_ids.add(video_id)
        added += 1
        print(f"[{idx}/{len(tracks)}] Agregada: {title} - {artist}")
        if progress_callback:
            progress_callback(
                "added",
                {
                    "index": str(idx),
                    "total": str(len(tracks)),
                    "title": title,
                    "artist": artist,
                },
            )

    if progress_callback:
        progress_callback(
            "done",
            {"added": str(added), "not_found": str(not_found), "total": str(len(tracks))},
        )
    return added, not_found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza una playlist de Spotify a YouTube Music."
    )
    parser.add_argument(
        "--spotify-playlist-id",
        required=True,
        help="ID o URI de playlist de Spotify",
    )
    parser.add_argument(
        "--spotify-source",
        choices=["web", "api"],
        default="web",
        help="Fuente para leer Spotify: web (sin Premium/app) o api (requiere credenciales).",
    )
    parser.add_argument(
        "--yt-playlist-name",
        required=True,
        help="Nombre de la playlist en YouTube Music",
    )
    parser.add_argument(
        "--yt-playlist-id",
        default=None,
        help="ID de playlist de YouTube Music (si se indica, se usa esta playlist directamente)",
    )
    parser.add_argument(
        "--yt-auth",
        default="oauth.json",
        help="Ruta al archivo de autenticacion de ytmusicapi (default: oauth.json)",
    )
    return parser.parse_args()


def normalize_spotify_playlist_id(value: str) -> str:
    value = value.strip()
    if value.startswith("spotify:playlist:"):
        return value.split(":")[-1]
    if "open.spotify.com/playlist/" in value:
        return value.split("playlist/")[-1].split("?")[0]
    if "spotify.link/" in value:
        response = requests.get(value, timeout=20, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url
        if "open.spotify.com/playlist/" in final_url:
            return final_url.split("playlist/")[-1].split("?")[0]
    return value


def normalize_ytmusic_playlist_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if "music.youtube.com/playlist?list=" in value:
        return value.split("list=")[-1].split("&")[0]
    return value      


if __name__ == "__main__":
    args = parse_args()
    spotify_playlist_id = normalize_spotify_playlist_id(args.spotify_playlist_id)
    ytmusic_playlist_id = normalize_ytmusic_playlist_id(args.yt_playlist_id)
    added, not_found = sync_spotify_to_ytmusic(
        spotify_playlist_id=spotify_playlist_id,
        ytmusic_playlist_name=args.yt_playlist_name,
        ytmusic_playlist_id=ytmusic_playlist_id,
        ytmusic_auth_file=args.yt_auth,
        spotify_source=args.spotify_source,
    )
    print("-" * 60)
    print(f"Completado. Agregadas: {added} | No encontradas: {not_found}")
