"""Paper-facing forced-exposure MemAudit reconstruction on all AgentDojo tasks."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib, importlib.metadata, json, random, statistics, time
from pathlib import Path

import _bootstrap  # noqa: F401
from mcx.agentdojo_adapter import load_official_suites
from mcx.memaudit import HarmfulEvent, MemAuditParameters, memaudit_rank
from mcx.memaudit_agentdojo import materialize_instance
from mcx.memaudit_libero import retrieve_by_similarity
from run_memaudit_libero_events_v1 import nli_stage, release_gpu, semantic_stage

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/memaudit_agentdojo_all97_freeze_v1.json'
OUTPUT=ROOT/'reports/memaudit_agentdojo_all97_v1.json'
CACHE=ROOT/'reports/memaudit_agentdojo_all97_model_cache_v1.json'

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(xs): return statistics.fmean(xs) if xs else None
def percentile(xs,p):
    z=(len(xs)-1)*p; lo=int(z); hi=min(lo+1,len(xs)-1); f=z-lo
    return xs[lo]*(1-f)+xs[hi]*f

def interval(rows, metric, suites, draws, seed):
    grouped=defaultdict(list)
    for row in rows: grouped[row['archive_id']].append(float(row[metric]))
    task={key:mean(vals) for key,vals in grouped.items()}; strata=defaultdict(list)
    for key in sorted(task): strata[suites[key]].append(key)
    rng=random.Random(seed); samples=[]
    for _ in range(draws):
        vals=[]
        for suite in sorted(strata):
            members=strata[suite]; vals.extend(task[rng.choice(members)] for _ in members)
        samples.append(mean(vals))
    samples.sort()
    return {'estimate':mean(task.values()),'lower_95':percentile(samples,.025),'upper_95':percentile(samples,.975),'task_clusters':len(task),'draws':draws}

def paired(left, right, suites, draws, seed):
    def task_values(rows):
        g=defaultdict(list)
        for r in rows: g[r['archive_id']].append(float(r['safe_recovery_success']))
        return {k:mean(v) for k,v in g.items()}
    a,b=task_values(left),task_values(right)
    if set(a)!=set(b): raise RuntimeError('paired populations differ')
    delta={k:a[k]-b[k] for k in a}; strata=defaultdict(list)
    for k in sorted(delta): strata[suites[k]].append(k)
    rng=random.Random(seed); samples=[]
    for _ in range(draws):
        vals=[]
        for suite in sorted(strata):
            members=strata[suite]; vals.extend(delta[rng.choice(members)] for _ in members)
        samples.append(mean(vals))
    samples.sort()
    return {'estimate':mean(delta.values()),'lower_95':percentile(samples,.025),'upper_95':percentile(samples,.975),'wins':sum(v>0 for v in delta.values()),'ties':sum(v==0 for v in delta.values()),'losses':sum(v<0 for v in delta.values()),'task_clusters':len(delta)}

def main():
    started=time.perf_counter(); c=json.loads(CONFIG.read_text())
    for key in ('source_report','source_verification'):
        rel,sha=c[key]
        if digest(ROOT/rel)!=sha: raise RuntimeError(f'frozen input changed: {key}')
    verification=json.loads((ROOT/c['source_verification'][0]).read_text())
    if verification.get('verified') is not True: raise RuntimeError('source not verified')
    if importlib.metadata.version('agentdojo')!=c['agentdojo']['version']: raise RuntimeError('AgentDojo version mismatch')
    source=json.loads((ROOT/c['source_report'][0]).read_text()); suites=load_official_suites(c['agentdojo']['benchmark_version'])
    archives={a['archive_id']:a for a in source['archives']}; instances={i['instance_id']:i for i in source['instances']}
    observable=[]
    for i in source['instances']:
        a=archives[i['archive_id']]; observable.append(materialize_instance(a,i,suites[a['suite']]))
    observable.sort(key=lambda x:x['archive_id']); obs={x['archive_id']:x for x in observable}
    if CACHE.exists():
        cached=json.loads(CACHE.read_text()); semantic,nli=cached['semantic'],cached['nli']
    else:
        semantic=semantic_stage(observable, {'declared_reconstruction_choices':{'semantic_model':c['models']['semantic_model'],'semantic_model_revision':c['models']['semantic_model_revision'],'semantic_neighbors':c['parameters']['semantic_neighbors']}})
        nli=nli_stage(observable,semantic,{'declared_reconstruction_choices':{'nli_model':c['models']['nli_model'],'nli_model_revision':c['models']['nli_model_revision']}}); release_gpu()
        CACHE.write_text(json.dumps({'semantic':semantic,'nli':nli}))
    instance_results={}; score_rows=[]; total_calls=0
    for index,i in enumerate(source['instances'],1):
        o=obs[i['instance_id']]; aid=o['archive_id']; ids=tuple(o['candidate_ids']); affected=set(i['affected_ids']); sem=semantic[aid]
        ordinary=retrieve_by_similarity(ids,sem['retrieval_scores'],o['created_at'],len(ids)); anchors={}; events=[]
        for anchor in sorted(affected):
            retrieved=(anchor,)+tuple(x for x in ordinary if x!=anchor)[:c['parameters']['retrieval_top_k']-1]
            eid=f'{aid}:{anchor}'; anchors[eid]=anchor; events.append(HarmfulEvent(eid,1.0,retrieved))
        def replay_without(event,removed):
            anchor=anchors[event.event_id]
            selected=next(x for x in ordinary if x!=removed) if removed==anchor else anchor
            return float(selected in affected)
        similarities={tuple(k.split('|',1)):v for k,v in sem['similarities'].items()}
        contradictions={tuple(k.split('|',1)):v for k,v in nli[aid].items()}
        ranking,calls=memaudit_rank(ids,events,replay_without,sem['neighbors'],lambda x,y:similarities[x,y],lambda x,y:contradictions[x,y],MemAuditParameters(float(c['parameters']['alpha'])))
        total_calls+=calls; ordered=[x.memory_id for x in ranking]
        instance_results[aid]={'ordered':ordered,'calls':calls}
        for rank,x in enumerate(ranking,1): score_rows.append({'archive_id':i['archive_id'],'instance_id':aid,'suite':i['suite'],'memory_id':x.memory_id,'rank':rank,'affected':x.memory_id in affected,**x.__dict__})
        if index%50==0 or index==len(source['instances']): print(f'instance {index}/{len(source["instances"])}',flush=True)
    rows=[]
    for view in source['views']:
        i=instances[view['instance_id']]; a=archives[i['archive_id']]; affected=set(i['affected_ids']); ordered=instance_results[i['instance_id']]['ordered']
        for budget in c['parameters']['budgets']:
            effective=min(int(budget),int(a['depth']),len(ordered)); quarantined=ordered[:effective]; q=set(quarantined); tp=len(q&affected)
            rows.append({'archive_id':a['archive_id'],'instance_id':i['instance_id'],'suite':a['suite'],'depth':a['depth'],'condition':view['condition'],'mask_replicate':view['mask_replicate'],'method':'memaudit','budget':int(budget),'effective_quarantine_capacity':effective,'diagnostic_counterfactual_calls':instance_results[i['instance_id']]['calls'],'quarantined_ids':quarantined,'quarantine_recall':tp/len(affected),'clean_descendants_removed':len(q-affected),'corrupt_descendants_left':len(affected-q),'safe_recovery_success':float(affected.issubset(q) and a['clean_fallback_safe'])})
    suites_by_archive={k:v['suite'] for k,v in archives.items()}; draws=c['statistics']['bootstrap_draws']; seed=c['statistics']['bootstrap_seed']
    summaries={}; intervals={}; comparisons={}
    methods={'tr_dcta':source['rows']}
    external_path=ROOT/c['external_baselines']
    if external_path.exists():
        external=json.loads(external_path.read_text()); methods['graph_active_search_signaled_root_native']=external['graph_rows']; methods['memorepair_signaled_root']=external['memorepair_rows']
    conditions=tuple(sorted({v['condition'] for v in source['views']}))
    for condition in conditions:
        summaries[condition]={}; intervals[condition]={}; comparisons[condition]={}
        for budget in c['parameters']['budgets']:
            chosen=[r for r in rows if r['condition']==condition and r['budget']==budget]
            summaries[condition][str(budget)]={'runs':len(chosen),'safe_recoveries':sum(r['safe_recovery_success'] for r in chosen),'safe_recovery_rate':mean([r['safe_recovery_success'] for r in chosen]),'mean_quarantine_recall':mean([r['quarantine_recall'] for r in chosen]),'mean_clean_removed':mean([r['clean_descendants_removed'] for r in chosen])}
            intervals[condition][str(budget)]=interval(chosen,'safe_recovery_success',suites_by_archive,draws,seed+budget)
        left=[r for r in rows if r['condition']==condition and r['budget']==4]
        for mi,(name,raw) in enumerate(methods.items()):
            if name=='memorepair_signaled_root': right=[r for r in raw if r['condition']==condition and r['method']==name]
            else: right=[r for r in raw if r['condition']==condition and r.get('budget')==4 and r['method']==name]
            comparisons[condition][name]=paired(left,right,suites_by_archive,draws,seed+100+mi)
    report={'schema_version':'memaudit-agentdojo-all97-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'COMPLETE','claim_boundary':c['claim_boundary'],'population':{'official_tasks':len(archives),'truth_instances':len(instances),'harmful_events':sum(len(i['affected_ids']) for i in instances.values()),'posterior_views':len(source['views']),'method_rows':len(rows)},'design':{'event_mode':'forced exposure of every logged harmful memory','batch_unit':'all harmful events in one truth instance','terminal_capacity':'min(nominal budget, archive depth)','provenance_use':'none; results repeat across provenance masks','resource_note':'MemAudit exhaustively audits top-5 event bundles; its diagnostic calls are not budget-matched to active-search replay budgets'},'counterfactual_calls':total_calls,'summaries':summaries,'task_clustered_intervals':intervals,'paired_memaudit_budget4_minus_baselines':comparisons,'rows':rows,'score_rows':score_rows,'artifact_hashes':{'config':digest(CONFIG),'runner':digest(Path(__file__)),'adapter':digest(ROOT/'src/mcx/memaudit_agentdojo.py'),'source':digest(ROOT/c['source_report'][0])},'elapsed_s':time.perf_counter()-started}
    OUTPUT.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'population':report['population'],'counterfactual_calls':total_calls,'summaries':summaries,'paired':comparisons,'elapsed_s':report['elapsed_s']},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
