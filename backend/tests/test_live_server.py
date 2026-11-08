"""
End-to-end integration smoke test running a live uvicorn server in a subprocess
and sending real HTTP requests to all 8 endpoints.
"""

import io
import subprocess
import sys
import time
import httpx


def test_live_server_endpoints():
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8009",
        "--log-level",
        "warning",
    ]

    proc = subprocess.Popen(cmd)
    base_url = "http://127.0.0.1:8009"

    try:
        # Wait for server to boot
        booted = False
        for _ in range(30):
            try:
                r = httpx.get(f"{base_url}/api/health", timeout=1.0)
                if r.status_code == 200:
                    booted = True
                    break
            except Exception:
                time.sleep(0.3)

        assert booted, "Live uvicorn server failed to boot on port 8009"

        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            # 1. GET /api/health
            r_health = client.get("/api/health")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "ok"

            # 2. GET /api/system/info
            r_sys = client.get("/api/system/info")
            assert r_sys.status_code == 200
            assert "vault_tools" in r_sys.json()

            # 3. GET /api/documents
            r_docs = client.get("/api/documents")
            assert r_docs.status_code == 200
            assert "total" in r_docs.json()

            # 4. POST /api/documents/upload
            file_data = b"Live server integration test data."
            files = {"file": ("live_test.txt", io.BytesIO(file_data), "text/plain")}
            r_upload = client.post("/api/documents/upload", files=files)
            assert r_upload.status_code == 201
            assert r_upload.json()["success"] is True

            # 5. GET /api/experiments
            r_exp = client.get("/api/experiments")
            assert r_exp.status_code == 200
            assert "items" in r_exp.json()

            # 6. POST /api/experiments
            r_create_exp = client.post(
                "/api/experiments",
                json={
                    "name": "Live Server Experiment",
                    "tool_type": "curatorkit",
                    "parameters": {"test": True},
                },
            )
            assert r_create_exp.status_code == 201

            # 7. POST /api/ground-truth/validate
            r_gt = client.post(
                "/api/ground-truth/validate",
                json={
                    "dataset_name": "live_bench",
                    "items": [
                        {
                            "prompt": "What is VAULT?",
                            "reference_answer": "An offline private platform.",
                            "context": "VAULT is an offline private platform.",
                        }
                    ],
                },
            )
            assert r_gt.status_code == 200
            assert r_gt.json()["is_valid"] is True

            # 8. POST /api/llm/generate
            r_llm = client.post(
                "/api/llm/generate",
                json={"prompt": "CuratorKIT test prompt", "model": "llama3:8b"},
            )
            assert r_llm.status_code == 200
            assert "content" in r_llm.json()

            # 9. POST /api/jobs & GET /api/jobs
            r_job = client.post(
                "/api/jobs",
                json={
                    "tool_name": "auditkit",
                    "parameters": {
                        "samples": [{"prompt": "test query", "reference_answer": "test answer"}],
                        "scorers": ["exact_match"],
                    },
                },
            )
            assert r_job.status_code == 201
            job_id = r_job.json()["job_id"]
            assert job_id.startswith("job_")

            r_jobs_list = client.get("/api/jobs")
            assert r_jobs_list.status_code == 200
            assert r_jobs_list.json()["total"] >= 1

            # 10. GET /api/jobs/{job_id} & /api/jobs/{job_id}/result
            time.sleep(0.5)
            r_job_detail = client.get(f"/api/jobs/{job_id}")
            assert r_job_detail.status_code == 200

            r_job_res = client.get(f"/api/jobs/{job_id}/result")
            assert r_job_res.status_code == 200
            assert "success" in r_job_res.json()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
