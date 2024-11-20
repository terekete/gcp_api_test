from fastapi import FastAPI, HTTPException
from google.cloud import compute_v1
import os
import asyncio

app = FastAPI()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "sa.json"

async def check_service_project(host_project_id: str, service_project_id: str) -> bool:
    client = compute_v1.ProjectsClient()

    try:
        request = compute_v1.GetXpnResourcesProjectsRequest(project=host_project_id)
        response = client.get_xpn_resources(request=request)

        for resource in response:
            if resource.id == service_project_id:
                return True
        return False

    except Exception as e:
        if 'is not a shared VPC host project' in str(e):
            raise HTTPException(status_code=400, detail=f"{host_project_id} is not a Shared VPC host project.")
        raise Exception(f"Error checking service project {service_project_id} under host project {host_project_id}: {e}")


@app.get("/check-service-project/{host_project_id}/{service_project_id}")
async def check_service_project_endpoint(host_project_id: str, service_project_id: str):
    try:
        is_service_project = await check_service_project(host_project_id, service_project_id)
        return {"host_project_id": host_project_id, "service_project_id": service_project_id, "is_service_project": is_service_project}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
