"""音乐推荐 Skill - 基于网易云音乐 API"""

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

NETEASE_API = "https://music.163.com/api"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://music.163.com",
}

# 网易云官方热门歌单 ID
PLAYLISTS = {
    "热歌榜": 3778678,
    "新歌榜": 3779629,
    "飙升榜": 19723756,
    "原创榜": 2884035,
}


class MusicSkill(BaseSkill):
    name = "music"
    description = "音乐搜索和热门推荐（网易云音乐）"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_music",
                description=(
                    "搜索歌曲。输入歌名、歌手名或关键词，"
                    "返回匹配的歌曲列表（歌名、歌手、专辑）。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词，如歌名、歌手名",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回数量，默认10",
                            "default": 10,
                        },
                    },
                    "required": ["keyword"],
                },
                handler=self._search_music,
            ),
            ToolDefinition(
                name="music_hot_list",
                description=(
                    "获取音乐热门榜单。支持: 热歌榜、新歌榜、飙升榜、原创榜。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "list_name": {
                            "type": "string",
                            "description": "榜单名称: 热歌榜/新歌榜/飙升榜/原创榜，默认热歌榜",
                            "default": "热歌榜",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回数量，默认10",
                            "default": 10,
                        },
                    },
                },
                handler=self._hot_list,
            ),
        ]

    def _search_music(self, keyword: str, limit: int = 10) -> str:
        if not keyword.strip():
            return "请提供搜索关键词。"

        try:
            resp = httpx.get(
                f"{NETEASE_API}/search/get/web",
                params={"s": keyword, "type": 1, "limit": limit},
                timeout=10,
                headers=_HEADERS,
            )
            data = resp.json()
            songs = data.get("result", {}).get("songs", [])
        except Exception as e:
            return f"搜索失败: {e}"

        if not songs:
            return f"没有找到与 '{keyword}' 相关的歌曲。"

        lines = [f"搜索: {keyword}  (共 {len(songs)} 首)"]
        lines.append("")
        for i, song in enumerate(songs[:limit], 1):
            name = song.get("name", "")
            artists = "/".join(a["name"] for a in song.get("artists", []))
            album = song.get("album", {}).get("name", "")
            song_id = song.get("id", "")
            url = f"https://music.163.com/#/song?id={song_id}" if song_id else ""
            lines.append(f"{i}. {name} - {artists}")
            if album:
                lines.append(f"   专辑: {album}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        return "\n".join(lines)

    def _hot_list(self, list_name: str = "热歌榜", limit: int = 10) -> str:
        playlist_id = PLAYLISTS.get(list_name)
        if not playlist_id:
            available = "、".join(PLAYLISTS.keys())
            return f"不支持的榜单 '{list_name}'，可选: {available}"

        try:
            resp = httpx.get(
                f"{NETEASE_API}/playlist/detail",
                params={"id": playlist_id},
                timeout=10,
                headers=_HEADERS,
            )
            data = resp.json()
            tracks = data.get("result", {}).get("tracks", [])
        except Exception as e:
            return f"获取榜单失败: {e}"

        if not tracks:
            return f"获取 {list_name} 失败，请稍后再试。"

        lines = [f"【{list_name}】Top {min(limit, len(tracks))}"]
        lines.append("")
        for i, track in enumerate(tracks[:limit], 1):
            name = track.get("name", "")
            artists = "/".join(a["name"] for a in track.get("artists", []))
            song_id = track.get("id", "")
            url = f"https://music.163.com/#/song?id={song_id}" if song_id else ""
            lines.append(f"{i}. {name} - {artists}")
            if url:
                lines.append(f"   {url}")

        return "\n".join(lines)


register(MusicSkill)
