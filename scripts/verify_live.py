"""Exercise a real public repository through the running product. No credentials printed."""
import argparse
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8765')
parser.add_argument('--repository', default='FalkorDB/falkordb')
args = parser.parse_args()

with httpx.Client(base_url=args.url, timeout=60) as client:
    response = client.post('/api/auth/github-cli')
    response.raise_for_status()
    ws = client.get('/api/workspaces').json()[0]
    base = '/api/w/' + ws['id']
    response = client.post(base + '/connectors/github/sync', json={
        'repository': args.repository, 'documents': True, 'issues': True, 'pull_requests': True, 'limit': 2,
    })
    response.raise_for_status()
    job_id = response.json()['job_id']
    print('Queued real repository sync:', args.repository, flush=True)
    for _ in range(90):
        job = next(x for x in client.get(base + '/jobs').json() if x['id'] == job_id)
        if job['status'] in {'completed', 'failed'}:
            print('Sync:', job['status'], job['message'], flush=True)
            if job['status'] == 'failed':
                raise RuntimeError('Live repository sync failed')
            break
        time.sleep(.5)
    else:
        raise RuntimeError('Sync exceeded verification deadline')
    overview = client.get(base + '/overview').json()
    print('Sources:', overview['sources'], 'nodes:', overview['graph']['nodes'], 'edges:', overview['graph']['edges'], flush=True)
    graph = client.get(base + '/graph').json()
    assert graph['edges'] and any('Repository' in n.get('labels', []) for n in graph['nodes'])
    query = client.post(base + '/graph/query', json={'query': 'MATCH (p:Person)<-[r:RELATED_TO]-(i:Entity) RETURN p.name AS person,r.predicate AS relationship,i.name AS item LIMIT 5'})
    query.raise_for_status()
    print('Graph query rows:', len(query.json()['rows']), flush=True)
    agent = client.get(base + '/agents').json()[0]
    result = client.post(base + '/agents/' + agent['id'] + '/run', json={'question': 'What does FalkorDB do?', 'use_ai': False})
    result.raise_for_status()
    assert result.json()['citations']
    print('Agent citations:', len(result.json()['citations']), 'tool calls:', len(result.json()['trace']), flush=True)
