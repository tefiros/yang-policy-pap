# YANG PAP

Demonstrates a simple **Policy Administration Point (PAP)** that accepts  *policy artifacts* , validates them, applies provenance (COSE signatures), and distributes executable policy logic to consumers.

This project implements example components aligned with the architecture described in the draft  "Model for distributed authorization policy sharing"

* Represent policies as YANG artifacts
* Validate using schema-based checks
* Apply COSE signatures (RFC9052) for provenance

---

## 🧩 Architecture Overview

The PAP:

1. Accepts policies
2. Validates them
3. Stores them with version metadata
4. Signs artifacts (COSE)
5. Distributes them to policy consumers (e.g., OPA)
6. Maintains a complete version history
7. Allows rollback to any historical version

---

## 📦 Repo Structure

<pre class="overflow-visible! px-0!" data-start="1121" data-end="1388"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre!"><span><span>.
├── pap/                </span><span># Go-based PAP (validation + signing)</span><span>
├── app/                </span><span># FastAPI Policy Administration Service</span><span>
├── proto/              </span><span># gRPC definitions</span><span>
├── policies.db         </span><span># SQLite storage (created at runtime)</span><span>
├── Makefile
└── README.md
</span></span></code></div></div></pre>

---

## 🗄 Policy Versioning Model

Each policy is stored in two tables:

### `policies`

Contains only the  **current active version** .

| Field         | Description              |
| ------------- | ------------------------ |
| policy_id     | Unique identifier (UUID) |
| description   | Policy description       |
| language      | rego / cedar / alfa      |
| rule          | Policy logic             |
| owner         | Policy owner             |
| version       | Version timestamp        |
| last_modified | Last update timestamp    |

---

### `policy_versions`

Contains the  **full history of all versions** , including rollbacks.

---

## 🔄 Policy Lifecycle

### Create Policy

<pre class="overflow-visible! px-0!" data-start="2086" data-end="2108"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre!"><span><span>POST /policies
</span></span></code></div></div></pre>

* Generates `policy_id`
* Stores as version `t1`
* Inserts into `policy_versions`
* Distributes to OPA if `rego`

---

### Update Policy

<pre class="overflow-visible! px-0!" data-start="2248" data-end="2281"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre!"><span><span>PUT /policies/{policy_id}
</span></span></code></div></div></pre>

* Generates new version `t2`
* Updates `policies`
* Inserts new row in `policy_versions`

---

### Get History

<pre class="overflow-visible! px-0!" data-start="2395" data-end="2436"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre!"><span><span>GET /policies/{policy_id}/history
</span></span></code></div></div></pre>

Returns full chronological history.

---

### Rollback

<pre class="overflow-visible! px-0!" data-start="2494" data-end="2546"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre!"><span><span>PUT /policies/{policy_id}/rollback/{version}
</span></span></code></div></div></pre>

* Restores selected historical version
* Generates **new version timestamp**
* Inserts new row in `policy_versions`
* Updates OPA if needed

---

## 📌 Getting Started

### Prerequisites

* Python 3.11+
* SQLite
* Open Policy Agent (OPA) running on port 8181

Install OPA:

<pre class="overflow-visible! px-0!" data-start="2866" data-end="2956"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-bash"><span><span>brew install opa
</span><span># or</span><span>
docker run -p 8181:8181 openpolicyagent/opa run --server
</span></span></code></div></div></pre>

---

## 🚀 Run the PAP Demo

```
poetry install
```

```
poetry shell
```

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 🧪 Example Policy (Rego)

<pre class="overflow-visible! px-0!" data-start="3244" data-end="3386"><div class="contain-inline-size rounded-2xl corner-superellipse/1.1 relative bg-token-sidebar-surface-primary"><div class="sticky top-[calc(var(--sticky-padding-top)+9*var(--spacing))]"><div class="absolute end-0 bottom-0 flex h-9 items-center pe-2"><div class="bg-token-bg-elevated-secondary text-token-text-secondary flex items-center gap-4 rounded-sm px-2 font-sans text-xs"></div></div></div><div class="overflow-y-auto p-4" dir="ltr"><code class="whitespace-pre! language-rego"><span>package policies

default allow = false

allow {
    input.user.role == "reader"
}

allow_write {
    input.user.role == "admin"
}
</span></code></div></div></pre>

---

## 🔐 Provenance

Artifacts may be signed using COSE to provide:

* Integrity
* Authenticity
* Traceability

---

## Docker Setup (Optional)

You can also run the application in a Docker container:

Build the Docker image:

```
 docker build -t pap .
```

Run the container:

```
 docker run -d -p 8000:8000 pap
```

## 🛠 Future Improvements

* Proper


## Documentation

You can consult the automatically generated API documentation at:

* Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
