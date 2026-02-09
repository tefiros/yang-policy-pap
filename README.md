
# YANG PAP

Demonstrates a simple **Policy Administration Point (PAP)** that accepts *YANG-encoded policy artifacts*, validates them,
applies provenance (COSE signatures), and distributes executable policy logic to consumers.

This project implements example components aligned with the architecture described in the draft “YANG-Based Framework for Distributed Authorization Policy Representation and Distribution”:

- Represent policies as YANG artifacts
- Validate using schema-based checks
- Apply COSE signatures {{RFC9052}} for provenance
- Expose a gRPC interface for distribution

## 📦 Repo Structure

## 📌 Getting Started

### Prerequisites

### Run the PAP demo

```bash
# generate proto stubs
make generate

# run validator and signer
go run ./pap
```
