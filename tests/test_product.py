from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.control import Control, now, uid
from app.ingestion import Ingestor, parse_file
from app.knowledge import Knowledge
from app.main import create_app
from app.connectors import oauth_start, oauth_callback
from app.workspace_agent import WorkspaceAgent


@pytest.fixture
def product(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/auth/setup', json={'name':'Test Owner','email':'owner@example.test','password':'Test password 123'})
        assert response.status_code == 200, response.text
        ctl = client.app.state.control
        ws = client.get('/api/workspaces').json()[0]
        yield client, ctl, ws
        for row in ctl.rows('SELECT graph_name FROM workspaces'):
            try:
                Knowledge(row['graph_name']).graph.delete()
            except Exception:
                pass  # graph never created (e.g. workspace with no data)


def wait_job(client, workspace_id, job_id):
    for _ in range(100):
        jobs = client.get(f'/api/w/{workspace_id}/jobs').json()
        job = next(j for j in jobs if j['id'] == job_id)
        if job['status'] in {'completed','failed'}:
            assert job['status'] == 'completed', job
            return job
        time.sleep(.03)
    raise AssertionError('Ingestion did not complete')


def test_real_upload_versions_queries_and_agent(product):
    client, ctl, ws = product
    base = f"/api/w/{ws['id']}"
    data = {'nodes':[{'id':'p1','name':'Orbit','type':'Project'},{'id':'u1','name':'Jules','type':'Person'}],
            'edges':[{'source':'u1','target':'p1','type':'OWNS'}]}
    upload = client.post(base+'/sources/upload', files={'file':('team.json', json.dumps(data).encode(),'application/json')})
    assert upload.status_code == 200, upload.text
    wait_job(client, ws['id'], upload.json()['job_id'])
    sources = client.get(base+'/sources').json()
    assert len(sources) == 1
    graph = client.get(base+'/graph').json()
    assert any(n.get('name') == 'Jules' for n in graph['nodes'])
    assert any(e.get('predicate') == 'OWNS' for e in graph['edges'])
    response = client.post(base+'/graph/query', json={'query':"MATCH (a:Entity)-[r:RELATED_TO]->(b) RETURN a,r,b"})
    assert response.status_code == 200, response.text
    assert response.json()['rows'][0]['r']['predicate'] == 'OWNS'
    blocked = client.post(base+'/graph/query', json={'query':'CREATE (:Malicious {name:"write"})'})
    assert blocked.status_code == 400
    agent_id = client.get(base+'/agents').json()[0]['id']
    response = client.post(base+f'/agents/{agent_id}/run', json={'question':'Who owns Orbit?','use_ai':False})
    assert response.status_code == 200, response.text
    assert response.json()['citations']
    assert response.json()['paths']
    assert client.get(base+'/runs').json()
    upload = client.post(base+'/sources/upload', files={'file':('team.json', json.dumps(data).encode(),'application/json')})
    wait_job(client, ws['id'], upload.json()['job_id'])
    assert client.get(base+'/sources').json()[0]['version'] == 1
    data['nodes'][0]['name'] = 'Orbit revised'
    upload = client.post(base+'/sources/upload', files={'file':('team.json', json.dumps(data).encode(),'application/json')})
    wait_job(client, ws['id'], upload.json()['job_id'])
    source = client.get(base+'/sources/'+sources[0]['id']).json()
    assert source['version'] == 2
    assert len(source['history']) == 2
    assert sum(v['active'] for v in source['history']) == 1
    client.post(base+'/sources/'+sources[0]['id']+'/archive')
    assert not Knowledge(ws['graph_name']).search('Orbit')
    upload=client.post(base+'/sources/upload',files={'file':('team.json',json.dumps(data).encode(),'application/json')})
    wait_job(client,ws['id'],upload.json()['job_id'])
    assert Knowledge(ws['graph_name']).search('Orbit')


def test_workspace_isolation_accounts_and_secret_redaction(product):
    client, ctl, ws = product
    response = client.put('/api/admin/settings', json={'github_app_id':'123','github_app_private_key':'never-return-this','openrouter_model':'paid/model'})
    assert response.status_code == 400
    response = client.put('/api/admin/settings', json={'github_app_id':'123','github_app_private_key':'never-return-this'})
    assert response.status_code == 200
    result = client.get('/api/admin/settings').json()
    assert result['github_key_configured'] is True
    assert 'never-return-this' not in json.dumps(result)
    assert 'never-return-this' not in ctl.path.read_bytes().decode(errors='ignore')
    client.post('/api/admin/users', json={'name':'Member','email':'member@example.test','password':'Member password 123'})
    client.post('/api/auth/logout')
    assert client.get('/api/workspaces').status_code == 401
    client.post('/api/auth/login', json={'email':'member@example.test','password':'Member password 123'})
    assert client.get(f"/api/w/{ws['id']}/sources").status_code == 404
    assert client.get('/api/admin/settings').status_code == 403
    assert client.post('/api/workspaces', json={'name':'Other workspace'},headers={'Origin':'https://untrusted.test'}).status_code == 403


def test_langchain_tool_planning_and_review_task(product):
    client, ctl, ws = product
    source = Ingestor(ctl, ws).source('note:orbit','Orbit plan','upload','Jules owns the Orbit project. The launch date needs confirmation.')
    agent = ctl.rows('SELECT * FROM agents WHERE workspace_id=?',(ws['id'],))[0]
    model = FakeListChatModel(responses=[
        '{"tool":"search_sources","arguments":{"query":"Orbit"}}',
        '{"tool":"done"}',
        json.dumps({'answer':'Jules owns Orbit; the launch date needs confirmation.','source_ids':[source['id']], 'review_tasks':[{'title':'Confirm Orbit launch date','reason':'Source says the date needs confirmation','source_id':source['id']}]}),
    ])
    result = WorkspaceAgent(ctl,ws,agent,model=model).run('Who owns Orbit?')
    assert result['model_status']=='connected'
    assert result['proposals']
    proposal=result['proposals'][0]
    review=client.post(f"/api/w/{ws['id']}/reviews/{proposal}",json={'approve':True})
    assert review.status_code==200, review.text
    graph=Knowledge(ws['graph_name'])
    assert graph.read('MATCH (t:Task) RETURN count(t) AS n')[0]['n']==1
    client.post(f"/api/w/{ws['id']}/reviews/{proposal}",json={'approve':True})
    assert graph.read('MATCH (t:Task) RETURN count(t) AS n')[0]['n']==1


def test_oauth_state_and_pkce(product, monkeypatch):
    client,ctl,ws=product
    ctl.secret_set('github_client_id','client')
    ctl.secret_set('github_client_secret','secret')
    url=oauth_start(ctl,ws['owner_id'],'http://127.0.0.1:8765/api/connectors/github/callback')
    assert 'code_challenge_method=S256' in url
    state=ctl.rows('SELECT * FROM oauth_states')[0]
    with pytest.raises(ValueError,match='state'):
        oauth_callback(ctl,'different-user','code',state['state'],'http://localhost/callback')
    import httpx
    class MockClient:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            assert kwargs['json']['code_verifier']==state['verifier']
            return httpx.Response(200,json={'access_token':'test-token'},request=httpx.Request('POST',url))
        def get(self,url,**kwargs):
            assert kwargs['headers']['Authorization']=='Bearer test-token'
            return httpx.Response(200,json={'login':'test-user'},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.connectors.httpx.Client',MockClient)
    result=oauth_callback(ctl,ws['owner_id'],'code',state['state'],'http://localhost/callback')
    assert result['login']=='test-user'
    assert not ctl.rows('SELECT * FROM oauth_states')


def test_parsers():
    text, records = parse_file('people.csv',b'id,name,manager\n1,Jules,2\n2,Sam,\n')
    assert records[0]['manager']=='2'
    with pytest.raises(ValueError):parse_file('binary.exe',b'\0')


def upload_text(client, ws, name, text):
    response = client.post(f"/api/w/{ws['id']}/sources/upload", files={'file': (name, text.encode(), 'text/plain')})
    assert response.status_code == 200, response.text
    wait_job(client, ws['id'], response.json()['job_id'])


def test_source_diff_reconstructs_history_and_rejects_foreign_workspace(product):
    client, ctl, ws = product
    base = f"/api/w/{ws['id']}"
    old_text = '\n'.join(f'line {i} ' + 'x' * 120 for i in range(60))  # several overlapping passages
    new_text = old_text.replace('line 30 ', 'changed 30 ')
    upload_text(client, ws, 'plan.txt', old_text)
    source = client.get(base + '/sources').json()[0]
    before_hash = client.get(base + '/sources/' + source['id']).json()['history'][0]['hash']
    upload_text(client, ws, 'plan.txt', new_text)
    diff = client.get(base + f"/sources/{source['id']}/diff", params={'before_hash': before_hash})
    assert diff.status_code == 200, diff.text
    body = diff.json()
    assert body['added'] == 1 and body['removed'] == 1
    assert any(line.startswith('+changed 30') for line in body['lines'])
    assert Knowledge(ws['graph_name']).version_text(source['id'], before_hash) == old_text
    assert client.get(base + f"/sources/{source['id']}/diff", params={'before_hash': 'nope'}).status_code == 400
    other = client.post('/api/workspaces', json={'name': 'Other'}).json()
    assert client.get(f"/api/w/{other['id']}/sources/{source['id']}/diff", params={'before_hash': before_hash}).status_code == 404


def test_dependency_impact_direction_predicates_depth_and_no_mutation(product):
    client, ctl, ws = product
    base = f"/api/w/{ws['id']}"
    data = {'nodes': [{'id': i, 'name': i.upper(), 'type': 'Service'} for i in ('a', 'b', 'c', 'd', 'e', 'f')],
            'edges': [{'source': 'b', 'target': 'a', 'type': 'DEPENDS_ON'},
                      {'source': 'c', 'target': 'b', 'type': 'DEPENDS_ON'},
                      {'source': 'd', 'target': 'c', 'type': 'DEPENDS_ON'},
                      {'source': 'e', 'target': 'a', 'type': 'FRIENDS_WITH'},
                      {'source': 'a', 'target': 'f', 'type': 'DEPENDS_ON'}]}
    upload = client.post(base + '/sources/upload', files={'file': ('deps.json', json.dumps(data).encode(), 'application/json')})
    wait_job(client, ws['id'], upload.json()['job_id'])
    graph = Knowledge(ws['graph_name'])
    counts = graph.read('MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r')
    ids = {r['name']: r['id'] for r in graph.read('MATCH (n:Service) RETURN n.id AS id,n.name AS name')}
    result = client.get(base + '/graph/impact', params={'entity_id': ids['A']}).json()
    assert result['mutated'] is False
    assert {i['name']: i['hops'] for i in result['items']} == {'B': 1, 'C': 2, 'D': 3}  # direction + predicate filter
    assert graph.read('MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r') == counts
    assert {i['name'] for i in graph.dependency_impact(ids['A'], depth=1)} == {'B'}


def test_task_lifecycle_persists_validates_and_isolates(product):
    client, ctl, ws = product
    base = f"/api/w/{ws['id']}"
    source = Ingestor(ctl, ws).source('note:t', 'Note', 'upload', 'Jules owns Orbit.')
    pid = uid('proposal')
    ctl.execute('INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?)',
                (pid, ws['id'], 'Check Orbit', '', source['id'], 'why', 'pending', now(), None))
    assert client.post(base + f'/reviews/{pid}', json={'approve': True}).status_code == 200
    task = client.get(base + '/tasks').json()[0]
    assert task['status'] == 'open' and task['source_id'] == source['id']
    for status in ('in_progress', 'done'):
        assert client.patch(base + f"/tasks/{task['id']}", json={'status': status}).status_code == 200
        assert client.get(base + '/tasks').json()[0]['status'] == status
    assert client.patch(base + f"/tasks/{task['id']}", json={'status': 'bogus'}).status_code == 422
    assert client.patch(base + '/tasks/task:missing', json={'status': 'done'}).status_code == 404
    other = client.post('/api/workspaces', json={'name': 'Other'}).json()
    assert client.patch(f"/api/w/{other['id']}/tasks/{task['id']}", json={'status': 'open'}).status_code == 404
    assert client.get(base + '/tasks').json()[0]['status'] == 'done'


def test_relationship_changes_and_conflict_candidates(product):
    client, ctl, ws = product
    base = f"/api/w/{ws['id']}"

    def graph_file(name, owner, extra=()):
        nodes = [{'id': 'orbit', 'name': 'Orbit', 'type': 'Project'}] + [{'id': o, 'name': o.title(), 'type': 'Person'} for o in (owner, *extra)]
        edges = [{'source': 'orbit', 'target': o, 'type': 'OWNED_BY'} for o in (owner, *extra)]
        upload = client.post(base + '/sources/upload', files={'file': (name, json.dumps({'nodes': nodes, 'edges': edges}).encode(), 'application/json')})
        wait_job(client, ws['id'], upload.json()['job_id'])

    graph_file('a.json', 'jules')
    assert client.get(base + '/analysis/conflicts').json()['candidates'] == []
    graph_file('b.json', 'sam')  # different source, different owner
    candidates = client.get(base + '/analysis/conflicts').json()['candidates']
    assert len(candidates) == 1 and candidates[0]['predicate'] == 'OWNED_BY'
    assert {c['object'] for c in candidates[0]['claims']} == {'Jules', 'Sam'}
    assert {c['source'] for c in candidates[0]['claims']} == {'a.json', 'b.json'}
    # Re-versioning a.json to agree with b.json removes the conflict and records the change.
    graph_file('a.json', 'sam')
    assert client.get(base + '/analysis/conflicts').json()['candidates'] == []
    source = next(s for s in client.get(base + '/sources').json() if s['title'] == 'a.json')
    changes = client.get(base + f"/sources/{source['id']}/changes").json()
    assert [r['object'] for r in changes['added']] == ['Sam'] and [r['object'] for r in changes['removed']] == ['Jules']
    other = client.post('/api/workspaces', json={'name': 'Other'}).json()
    assert client.get(f"/api/w/{other['id']}/sources/{source['id']}/changes").status_code == 404
