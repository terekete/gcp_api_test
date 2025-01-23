from fastapi import FastAPI, HTTPException
from typing import List, Dict, Optional, Any, Tuple, Callable
import asyncio
import random
import uuid
import logging
from datetime import datetime
from dataclasses import dataclass
from collections import OrderedDict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class TaskConfig:
    name: str
    func: Callable
    retry_interval: float = 1.0
    max_attempts: int = 5
    task_type: str = "default"
    required_params: List[str] = None
    on_complete: Optional[Callable[[Dict], None]] = None

    def __post_init__(self):
        if self.required_params is None:
            self.required_params = []

class ChainData:
    def __init__(self):
        self.data = {}

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str) -> Optional[Any]:
        return self.data.get(key)

class ChainTracker:
    def __init__(self):
        self._chains = {}
        self._lock = asyncio.Lock()

    async def start_chain(self, chain_id: str, task_sequence: List[str]) -> None:
        async with self._lock:
            self._chains[chain_id] = {
                'status': 'running',
                'start_time': datetime.now().isoformat(),
                'current_task': None,
                'task_sequence': task_sequence,
                'completed_tasks': OrderedDict(),
                'total_tasks': len(task_sequence),
                'last_updated': datetime.now().isoformat(),
                'attempts': {}
            }

    async def update_attempts(self, chain_id: str, task_name: str) -> None:
        async with self._lock:
            if chain_id in self._chains:
                if task_name not in self._chains[chain_id]['attempts']:
                    self._chains[chain_id]['attempts'][task_name] = 0
                self._chains[chain_id]['attempts'][task_name] += 1

    async def complete_task(self, chain_id: str, task_name: str, result: Dict) -> None:
        async with self._lock:
            if chain_id in self._chains:
                self._chains[chain_id]['completed_tasks'][task_name] = {
                    'completion_time': datetime.now().isoformat(),
                    'result': result,
                    'attempts': self._chains[chain_id]['attempts'].get(task_name, 0)
                }
                if len(self._chains[chain_id]['completed_tasks']) == self._chains[chain_id]['total_tasks']:
                    self._chains[chain_id]['status'] = 'completed'
                    self._chains[chain_id]['end_time'] = datetime.now().isoformat()

    async def fail_chain(self, chain_id: str, error: str, failed_task: str) -> None:
        async with self._lock:
            if chain_id in self._chains:
                self._chains[chain_id].update({
                    'status': 'failed',
                    'error': error,
                    'failed_task': failed_task,
                    'end_time': datetime.now().isoformat(),
                    'attempts_at_failure': self._chains[chain_id]['attempts'].get(failed_task, 0)
                })

    async def get_chain_status(self, chain_id: str) -> Optional[Dict]:
        async with self._lock:
            return self._chains.get(chain_id)

    async def get_active_chains(self) -> Dict[str, Dict]:
        async with self._lock:
            return {
                chain_id: chain 
                for chain_id, chain in self._chains.items() 
                if chain['status'] == 'running'
            }

class ChainedTasks:
    def __init__(self, tasks: List[TaskConfig]):
        self.tasks = tasks
        self.chain_tracker = chain_tracker
        self.chain_data = ChainData()

    async def execute_task(self, task: TaskConfig, project_id: str, chain_id: str) -> Dict:
        attempts = 0
        while attempts < task.max_attempts:
            attempts += 1
            await self.chain_tracker.update_attempts(chain_id, task.name)
            
            try:
                task_params = {'project_id': project_id}
                for param in task.required_params:
                    value = self.chain_data.get(param)
                    if value is None:
                        raise Exception(f"Required parameter {param} not found in chain data")
                    task_params[param] = value

                result = task.func(**task_params)
                
                if isinstance(result, tuple):
                    status, data = result
                    if status == 'Y':
                        if data is not None:
                            self.chain_data.set(task.name, data)
                        result_dict = {
                            'status': 'Y',
                            'task': task.name,
                            'attempts': attempts,
                            'data': data,
                            'project_id': project_id,
                            **task_params  # Include all task parameters
                        }
                        await self.chain_tracker.complete_task(chain_id, task.name, {'status': 'Y', 'data': data})
                        if task.on_complete:
                            task.on_complete(result_dict)
                        return result_dict
                else:
                    if result == 'Y':
                        result_dict = {
                            'status': 'Y',
                            'task': task.name,
                            'attempts': attempts,
                            'project_id': project_id,
                            **task_params  # Include all task parameters
                        }
                        await self.chain_tracker.complete_task(chain_id, task.name, {'status': 'Y'})
                        if task.on_complete:
                            task.on_complete(result_dict)
                        return result_dict
                
                logging.info(f"Task {task.name} attempt {attempts}: got N, retrying after {task.retry_interval}s")
                await asyncio.sleep(task.retry_interval)
                
            except Exception as e:
                logging.error(f"Task {task.name} attempt {attempts} failed with error: {str(e)}")
                if attempts < task.max_attempts:
                    await asyncio.sleep(task.retry_interval)
                continue
        
        error_msg = f"Task {task.name} failed after {attempts} attempts"
        await self.chain_tracker.fail_chain(chain_id, error_msg, task.name)
        return {'status': 'N', 'task': task.name, 'attempts': attempts}

    async def execute_chain(self, chain_id: str, project_id: str) -> List[Dict]:
        start_time = datetime.now()
        results = []
        try:
            for task in self.tasks:
                result = await self.execute_task(task, project_id, chain_id)
                if result['status'] == 'N':
                    logging.info(f"Chain {chain_id} stopped at task {task.name} after {result['attempts']} attempts")
                    return results
                results.append(result)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logging.info(f"Chain completed - UUID: {chain_id}, Project: {project_id}, Duration: {duration:.2f}s")
            return results
            
        except Exception as e:
            logging.error(f"Chain {chain_id} failed with error: {str(e)}")
            raise

def project_lookup(project_id: str) -> Tuple[str, Optional[str]]:
    if random.choice(['Y', 'N']) == 'Y':
        project_number = f"project_{random.randint(100000, 999999)}"
        return 'Y', project_number
    return 'N', None

def vpc_sc_lookup(project_id: str, project_lookup: str) -> str:
    return random.choice(['Y', 'N'])

def shared_vpc_lookup(project_id: str) -> str:
    return random.choice(['Y', 'N'])

def on_project_lookup_complete(result: Dict):
    if result['status'] == 'Y':
        logging.info(f"✓ Project Lookup | Project ID: {result.get('project_id')} | Number: {result.get('data')} | Attempts: {result['attempts']}")
    else:
        logging.info(f"✗ Project Lookup Failed | Project ID: {result.get('project_id')} | Attempts: {result['attempts']}")

def on_vpc_sc_complete(result: Dict):
    logging.info(f"{'✓' if result['status'] == 'Y' else '✗'} VPC SC | Project ID: {result.get('project_id')} | Project Number: {result.get('project_lookup')} | Status: {result['status']} | Attempts: {result['attempts']}")

def on_shared_vpc_complete(result: Dict):
    logging.info(f"{'✓' if result['status'] == 'Y' else '✗'} Shared VPC | Project ID: {result.get('project_id')} | Status: {result['status']} | Attempts: {result['attempts']}")

app = FastAPI()
chain_tracker = ChainTracker()

TASKS = [
    TaskConfig(
        name='project_lookup',
        func=project_lookup,
        retry_interval=60.0,
        max_attempts=3,
        on_complete=on_project_lookup_complete
    ),
    TaskConfig(
        name='vpc_sc_lookup',
        func=vpc_sc_lookup,
        retry_interval=60.0,
        max_attempts=4,
        required_params=['project_lookup'],
        on_complete=on_vpc_sc_complete
    ),
    TaskConfig(
        name='shared_vpc_lookup',
        func=shared_vpc_lookup,
        retry_interval=60.0,
        max_attempts=5,
        on_complete=on_shared_vpc_complete
    )
]

@app.post("/start-chain/{project_id}")
async def start_chain(project_id: str):
    chain_id = str(uuid.uuid4())
    chain_executor = ChainedTasks(TASKS)
    await chain_executor.chain_tracker.start_chain(chain_id, [t.name for t in TASKS])
    
    asyncio.create_task(chain_executor.execute_chain(chain_id, project_id))
    
    return {
        "chain_id": chain_id,
        "status": "started",
        "project_id": project_id
    }

@app.get("/chain-status/{chain_id}")
async def get_chain_status(chain_id: str):
    status = await chain_tracker.get_chain_status(chain_id)
    if not status:
        raise HTTPException(status_code=404, detail="Chain not found")
    return status

@app.get("/active-chains")
async def get_active_chains():
    return await chain_tracker.get_active_chains()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)