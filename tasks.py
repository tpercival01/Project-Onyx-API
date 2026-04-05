import os
import httpx
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from celery_app import celery_app
from database import AsyncSessionLocal
from models import Game, Achievement
from sqlalchemy.dialects.postgresql import insert

@celery_app.task
def sync_user_games(xuid: str):
    print(f"Starting game sync for {xuid}.")
    asyncio.run(async_sync_user_games(xuid))
    return f"Finished syncing games for {xuid}"

@celery_app.task
def sync_game_achievements(xuid: str, title_id: str):
    print(f"Starting sync for achievements of {xuid} and title {title_id}.")
    asyncio.run(async_sync_game_achievements(xuid, title_id))
    return f"Finished syncing achievements for {xuid} and title {title_id}"

async def async_sync_user_games(xuid: str):
    load_dotenv()
    api_key = os.getenv("XBOX_API_KEY")
    if not api_key: return

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://xbl.io/api/v2/titles/{xuid}",
            headers={"X-Authorization": api_key, "Accept-Language": "en-GB"},
            timeout=30.0
        )
    data = response.json() if response.status_code == 200 else {}
    titles = data.get("content", {}).get("titles", [])

    games_to_insert = []
    for title in titles:
        ach_data = title.get("achievement", {})
        
        history = title.get("titleHistory", {})
        last_played_str = history.get("lastTimePlayed")
        last_played = None
        if last_played_str:
            last_played = datetime.fromisoformat(last_played_str.replace("Z", "+00:00")).replace(tzinfo=None)

        games_to_insert.append({
            "id": str(title["titleId"]),
            "user_xuid": xuid,
            "name": title.get("name", "Unknown Game"),
            "earned_achievements": int(ach_data.get("currentAchievements") or 0),
            "total_achievements": int(ach_data.get("totalAchievements") or 0),
            "current_gamerscore": int(ach_data.get("currentGamerscore") or 0),
            "total_gamerscore": int(ach_data.get("totalGamerscore") or 0),
            "last_time_played": last_played,
            "display_image": title.get("displayImage")
        })
    if not games_to_insert: return

    async with AsyncSessionLocal() as db:
        stmt = insert(Game).values(games_to_insert)
        # Upsert restores the correct Gamerscores!
        stmt = stmt.on_conflict_do_update(
            index_elements=['id'],
            set_={
                "name": stmt.excluded.name,
                "earned_achievements": stmt.excluded.earned_achievements,
                "total_achievements": stmt.excluded.total_achievements,
                "current_gamerscore": stmt.excluded.current_gamerscore,
                "total_gamerscore": stmt.excluded.total_gamerscore,
                "last_time_played": stmt.excluded.last_time_played,
                "display_image": stmt.excluded.display_image
            }
        )
        await db.execute(stmt)
        await db.commit()

async def async_sync_game_achievements(xuid: str, title_id: str):
    load_dotenv()
    api_key = os.getenv("XBOX_API_KEY")
    if not api_key: return

    def extract_achievements(data_dict):
        if not data_dict: return []
        if isinstance(data_dict.get("achievements"), list): return data_dict["achievements"]
        if isinstance(data_dict.get("content", {}).get("achievements"), list): return data_dict["content"]["achievements"]
        if isinstance(data_dict.get("content"), list): return data_dict["content"]
        return []

    async with httpx.AsyncClient() as client:
        url = f"https://xbl.io/api/v2/achievements/player/{xuid}/{title_id}"
        response = await client.get(url, headers={"X-Authorization": api_key}, timeout=30.0)
        data = response.json() if response.status_code == 200 else {}
        raw_achievements = extract_achievements(data)
        
        if not raw_achievements:
            cat_url = f"https://xbl.io/api/v2/achievements/player/{xuid}/title/{title_id}"
            prog_url = f"https://xbl.io/api/v2/achievements/x360/{xuid}/title/{title_id}"
            
            cat_resp = await client.get(cat_url, headers={"X-Authorization": api_key}, timeout=30.0)
            prog_resp = await client.get(prog_url, headers={"X-Authorization": api_key}, timeout=30.0)
            
            catalog_list = extract_achievements(cat_resp.json() if cat_resp.status_code == 200 else {})
            progress_list = extract_achievements(prog_resp.json() if prog_resp.status_code == 200 else {})
            
            progress_dict = {str(ach.get("id")): ach for ach in progress_list}
            for ach in catalog_list:
                ach_id = str(ach.get("id"))
                if ach_id in progress_dict:
                    ach["is_force_unlocked"] = True
                    prog_ach = progress_dict[ach_id]
                    if prog_ach.get("imageUnlocked"): ach["imageUnlocked"] = prog_ach.get("imageUnlocked")
                    if prog_ach.get("imageLocked"): ach["imageLocked"] = prog_ach.get("imageLocked")
            raw_achievements = catalog_list

    if not raw_achievements: return

    achievements_to_insert = []
    for ach in raw_achievements:
        gs = 0
        rewards = ach.get("rewards", [])
        if rewards and isinstance(rewards, list) and len(rewards) > 0:
            gs = int(rewards[0].get("value", 0))
        elif ach.get("gamerscore") is not None:
            gs = int(ach.get("gamerscore", 0))

        is_unlocked = (
            ach.get("is_force_unlocked") is True or
            ach.get("progressState") == "Achieved" or 
            ach.get("unlocked") is True or 
            ach.get("isUnlocked") is True
        )

        icon = None
        media = ach.get("mediaAssets", [])
        if media and isinstance(media, list) and len(media) > 0: icon = media[0].get("url")
        if not icon: icon = ach.get("imageUnlocked") or ach.get("imageLocked")
        if icon and icon.startswith("http://"): icon = icon.replace("http://", "https://")

        achievements_to_insert.append({
            "id": f"{xuid}_{title_id}_{ach.get('id')}",
            "user_xuid": xuid,
            "title_id": str(title_id),
            "name": ach.get("name", "Unknown"),
            "description": ach.get("description") or ach.get("lockedDescription") or "Secret Achievement",
            "gamerscore": gs,
            "is_unlocked": is_unlocked,
            "icon_url": icon
        })

    async with AsyncSessionLocal() as db:
        stmt = insert(Achievement).values(achievements_to_insert)
        stmt = stmt.on_conflict_do_update(
            index_elements=['id'],
            set_={"is_unlocked": stmt.excluded.is_unlocked, "icon_url": stmt.excluded.icon_url}
        )
        await db.execute(stmt)
        await db.commit()