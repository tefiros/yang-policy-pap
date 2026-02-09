__name__ = "YANG Policy Administration Service"
__version__ = "0.1.0"

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from pydantic import BaseModel
import uuid
import os
import subprocess

app = FastAPI(
    title=__name__ + " YANG Policy Administration Service - REST API",
    version=__version__
)

POLICY_STORE = "/tmp/policies"
os.makedirs(POLICY_STORE, exist_ok=True)

class PolicyListResponse(BaseModel):
    policies: list[str]

class PolicyResponse(BaseModel):
    policy_id: str
    yang_content: str

class RegisterPolicyResponse(BaseModel):
    policy_id: str
    status: str

@app.get("/policies", response_model=PolicyListResponse)
def list_policies():
    return {"policies": os.listdir(POLICY_STORE)}

@app.get("/policies/{policy_id}", response_model=PolicyResponse)
def get_policy(policy_id: str):
    path = f"{POLICY_STORE}/{policy_id}.yang"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Policy not found")

    with open(path) as f:
        return {
            "policy_id": policy_id,
            "yang_content": f.read()
        }

@app.post("/policies", response_model=RegisterPolicyResponse)
async def register_policy(file: UploadFile = File(...)):
    if not file.filename.endswith(".yang"):
        raise HTTPException(status_code=400, detail="Only YANG files are accepted")

    policy_id = str(uuid.uuid4())
    path = f"{POLICY_STORE}/{policy_id}.yang"

    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)

    # 1️⃣ Validate YANG (pyang)
    result = subprocess.run(
        ["pyang", path],
        capture_output=True
    )
    if result.returncode != 0:
        os.remove(path)
        raise HTTPException(
            status_code=400,
            detail=result.stderr.decode()
        )

    # 2️⃣ (Optional) Sign with COSE – placeholder
    # sign_policy(path)

    # 3️⃣ Extract PaC (rego) – placeholder
    # extract_pac(path)

    return {
        "policy_id": policy_id,
        "status": "validated-and-registered"
    }

@app.delete("/policies/{policy_id}")
def delete_policy(policy_id: str):
    path = f"{POLICY_STORE}/{policy_id}.yang"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Policy not found")

    os.remove(path)
    return {"message": "Policy retired"}
