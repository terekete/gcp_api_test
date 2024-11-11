from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

# Set up your service account credentials
SERVICE_ACCOUNT_FILE = 'sa.json'
ORGANIZATION_ID = '1080241945545'
TARGET_PROJECT_ID = 'projects/378072761275'

def get_vpc_sc_projects():
    # Authenticate using service account
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE
    )

    # Create a service client for the Access Context Manager API
    access_context_manager_service = build('accesscontextmanager', 'v1', credentials=credentials)
    
    try:
        # List access policies for the specified organization
        request = access_context_manager_service.accessPolicies().servicePerimeters().get(
            name='accessPolicies/598779897758/servicePerimeters/default'
        )
        response = request.execute()
        print(response)
        if 'status' in response and 'resources' in response['status']:
            resources = response['status']['resources']
            print(f"    Resources in Perimeter: {resources}")

            if TARGET_PROJECT_ID in resources:
                print(f"    Project {TARGET_PROJECT_ID} exists in the perimeter {response['name']}")
            else:
                print(f"    Project {TARGET_PROJECT_ID} does NOT exist in the perimeter {response['name']}")


    except HttpError as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    get_vpc_sc_projects()