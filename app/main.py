__name__ = "Policy Administration Point"
__version__ = "3.0.0"

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import uuid
import os
import subprocess

# ----------------------
# CONFIG
# ----------------------
GIT_REPO_PATH = os.getenv("GIT_REPO_PATH", "./policies-repo")

DOMAINS_DIR = "domains"

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
class PolicyData(BaseModel):

    domain: str
    description: str
    language: Literal["rego", "cedar", "alfa"]
    pac: str
    owner: str


class AuthPolicyRequest(BaseModel):

    auth_policy: PolicyData = Field(..., alias="auth-policy:policy")

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


def get_domain_path(domain: str):

    return os.path.join(
        GIT_REPO_PATH,
        DOMAINS_DIR,
        domain,
        "policies"
    )


def get_policy_file(domain: str, policy_id: str):

    domain_path = get_domain_path(domain)

    if not os.path.exists(domain_path):
        return None

    for file in os.listdir(domain_path):

        if file.startswith(policy_id):
            return os.path.join(domain_path, file)

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

    domain_path = get_domain_path(policy.domain)

    os.makedirs(domain_path, exist_ok=True)

    keep_file = os.path.join(domain_path, ".gitkeep")

    if not os.path.exists(keep_file):

        with open(keep_file, "w") as f:
            f.write("")

    file_name = f"{policy_id}.{policy.language}"

    file_path = os.path.join(
        domain_path,
        file_name
    )

    with open(file_path, "w") as f:

        f.write(
f"""# owner: {policy.owner}
# description: {policy.description}

{policy.pac}
"""
        )

    commit_hash = git_commit(
        f"{policy.domain} {policy_id}"
    )

    return commit_hash


def delete_policy_from_git(domain: str, policy_id: str):

    file_path = get_policy_file(domain, policy_id)

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

    domain_path = get_domain_path(domain)

    keep_file = os.path.join(domain_path, ".gitkeep")

    if not os.path.exists(keep_file):

        with open(keep_file, "w") as f:
            f.write("")

    commit_hash = git_commit(
        f"delete {domain} {policy_id}"
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


@app.get("/domains")
def list_domains():

    domains_path = os.path.join(
        GIT_REPO_PATH,
        DOMAINS_DIR
    )

    if not os.path.exists(domains_path):

        return {
            "domains": []
        }

    return {
        "domains": os.listdir(domains_path)
    }


@app.get("/policies")
def list_policies():

    policies = []

    domains_root = os.path.join(
        GIT_REPO_PATH,
        DOMAINS_DIR
    )

    if not os.path.exists(domains_root):

        return {
            "policies": []
        }

    for domain in os.listdir(domains_root):

        domain_path = os.path.join(
            domains_root,
            domain,
            "policies"
        )

        if not os.path.exists(domain_path):
            continue

        for file in os.listdir(domain_path):

            if file == ".gitkeep":
                continue

            policies.append({
                "domain": domain,
                "policy_id": file.split(".")[0],
                "file": file
            })

    return {
        "policies": policies
    }


@app.get("/policies/{domain}/{policy_id}")
def get_policy(domain: str, policy_id: str):

    file_path = get_policy_file(domain, policy_id)

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
        "domain": domain,
        "policy_id": policy_id,
        "file": os.path.basename(file_path),
        "content": content,
        "git_history": history.splitlines()
    }


@app.post("/policies")
def create_policy(request: AuthPolicyRequest):

    policy = request.auth_policy

    policy_id = str(uuid.uuid4())

    commit_hash = save_policy_to_git(
        policy_id,
        policy
    )

    return {
        "policy_id": policy_id,
        "domain": policy.domain,
        "commit_hash": commit_hash
    }


@app.put("/policies/{domain}/{policy_id}")
def update_policy(
    domain: str,
    policy_id: str,
    request: AuthPolicyRequest
):

    policy = request.auth_policy

    if policy.domain != domain:
        raise HTTPException(400, "Domain mismatch")

    existing = get_policy_file(domain, policy_id)

    if not existing:
        raise HTTPException(404, "Policy not found")

    commit_hash = save_policy_to_git(
        policy_id,
        policy
    )

    return {
        "policy_id": policy_id,
        "domain": domain,
        "commit_hash": commit_hash,
        "message": "Policy updated"
    }


@app.delete("/policies/{domain}/{policy_id}")
def delete_policy(domain: str, policy_id: str):

    commit_hash = delete_policy_from_git(
        domain,
        policy_id
    )

    return {
        "policy_id": policy_id,
        "domain": domain,
        "commit_hash": commit_hash,
        "message": "Policy deleted"
    }


# ----------------------
# ROLLBACK
# ----------------------
@app.post("/rollback/{domain}/{policy_id}/{commit_hash}")
def rollback(
    domain: str,
    policy_id: str,
    commit_hash: str
):

    file_path = get_policy_file(domain, policy_id)

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