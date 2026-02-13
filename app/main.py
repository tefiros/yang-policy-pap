# app/main.py
__name__ = "Policy Administration Service"
__version__ = "0.4.0"

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional
import uuid
import datetime
import sqlite3
import os
from opa_client.opa import OpaClient

# ----------------------
# CONFIG
# ----------------------
OPA_HOSTNAME = os.getenv("OPA_HOSTNAME", "localhost")
OPA_PORT = int(os.getenv("OPA_PORT", "8181"))
DB_FILE = "policies.db"

app = FastAPI(title=__name__, version=__version__)
opa_client = OpaClient(host=OPA_HOSTNAME, port=OPA_PORT)

# ----------------------
# DATABASE INIT
# ----------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS policies (
            policy_id TEXT PRIMARY KEY,
            description TEXT,
            language TEXT,
            rule TEXT,
            owner TEXT,
            version TEXT,
            created TEXT,
            last_modified TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ----------------------
# MODELS
# ----------------------
class PolicyData(BaseModel):
    description: str
    language: Literal["rego", "cedar", "alfa"]
    rule: str
    owner: str
    version: Optional[str] = None
    created: Optional[str] = None
    last_modified: Optional[str] = None

class AuthPolicyRequest(BaseModel):
    auth_policy: PolicyData = Field(..., alias="auth-policy:policy")

    class Config:
        allow_population_by_field_name = True

class AuthPolicyResponse(BaseModel):
    policy_id: str
    auth_policy: PolicyData = Field(..., alias="auth-policy:policy")

    class Config:
        allow_population_by_field_name = True

# ----------------------
# HELPERS
# ----------------------
def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def build_unique_rego_package(policy_id: str, rule: str):
    safe_id = policy_id.replace("-", "_")
    # Prepend 'p_' para que empiece con letra
    return f"package policies.p_{safe_id}\n\n{rule}"

# ----------------------
# ROUTES
# ----------------------
@app.get("/policies", tags=["Read"])
def get_policies():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT policy_id FROM policies")
    rows = cursor.fetchall()
    conn.close()
    return {"policies": [r[0] for r in rows]}

@app.get("/policies/{policy_id}", response_model=AuthPolicyResponse, tags=["Read"])
def get_policy(policy_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy = PolicyData(
        description=row[1],
        language=row[2],
        rule=row[3],
        owner=row[4],
        version=row[5],
        created=row[6],
        last_modified=row[7]
    )
    return {"policy_id": policy_id, "auth-policy:policy": policy}

@app.post("/policies", response_model=AuthPolicyResponse, tags=["Create"])
def register_policy(request: AuthPolicyRequest):
    policy = request.auth_policy
    policy_id = str(uuid.uuid4())
    now = now_iso()

    # Generamos timestamps automáticamente
    policy.created = now
    policy.last_modified = now
    policy.version = now

    # Guardar en OPA si es Rego
    if policy.language == "rego":
        rule_with_package = build_unique_rego_package(policy_id, policy.rule)
        try:
            opa_client.update_policy_from_string(rule_with_package, policy_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Guardar en SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO policies VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        policy_id,
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        policy.version,
        policy.created,
        policy.last_modified
    ))
    conn.commit()
    conn.close()

    return {"policy_id": policy_id, "auth-policy:policy": policy}

@app.put("/policies/{policy_id}", response_model=AuthPolicyResponse, tags=["Update"])
def update_policy(policy_id: str, request: AuthPolicyRequest):
    policy_in = request.auth_policy
    now = now_iso()
    policy_in.last_modified = now
    policy_in.version = now

    # Actualizar en OPA si es Rego
    if policy_in.language == "rego":
        rule_with_package = build_unique_rego_package(policy_id, policy_in.rule)
        try:
            opa_client.update_policy_from_string(rule_with_package, policy_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Actualizar SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE policies
        SET description=?, language=?, rule=?, owner=?, version=?, last_modified=?
        WHERE policy_id=?
    """, (
        policy_in.description,
        policy_in.language,
        policy_in.rule,
        policy_in.owner,
        policy_in.version,
        policy_in.last_modified,
        policy_id
    ))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Policy not found")
    conn.commit()
    conn.close()

    return {"policy_id": policy_id, "auth-policy:policy": policy_in}

@app.delete("/policies/{policy_id}", tags=["Delete"])
def delete_policy(policy_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM policies WHERE policy_id = ?", (policy_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    try:
        opa_client.delete_policy(policy_id)
    except Exception:
        pass

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {"message": f"Policy '{policy_id}' deleted successfully"}

# ----------------------
# MAIN
# ----------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
