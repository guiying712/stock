"""Refresh public research evidence; no credentials, installation, or repository code execution."""
import concurrent.futures, datetime, hashlib, json, pathlib, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
INPUT = json.loads((ROOT / 'sources/connector-metadata.json').read_text())

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'InvestmentAgentResearch', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read()

def collect(entry):
    repo = entry['repo']
    base = entry['result']['structuredContent']
    folder = ROOT / 'sources' / repo.replace('/', '__')
    folder.mkdir(parents=True, exist_ok=True)
    record = {'repo': repo, 'retrieved_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'errors': [], 'files': []}
    def save(name, url):
        data = fetch(url)
        (folder / name).write_bytes(data)
        record['files'].append({'path': name, 'source_url': url, 'sha256': hashlib.sha256(data).hexdigest()})
        return data
    try:
        metadata = json.loads(save('repository.json', 'https://api.github.com/repos/' + repo))
        record['metadata'] = metadata
    except Exception as exc:
        record['metadata'] = base
        record['errors'].append('metadata: ' + str(exc))
    ref = base['default_branch']
    try:
        commit = json.loads(save('commit.json', 'https://api.github.com/repos/' + repo + '/commits/' + urllib.parse.quote(ref, safe='')))
        ref = commit['sha']
        record['commit_sha'] = ref
    except Exception as exc:
        record['errors'].append('commit: ' + str(exc))
    raw = 'https://raw.githubusercontent.com/' + repo + '/' + ref + '/'
    for kind, candidates in [('README', ['README.md','README.MD','README.rst','README']), ('LICENSE', ['LICENSE','LICENSE.md','LICENSE.txt','LICENCE','COPYING'])]:
        found = False
        for name in candidates:
            try:
                save(kind + '.txt', raw + name)
                record[kind.lower() + '_path'] = name
                found = True
                break
            except Exception as exc:
                last_error = str(exc)
        if not found:
            record['errors'].append(kind + ': not retrieved; ' + last_error)
    (folder / 'provenance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(repo, 'sha=' + record.get('commit_sha','UNPINNED')[:10], 'files=' + str(len(record['files'])), 'errors=' + str(record['errors']), flush=True)
    return record

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(collect, INPUT))
    (ROOT / 'sources/manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
