from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from database import AsyncSessionLocal
from tasks import sync_user_games, sync_game_achievements
from models import User
import httpx
import os

app = FastAPI(title="Xbox Platinum API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",          
        "https://onyx.thomaspercival.dev",     
        "https://www.thomaspercival.dev"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok",
                "message": "Database connection successful"}
    except Exception as e:
        return {"status": "error",
                "message": f"Database connection failed: {str(e)}"}

@app.post("/sync/profile/{gamertag}")
async def sync_profile(gamertag: str, db: AsyncSession = Depends(get_db)):
    api_key = os.getenv("XBOX_API_KEY")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://xbl.io/api/v2/search/{gamertag}",
            headers={"X-Authorization": api_key}
        )
    
    if response.status_code != 200:
        return {
            "debug_error": f"Failed with status {response.status_code}",
            "raw_text": response.text
        }
        
    data = response.json()

    people = data.get("content", {}).get("people", [])
    if not people:
        return {"error": "Gamertag not found"}

    profile = people[0]
    xuid = profile.get("xuid")
    formatted_gamertag = profile.get("uniqueModernGamertag") or profile.get("gamertag")
    avatar_url = profile.get("displayPicRaw")

    if not xuid:
        return {"error": "XUID not found for the provided gamertag"}

    stmt = insert(User).values(
        xuid=xuid,
        gamertag=formatted_gamertag,
        avatar_url=avatar_url
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["xuid"],
        set_={
            "gamertag": formatted_gamertag,
            "avatar_url": avatar_url
        }
    )

    await db.execute(stmt)
    await db.commit()

    sync_user_games.delay(xuid)

    return {
        "status": "queued",
        "message": "Profile created. Syncing games",
        "xuid": xuid,
        "gamertag": formatted_gamertag,
    }

@app.post("/sync/achievements/{xuid}/{title_id}")
async def sync_achievements(xuid: str, title_id: str):
    sync_game_achievements.delay(xuid, title_id)
    return {"status": "queued", "message": "Achievements syncing initiated"}

@app.post("/sync/refresh/{xuid}")
async def refresh_profile(xuid: str):
    sync_user_games.delay(xuid)
    return {"status": "queued", "message": "Global profile sync started"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)