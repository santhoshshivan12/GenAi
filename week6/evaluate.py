from __future__ import annotations
import argparse, json, os, re, time, urllib.error, urllib.request
from pathlib import Path
from rag.env import load_env_file

load_env_file()
ROOT=Path(__file__).resolve().parent
TRACE=ROOT.parent/'data'/'traces.jsonl'

def load_traces():
    out=[]
    for line in TRACE.read_text(encoding='utf-8').splitlines():
        try: out.append(json.loads(line))
        except json.JSONDecodeError: pass
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--judge-version", choices=("1","2"), default="1")
    args=parser.parse_args()
    cases_payload=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))
    cases=cases_payload.get('cases',[])
    if len(cases)<25: raise SystemExit('week6/cases.json must contain at least 25 cases')
    if len({case.get('trace_id') for case in cases}) != len(cases):
        raise SystemExit('week6/cases.json contains duplicate trace IDs')
    labels_path=ROOT/'labels_25.json'; labels=json.loads(labels_path.read_text(encoding='utf-8'))
    if len(labels.get('labels',[])) != len(cases) or len(cases) < 25 or any(x.get('human_label') not in ('PASS','FAIL') for x in labels['labels']):
        raise SystemExit('Fill 25 blind human_label values in week6/labels_25.json before running the judge.')
    prompt=(ROOT/f'judge_v{args.judge_version}.txt').read_text(encoding='utf-8')
    results=[]
    for case in cases:
        evidence=[]
        for chunk in case.get('retrieval',{}).get('chunks',[])[:3]:
            evidence.append({
                'chunk_id': chunk.get('chunk_id'),
                'source_file': chunk.get('source_file'),
                'sdk_version': chunk.get('sdk_version'),
                'page_number': chunk.get('page_number'),
                'score': chunk.get('score'),
                'text': str(chunk.get('text',''))[:2500],
            })
        user=json.dumps({'question':case.get('question'),'answer':case.get('answer'),'documentation':evidence},ensure_ascii=False)
        key=os.getenv('OPENROUTER_API_KEY','').strip()
        if not key: raise SystemExit('OPENROUTER_API_KEY is required in .env')
        model=os.getenv('OPENROUTER_MODEL','openai/gpt-4o-mini').strip()
        openrouter_payload={
            'model': model,
            'temperature': 0,
            'max_tokens': int(os.getenv('OPENROUTER_JUDGE_MAX_TOKENS','300')),
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': user},
            ],
        }
        req=urllib.request.Request(
            'https://openrouter.ai/api/v1/chat/completions',
            data=json.dumps(openrouter_payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'http://127.0.0.1:8000',
                'X-Title': 'Week 6 G-Eval Judge',
            },
            method='POST',
        )
        last_error=None
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req,timeout=180) as resp:
                    raw=json.loads(resp.read())
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error=exc
                if attempt == 5:
                    raise RuntimeError(f"OpenRouter failed after 6 attempts for trace {case['trace_id']}: {exc}") from exc
                wait_seconds=min(60, 2 ** (attempt + 1))
                print(f"Network retry {attempt + 1}/5 for {case['trace_id']} in {wait_seconds}s: {exc}")
                time.sleep(wait_seconds)
        content=raw['choices'][0]['message']['content']
        match=re.search(r'\{.*\}', content, re.S)
        if match is None:
            raise ValueError(f"OpenRouter returned no JSON object for trace {case['trace_id']}: {content[:200]}")
        judged=json.loads(match.group(0))
        geval_score=max(0,min(4,float(judged.get('score',0))))
        judge_label='PASS' if geval_score >= 3 else 'FAIL'
        results.append({'trace_id':case['trace_id'],'human_label':labels['labels'][len(results)]['human_label'],'judge_label':judge_label,'geval_score':geval_score,'normalized_score':geval_score/4,'reason':judged.get('reason')})
        time.sleep(1)
    agreement=sum(x['human_label']==x['judge_label'] for x in results)/len(results)*100
    agreement_key='agreement_before' if args.judge_version=='1' else 'agreement_after'
    output=ROOT/f'eval_results_v{args.judge_version}.json'
    output.write_text(json.dumps({agreement_key:agreement,'judge_version':args.judge_version,'results':results},indent=2),encoding='utf-8')
    print(f'{agreement_key}: {agreement:.2f}%')
    print('Assertions: 2; LLM-judged criteria: 1')
    print(f'Results saved to {output}')
if __name__=='__main__': main()
