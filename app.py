from fastapi import FastAPI, HTTPException, Path, Query
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import re
import httpx

app = FastAPI()

PROJECT_ID_REGEX = r'^[a-z][a-z0-9\-]{4,28}[a-z0-9]$'
PORT = 8082

def get_resource_management_credentials():
    credentials = service_account.Credentials.from_service_account_file(
        os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    )

    service = build('cloudresourcemanager', 'v1', credentials=credentials)
    return service


def get_access_context_credentials():
    credentials = service_account.Credentials.from_service_account_file(
        os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    )

    service = build('accesscontextmanager', 'v1', credentials=credentials)
    return service


@app.get("/check-project/{project_id}")
async def check_project_exists(project_id: str = Path(..., min_length=6, max_length=30, pattern=PROJECT_ID_REGEX)):

    client = get_resource_management_credentials()

    try:
        request = client.projects().get(projectId=project_id)
        response = request.execute()

        return {"project_id": project_id, "status": "exists", "project_info": response}
    except HttpError as e:
        if e.resp.status == 404:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
        elif e.resp.status == 403:
            raise HTTPException(status_code=403, detail=f"Access denied for project '{project_id}'.")
        else:
            raise HTTPException(status_code=500, detail="An error occurred while checking the project.")


@app.get("/internal-call/{project_id}")
async def internal_call(project_id: str = Path(..., min_length=6, max_length=30, pattern=PROJECT_ID_REGEX)):
    async with httpx.AsyncClient as client:
        url = f"http://localhost:{PORT}/check-project/{project_id}"
        response = await client.get(url)

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=response.status_code, detail=response.json())


@app.get("/check-perimeter/{project_id}")
async def check_perimeter(
    project_id: str = Path(..., min_length=6, max_length=30),
    perimeter_name: str = Query(..., min_length=1)
):
    access_context_client = get_access_context_credentials()

    async with httpx.AsyncClient() as httpx_client:
        url = f"http://localhost:{PORT}/check-project/{project_id}"
        response = await httpx_client.get(url)
        
        project_info = response.json()
        if project_info.get('status') != 'exists':
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' does not exist.")

        try: 
            perimeter_request = access_context_client.services().list()
            perimeter_response = perimeter_request.execute()

            for perimeter in perimeter_response.get('accessLevels', []):
                if perimeter.get('name') == perimeter_name:
                    if project_id in perimeter.get('projects', []):
                        return {"project_id": project_id, "in_perimeter": True}

            return {"project_id": project_id, "in_perimeter": False, "output": perimeter_response}

        except HttpError as e:
            raise HTTPException(status_code=500, detail="An error occurred while checking perimeters.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="debug")
