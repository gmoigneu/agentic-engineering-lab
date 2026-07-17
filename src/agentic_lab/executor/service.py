from fastapi import FastAPI

app = FastAPI(title="Agentic Engineering Lab executor launcher")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
