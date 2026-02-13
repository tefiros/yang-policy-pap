# app/main.py
__name__ = "Policy Administration Service"
__version__ = "0.5.0"

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional, List
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
            last_modified TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS policy_versions (
            policy_id TEXT,
            description TEXT,
            language TEXT,
            rule TEXT,
            owner TEXT,
            version TEXT,
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

class AuthPolicyRequest(BaseModel):
    auth_policy: PolicyData = Field(..., alias="auth-policy:policy")

    class Config:
        allow_population_by_field_name = True

class AuthPolicyResponse(BaseModel):
    policy_id: str
    auth_policy: PolicyData = Field(..., alias="auth-policy:policy")
    version: str
    last_modified: str
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
    return f"package policies.policy_{safe_id}\n\n{rule}"

def save_policy_version(policy_id: str, policy: PolicyData, version:str, last_modified:str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO policy_versions VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        policy_id,
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        version,
        last_modified
    ))
    conn.commit()
    conn.close()

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
        last_modified=row[6]
    )
    return {"policy_id": policy_id, "auth-policy:policy": policy}

@app.get("/policies/{policy_id}/history", tags=["Read"])
def get_policy_history(policy_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT version, last_modified, description, language, rule, owner
        FROM policy_versions
        WHERE policy_id = ?
        ORDER BY last_modified ASC
    """, (policy_id,))
    rows = cursor.fetchall()
    conn.close()
    history = [
        {
            "version": r[0],
            "last_modified": r[1],
            "description": r[2],
            "language": r[3],
            "rule": r[4],
            "owner": r[5]
        } for r in rows
    ]
    return {"policy_id": policy_id, "history": history}

@app.post("/policies", response_model=AuthPolicyResponse, tags=["Create"])
def register_policy(request: AuthPolicyRequest):
    policy = request.auth_policy
    policy_id = str(uuid.uuid4())
    now = now_iso()

    last_modified = now
    version = now

    # Guardar en OPA
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
        INSERT INTO policies VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        policy_id,
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        version,
        last_modified
    ))
    conn.commit()
    conn.close()

    # Guardar versión inicial
    save_policy_version(policy_id, policy, version, last_modified)

    return {"policy_id": policy_id, "auth-policy:policy": policy}

@app.put("/policies/{policy_id}", response_model=AuthPolicyResponse, tags=["Update"])
def update_policy(policy_id: str, request: AuthPolicyRequest):
    policy_in = request.auth_policy
    now = now_iso()
    last_modified = now
    version = now

    # Guardar versión anterior antes de actualizar
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM policies WHERE policy_id = ?", (policy_id,))
    old_row = cursor.fetchone()
    if not old_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Policy not found")
    old_policy = PolicyData(
        description=old_row[1],
        language=old_row[2],
        rule=old_row[3],
        owner=old_row[4],
        version=old_row[5],
        last_modified=old_row[6]
    )
    save_policy_version(policy_id, old_policy, version, last_modified)

    # Actualizar en OPA
    if policy_in.language == "rego":
        rule_with_package = build_unique_rego_package(policy_id, policy_in.rule)
        try:
            opa_client.update_policy_from_string(rule_with_package, policy_id)
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=400, detail=str(e))

    # Actualizar SQLite
    cursor.execute("""
        UPDATE policies
        SET description=?, language=?, rule=?, owner=?, version=?, last_modified=?
        WHERE policy_id=?
    """, (
        policy_in.description,
        policy_in.language,
        policy_in.rule,
        policy_in.owner,
        version,
        last_modified,
        policy_id
    ))
    conn.commit()
    conn.close()

    return {"policy_id": policy_id, "auth-policy:policy": policy_in}

@app.put("/policies/{policy_id}/rollback/{version}", response_model=AuthPolicyResponse, tags=["Update"])
def rollback_policy(policy_id: str, version: str):
    now = now_iso()
    last_modified = now
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT description, language, rule, owner, version, last_modified
        FROM policy_versions
        WHERE policy_id=? AND version=?
    """, (policy_id, version))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")
    policy = PolicyData(
        description=row[0],
        language=row[1],
        rule=row[2],
        owner=row[3],
        version=row[4],
        last_modified=row[5]
    )
    # Guardar versión actual antes de rollback
    cursor.execute("SELECT * FROM policies WHERE policy_id=?", (policy_id,))
    current_row = cursor.fetchone()
    if current_row:
        current_policy = PolicyData(
            description=current_row[1],
            language=current_row[2],
            rule=current_row[3],
            owner=current_row[4],
            version=current_row[5],
            last_modified=current_row[6]
        )
        save_policy_version(policy_id, current_policy, version, last_modified)
    # Actualizar SQLite
    cursor.execute("""
        UPDATE policies
        SET description=?, language=?, rule=?, owner=?, version=?, last_modified=?
        WHERE policy_id=?
    """, (
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        version,
        last_modified,
        policy_id
    ))
    conn.commit()
    conn.close()
    # Actualizar OPA
    if policy.language == "rego":
        rule_with_package = build_unique_rego_package(policy_id, policy.rule)
        try:
            opa_client.update_policy_from_string(rule_with_package, policy_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"policy_id": policy_id, "auth-policy:policy": policy}

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
