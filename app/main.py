__name__ = "Policy Administration Point"
__version__ = "3.0.0"

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import uuid
import os
import hashlib
import re
import subprocess
from urllib.parse import urlparse

# ----------------------
# CONFIG
# ----------------------
GIT_REPO_PATH = os.getenv("GIT_REPO_PATH", "./policies-repo")

AREAS_DIR = "areas"

app = FastAPI(
    title=__name__,
    version=__version__
)

# ----------------------
# INIT
# ----------------------
def init_repo():

    os.makedirs(GIT_REPO_PATH, exist_ok=True)

    git_dir = os.path.join(GIT_REPO_PATH, ".git")

    if not os.path.exists(git_dir):

        subprocess.run(
            ["git", "init"],
            cwd=GIT_REPO_PATH,
            check=True
        )

        subprocess.run(
            ["git", "config", "user.email", "pap@local"],
            cwd=GIT_REPO_PATH,
            check=True
        )

        subprocess.run(
            ["git", "config", "user.name", "Policy Administration Point"],
            cwd=GIT_REPO_PATH,
            check=True
        )

init_repo()

# ----------------------
# MODELS
# ----------------------
SUPPORTED_LANGUAGES = {
    "authz-policy:rego": "rego",
    "authz-policy:cedar": "cedar",
    "authz-policy:alfa": "alfa"
}

def validate_uri(value: str, field_name: str) -> str:
 
    parsed = urlparse(value)
 
    if not parsed.scheme or not parsed.netloc and not parsed.path:
        raise ValueError(
            f"'{field_name}' must be a valid URI (e.g. urn:example:foo or https://example.com/bar)"
        )
 
    return value
 

class PolicyData(BaseModel):

    area: str
    description: str
    language: str
    pac: str
    owner: str
    author: str
    origin: Optional[str] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value):

        if value not in SUPPORTED_LANGUAGES:

            raise ValueError(
                f"Unsupported language identity: {value}"
            )

        return value
    
    @field_validator("area")
    @classmethod
    def validate_area(cls, value):
        return validate_uri(value, "area")
 
    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value):
        return validate_uri(value, "owner")
 
    @field_validator("author")
    @classmethod
    def validate_author(cls, value):
        return validate_uri(value, "author")
 
    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value):
 
        if value is None:
            return value
 
        return validate_uri(value, "origin")
 
class AuthzPolicyRequest(BaseModel):

    authz_policy: PolicyData = Field(..., alias="authz-policy:policy")

    class Config:
        allow_population_by_field_name = True


# ----------------------
# HELPERS
# ----------------------
def run_git(cmd):

    result = subprocess.run(
        cmd,
        cwd=GIT_REPO_PATH,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise HTTPException(
            status_code=500,
            detail=f"Git error: {result.stderr.strip()}"
        )

    return result.stdout.strip()


def uri_to_dir_path(uri: str) -> str:
    if uri.startswith("urn:"):
        parts = uri[4:].split(":")  
        return "/".join(parts)

    parsed = urlparse(uri)
    return f"{parsed.netloc}{parsed.path}".strip("/")

def get_area_path(area: str):

    return os.path.join(
        GIT_REPO_PATH,
        AREAS_DIR,
        uri_to_dir_path(area),
        "policies"
    )



def get_policy_file(area: str, policy_id: str):

    area_path = get_area_path(area)

    if not os.path.exists(area_path):
        return None

    for file in os.listdir(area_path):

        if file.startswith(policy_id):
            return os.path.join(area_path, file)

    return None


def git_commit(message: str):

    run_git(["git", "add", "."])

    try:

        run_git([
            "git",
            "commit",
            "-m",
            message
        ])

    except Exception:
        pass

    return run_git([
        "git",
        "rev-parse",
        "HEAD"
    ])


# ----------------------
# POLICY OPS
# ----------------------
def save_policy_to_git(policy_id: str, policy: PolicyData):
 
    area_path = get_area_path(policy.area)
 
    os.makedirs(area_path, exist_ok=True)
 
    keep_file = os.path.join(area_path, ".gitkeep")
 
    if not os.path.exists(keep_file):
 
        with open(keep_file, "w") as f:
            f.write("")
 
    extension = SUPPORTED_LANGUAGES.get(policy.language)
 
    if not extension:
 
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported policy language: {policy.language}"
        )
 
    file_name = f"{policy_id}.{extension}"
 
    file_path = os.path.join(
        area_path,
        file_name
    )
 
    origin_line = f"# origin: {policy.origin}" if policy.origin else "# origin: (none)"
 
    with open(file_path, "w") as f:
 
        f.write(
f"""# owner: {policy.owner}
# author: {policy.author}
{origin_line}
# description: {policy.description}
 
{policy.pac}
"""
        )
 
    commit_hash = git_commit(
        f"{policy.area} {policy_id}"
    )
 
    return commit_hash


def delete_policy_from_git(area: str, policy_id: str):

    file_path = get_policy_file(area, policy_id)

    if not file_path:
        raise HTTPException(404, "Policy not found")

    relative_path = os.path.relpath(
        file_path,
        GIT_REPO_PATH
    )

    run_git([
        "git",
        "rm",
        relative_path
    ])

    area_path = get_area_path(area)

    keep_file = os.path.join(area_path, ".gitkeep")

    if not os.path.exists(keep_file):

        with open(keep_file, "w") as f:
            f.write("")

    commit_hash = git_commit(
        f"delete {area} {policy_id}"
    )

    return commit_hash


# ----------------------
# ROUTES
# ----------------------
@app.get("/")
def root():

    return {
        "service": __name__,
        "version": __version__
    }


@app.get("/areas")
def list_areas():

    areas_path = os.path.join(
        GIT_REPO_PATH,
        AREAS_DIR
    )

    if not os.path.exists(areas_path):

        return {
            "areas": []
        }

    return {
        "areas": os.listdir(areas_path)
    }


@app.get("/policies")
def list_policies():

    policies = []

    areas_root = os.path.join(
        GIT_REPO_PATH,
        AREAS_DIR
    )

    if not os.path.exists(areas_root):

        return {
            "policies": []
        }

    for area in os.listdir(areas_root):

        area_path = os.path.join(
            areas_root,
            area,
            "policies"
        )

        if not os.path.exists(area_path):
            continue

        for file in os.listdir(area_path):

            if file == ".gitkeep":
                continue

            policies.append({
                "area": area,
                "policy_id": file.split(".")[0],
                "file": file
            })

    return {
        "policies": policies
    }


@app.get("/policies/{area}/{policy_id}")
def get_policy(area: str, policy_id: str):

    file_path = get_policy_file(area, policy_id)

    if not file_path:
        raise HTTPException(404, "Policy not found")

    with open(file_path, "r") as f:
        content = f.read()

    relative_path = os.path.relpath(
        file_path,
        GIT_REPO_PATH
    )

    history = run_git([
        "git",
        "log",
        "--oneline",
        "--",
        relative_path
    ])

    return {
        "area": area,
        "policy_id": policy_id,
        "file": os.path.basename(file_path),
        "content": content,
        "git_history": history.splitlines()
    }


@app.post("/policies")
def create_policy(request: AuthzPolicyRequest):

    policy = request.authz_policy

    policy_id = str(uuid.uuid4())

    commit_hash = save_policy_to_git(
        policy_id,
        policy
    )

    return {
        "policy_id": policy_id,
        "area": policy.area,
        "commit_hash": commit_hash
    }


@app.put("/policies/{area}/{policy_id}")
def update_policy(
    area: str,
    policy_id: str,
    request: AuthzPolicyRequest
):

    policy = request.authz_policy

    if policy.area != area:
        raise HTTPException(400, "area mismatch")

    existing = get_policy_file(area, policy_id)

    if not existing:
        raise HTTPException(404, "Policy not found")

    commit_hash = save_policy_to_git(
        policy_id,
        policy
    )

    return {
        "policy_id": policy_id,
        "area": area,
        "commit_hash": commit_hash,
        "message": "Policy updated"
    }


@app.delete("/policies/{area}/{policy_id}")
def delete_policy(area: str, policy_id: str):

    commit_hash = delete_policy_from_git(
        area,
        policy_id
    )

    return {
        "policy_id": policy_id,
        "area": area,
        "commit_hash": commit_hash,
        "message": "Policy deleted"
    }


# ----------------------
# ROLLBACK
# ----------------------
@app.post("/rollback/{area}/{policy_id}/{commit_hash}")
def rollback(
    area: str,
    policy_id: str,
    commit_hash: str
):

    file_path = get_policy_file(area, policy_id)

    if not file_path:
        raise HTTPException(404, "Policy not found")

    relative_path = os.path.relpath(
        file_path,
        GIT_REPO_PATH
    )

    run_git([
        "git",
        "checkout",
        commit_hash,
        "--",
        relative_path
    ])

    rollback_commit = git_commit(
        f"rollback {policy_id} to {commit_hash}"
    )

    return {
        "policy_id": policy_id,
        "rollback_to": commit_hash,
        "new_commit_hash": rollback_commit
    }


# ----------------------
# MAIN
# ----------------------
if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )