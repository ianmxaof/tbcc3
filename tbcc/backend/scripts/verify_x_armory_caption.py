"""One-off: print first armory caption after affiliate fix."""
from app.data.aof_x_buffer_armory import AOF_X_BUFFER_ARMORY_TEMPLATES
from app.database.session import SessionLocal
from app.services.aof_social_links import fill_armory_template

db = SessionLocal()
try:
    text = fill_armory_template(AOF_X_BUFFER_ARMORY_TEMPLATES[0]["text"], for_x=True, db=db)
    print(text)
    print(f"lootgod_count={text.count('aof_lootgod_bot')}")
finally:
    db.close()
