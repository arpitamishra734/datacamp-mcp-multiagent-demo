from typing import List, Dict, Optional
from pymongo import MongoClient
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.checkpoint.memory import MemorySaver
from datetime import datetime, timezone
import uuid

from promotion_tycoon.config import MONGODB_URI, DATABASE_NAME
from promotion_tycoon.tracing import log_trace, log_error


log_trace("🔌 Initializing MongoDB connections")

IN_MEMORY = {"packets": {}, "roles": {}, "projects": {}, "reports": {}}

try:
    pymongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    pymongo_client.server_info()
    db = pymongo_client[DATABASE_NAME]
    checkpointer = MongoDBSaver(pymongo_client)
    USE_MONGODB = True
    log_trace("✅ MongoDB connected", database=DATABASE_NAME)
except Exception as e:
    log_error("MongoDB Connection", e)
    checkpointer = MemorySaver()
    db = None
    USE_MONGODB = False
    log_trace("⚠️ Using in-memory storage (MongoDB unavailable)")

def create_packet(user_id: str, current_role: str = "", target_role: str = "") -> str:
    packet_id = str(uuid.uuid4())
    data = {
        "_id": packet_id,
        "packet_id": packet_id,
        "user_id": user_id,
        "current_role": current_role,
        "target_role": target_role,
        "created_at": datetime.now(timezone.utc),
        "phase": "setup",
    }
    if USE_MONGODB:
        try: db.packets.insert_one(data)
        except Exception as e: log_error("Create Packet DB", e)
    else:
        IN_MEMORY["packets"][packet_id] = data
    log_trace("💾 Packet created", packet_id=packet_id)
    return packet_id

def upsert_role(packet_id: str, role_def):
    role_data = {**role_def.model_dump(), "packet_id": packet_id}
    if USE_MONGODB:
        try: db.roles.update_one({"packet_id": packet_id}, {"$set": role_data}, upsert=True)
        except Exception as e: log_error("Upsert Role DB", e)
    else:
        IN_MEMORY["roles"][packet_id] = role_data
    log_trace("🎯 Role upserted", title=role_def.title)

def insert_projects(packet_id: str, projects: List):
    if USE_MONGODB:
        try:
            for proj in projects:
                db.projects.insert_one({**proj.model_dump(), "packet_id": packet_id})
        except Exception as e:
            log_error("Insert Projects DB", e)
    else:
        IN_MEMORY["projects"].setdefault(packet_id, [])
        for proj in projects:
            IN_MEMORY["projects"][packet_id].append({**proj.model_dump(), "packet_id": packet_id})
    log_trace("📁 Projects inserted", count=len(projects))

def upsert_report(packet_id: str, report):
    data = {**report.model_dump(), "packet_id": packet_id}
    if USE_MONGODB:
        try: db.reports.update_one({"packet_id": packet_id}, {"$set": data}, upsert=True)
        except Exception as e: log_error("Upsert Report DB", e)
    else:
        IN_MEMORY["reports"][packet_id] = data
    log_trace("📊 Report upserted")

def get_role_direct(packet_id: str) -> Optional[Dict]:
    if USE_MONGODB:
        try: return db.roles.find_one({"packet_id": packet_id})
        except Exception as e: log_error("Get Role DB", e); return None
    return IN_MEMORY["roles"].get(packet_id)

get_role = get_role_direct

def get_projects(packet_id: str) -> List[Dict]:
    if USE_MONGODB:
        try: return list(db.projects.find({"packet_id": packet_id}))
        except Exception as e: log_error("Get Projects DB", e); return []
    return IN_MEMORY["projects"].get(packet_id, [])

def get_report(packet_id: str) -> Optional[Dict]:
    if USE_MONGODB:
        try: return db.reports.find_one({"packet_id": packet_id})
        except Exception as e: log_error("Get Report DB", e); return None
    return IN_MEMORY["reports"].get(packet_id)

__all__ = [
    "checkpointer",
    "USE_MONGODB",
    "create_packet",
    "upsert_role",
    "insert_projects",
    "upsert_report",
    "get_role",
    "get_projects",
    "get_report",
]
