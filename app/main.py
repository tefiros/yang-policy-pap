# app/main.py
__name__ = "Policy Administration Service"
__version__ = "1.0.0"

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import uuid
import datetime
import sqlite3
import os
from opa_client.opa import OpaClient

# ----------------------
# CONFIG
# ----------------------
OPA_HOSTNAME = os.getenv("OPA_HOSTNAME")
OPA_PORT = os.getenv("OPA_PORT")
DB_FILE = "policies.db"

app = FastAPI(title=__name__, version=__version__)
opa_client = OpaClient(host=OPA_HOSTNAME, port=int(OPA_PORT))

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
    rule: str   # El package ya viene dentro
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


def save_policy_version(policy_id, description, language, rule, owner, version, last_modified):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO policy_versions
        (policy_id, description, language, rule, owner, version, last_modified)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        policy_id,
        description,
        language,
        rule,
        owner,
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
    cursor.execute("SELECT * FROM policies WHERE policy_id=?", (policy_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")

    policy = PolicyData(
        description=row[1],
        language=row[2],
        rule=row[3],
        owner=row[4]
    )

    return AuthPolicyResponse.model_validate({
        "policy_id": policy_id,
        "auth-policy:policy": policy,
        "version": row[5],
        "last_modified": row[6]
    })


@app.get("/policies/{policy_id}/history", tags=["Read"])
def get_policy_history(policy_id: str):

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT description, language, rule, owner, version, last_modified
        FROM policy_versions
        WHERE policy_id=?
        ORDER BY last_modified ASC
    """, (policy_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Policy not found")

    history = [
        {
            "description": r[0],
            "language": r[1],
            "rule": r[2],
            "owner": r[3],
            "version": r[4],
            "last_modified": r[5]
        }
        for r in rows
    ]

    return {
        "policy_id": policy_id,
        "history": history
    }


# ----------------------
# CREATE
# ----------------------

@app.post("/policies", response_model=AuthPolicyResponse, tags=["Create"])
def register_policy(request: AuthPolicyRequest):

    policy = request.auth_policy
    policy_id = str(uuid.uuid4())
    version = now_iso()

    if policy.language == "rego":
        try:
            opa_client.update_policy_from_string(
                policy.rule,
                policy_id
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO policies
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        policy_id,
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        version,
        version
    ))

    conn.commit()
    conn.close()

    save_policy_version(
        policy_id,
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        version,
        version
    )

    return AuthPolicyResponse.model_validate({
        "policy_id": policy_id,
        "auth-policy:policy": policy,
        "version": version,
        "last_modified": version
    })


# ----------------------
# UPDATE
# ----------------------

@app.put("/policies/{policy_id}", response_model=AuthPolicyResponse, tags=["Update"])
def update_policy(policy_id: str, request: AuthPolicyRequest):
    policy = request.auth_policy
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM policies WHERE policy_id=?", (policy_id,))
    row = cursor.fetchone()
    new_version = now_iso()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Policy not found")

    save_policy_version(
        policy_id,
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        new_version,
        new_version
    )

    policy = request.auth_policy


    if policy.language == "rego":
        try:
            opa_client.update_policy_from_string(
                policy.rule,
                policy_id
            )
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=400, detail=str(e))

    cursor.execute("""
        UPDATE policies
        SET description=?, language=?, rule=?, owner=?, version=?, last_modified=?
        WHERE policy_id=?
    """, (
        policy.description,
        policy.language,
        policy.rule,
        policy.owner,
        new_version,
        new_version,
        policy_id
    ))

    conn.commit()
    conn.close()

    return AuthPolicyResponse.model_validate({
        "policy_id": policy_id,
        "auth-policy:policy": policy,
        "version": new_version,
        "last_modified": new_version
    })

# ----------------------
# ROLLBACK
# ----------------------
@app.put("/policies/{policy_id}/rollback/{version}", response_model=AuthPolicyResponse, tags=["Update"])
def rollback_policy(policy_id: str, version: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Buscar la versión histórica indicada
    cursor.execute("""
        SELECT description, language, rule, owner
        FROM policy_versions
        WHERE policy_id=? AND version=?
    """, (policy_id, version))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")

    description, language, rule, owner = row

    last_modified = now_iso() 


    cursor.execute("""
        UPDATE policies
        SET description=?, language=?, rule=?, owner=?, version=?, last_modified=?
        WHERE policy_id=?
    """, (
        description,
        language,
        rule,
        owner,
        version,
        last_modified,
        policy_id
    ))
    conn.commit()
    conn.close()

    # Guardar rollback como nueva versión en history
    save_policy_version(
        policy_id,
        description,
        language,
        rule,
        owner,
        version,
        last_modified
    )

    # Actualizar OPA si es Rego
    if language == "rego":
        try:
            opa_client.update_policy_from_string(rule, policy_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return AuthPolicyResponse.model_validate({
        "policy_id": policy_id,
        "auth-policy:policy": {
            "description": description,
            "language": language,
            "rule": rule,
            "owner": owner
        },
        "version": version,
        "last_modified": last_modified
    })


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
