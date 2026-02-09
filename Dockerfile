FROM python:3.11-slim

LABEL app="YANG Policy PAP Demo"
LABEL version="0.1.0"
LABEL maintainer="Lucía Cabanillas Rodríguez"

RUN pip install fastapi uvicorn pyang

WORKDIR /app
COPY ./yang_policy_pap /app

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]

