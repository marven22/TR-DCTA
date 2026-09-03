"""Run TR-DCTA and baselines on all 97 official AgentDojo user tasks."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, os, statistics, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import _bootstrap  # noqa
from mcx.agentdojo_adapter import load_official_suites, replay_workflow, task_number
from mcx.agentdojo_method import random_policy, regime_prior, stable_seed
from mcx.agentdojo_variable_depth import lineages, masks, posterior
from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.terminal_recovery_dcta import run_terminal_recovery_dcta
from run_agentdojo_tr_dcta_development_v1 import STRUCTURED, aggregate, digest, result_row
from run_agentdojo_tr_dcta_heldout_v1 import archive_values, stratified_paired_bootstrap

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs'/'agentdojo_tr_dcta_all97_freeze_v1.json'
OUTPUT=ROOT/'reports'/'agentdojo_tr_dcta_all97_v1.json'

def selected_sources(qualifying, suite, user, salt):
    return tuple(sorted(set(qualifying), key=lambda inj: hashlib.sha256(f'{salt}|{suite}|{user}|{inj}'.encode()).hexdigest())[:3])

def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,default=CONFIG); p.add_argument('--output',type=Path,default=OUTPUT); a=p.parse_args()
    c=json.loads(a.config.read_text());
    if os.environ.get('PYTHONHASHSEED')!=c['python_hash_seed']: raise RuntimeError('PYTHONHASHSEED mismatch')
    if importlib.metadata.version('agentdojo')!=c['agentdojo_package_version']: raise RuntimeError('AgentDojo version mismatch')
    suites=load_official_suites(c['benchmark_version']); sources=tuple(c['source_ids']); started=time.perf_counter()
    archives=[]; screening={}; screened_pairs=0; qualifying_pairs=0
    for suite_name in c['suites']:
        suite=suites[suite_name]; suite_counts={'official_user_tasks':len(suite.user_tasks),'official_injection_tasks':len(suite.injection_tasks),'candidate_pairs':0,'qualifying_pairs':0}
        for user_id,user_task in sorted(suite.user_tasks.items(),key=lambda x:task_number(x[0])):
            env=suite.load_and_inject_default_environment({}); env=user_task.init_environment(env); clean_calls=len(user_task.ground_truth(env))
            depth=2 if clean_calls==1 else 3; variants=tuple(c['two_stage_variants'] if depth==2 else c['three_stage_variants'])
            valid=[]; cache={}
            for injection_id in sorted(suite.injection_tasks,key=task_number):
                suite_counts['candidate_pairs']+=1; screened_pairs+=1
                clean=replay_workflow(suite,user_id,injection_id,'clean',score_clean_against_injection=True)
                positives={v:replay_workflow(suite,user_id,injection_id,v) for v in variants}
                ok=(clean.safe_success and not clean.attack_success and clean.error is None and
                    len({x.trace_digest for x in positives.values()})==depth and
                    all(x.attack_success and x.error is None for x in positives.values()))
                if ok: valid.append(injection_id); cache[injection_id]=(clean,positives); qualifying_pairs+=1; suite_counts['qualifying_pairs']+=1
            if len(valid)<3: raise RuntimeError(f'{suite_name}/{user_id} has fewer than three executable origins')
            chosen=selected_sources(valid,suite_name,user_id,c['selection_salt'])
            archive_id=f'agentdojo-all97-{suite_name}-{task_number(user_id):02d}'
            chains,mapping,layers=lineages(archive_id,sources,variants); replay_map={}
            for source,injection_id in zip(sources,chosen):
                clean,positives=cache[injection_id]
                for variant in variants:
                    node=mapping[(source,variant)]; replay_map[node]={'source_id':source,'injection_task_id':injection_id,'variant':variant,'negative':clean.to_dict(),'positive':positives[variant].to_dict()}
            archives.append({'archive_id':archive_id,'suite':suite_name,'user_task_id':user_id,'clean_tool_calls':clean_calls,'depth':depth,'variants':list(variants),'source_injection_tasks':dict(zip(sources,chosen)),'lineages':{k:list(v) for k,v in chains.items()},'by_depth':[list(x) for x in layers],'clean_fallback_safe':all(cache[x][0].safe_success for x in chosen),'replay_map':replay_map})
        screening[suite_name]=suite_counts; print(f'[all97] screened {suite_name}',flush=True)
    instances=[]; views=[]; rows=[]; regimes=tuple(c['confidence_regimes']); budgets=tuple(c['budgets'])
    for ai,archive in enumerate(archives):
        depth=archive['depth']; chains={k:tuple(v) for k,v in archive['lineages'].items()}; layers=tuple(tuple(x) for x in archive['by_depth']); weights={node:float(c['stage_harm_weights'][d]) for d,layer in enumerate(layers) for node in layer}; capacity=depth
        mask_sets={condition:masks(archive['archive_id'],chains,condition,int(reps),c['mask_namespace']) for condition,reps in c['conditions'].items()}
        for si,true_source in enumerate(sources):
            length=1+(ai+si)%depth; regime=regimes[(ai*3+si)%4]; decoy=sources[(si+1)%3]; prior=regime_prior(sources,true_source,decoy,c['source_priors'][regime]); affected=frozenset(chains[true_source][:length])
            instance={'instance_id':f"{archive['archive_id']}--truth-{si}",'archive_id':archive['archive_id'],'suite':archive['suite'],'depth':depth,'true_source':true_source,'true_cascade_length':length,'confidence_regime':regime,'source_prior':prior,'affected_ids':sorted(affected)}; instances.append(instance); truth=LatentSourceWorld(true_source,affected,1.0)
            for condition,mask_list in mask_sets.items():
                for rep,nonce,pattern,edges in mask_list:
                    belief,completions=posterior(sources,layers,edges,prior,(1/depth,)*depth)
                    support=sum(w.weight for w in belief.worlds if w.source_id==true_source and w.affected_ids==affected)
                    views.append({'instance_id':instance['instance_id'],'condition':condition,'mask_replicate':rep,'mask_nonce':nonce,'hidden_counts_by_layer':list(pattern),'observed_edges':[list(x) for x in edges],'completion_count':completions,'truth_support':support})
                    for budget in budgets:
                        effective=min(budget,len(belief.candidates))
                        tr=run_terminal_recovery_dcta(belief,truth,effective,weights=weights,quarantine_capacity=capacity)
                        rr=result_row(instance,condition,'tr_dcta',effective,None,tr.replayed_ids,tr.final_posterior,weights,capacity,archive['clean_fallback_safe']); rr.update({'nominal_budget':budget,'mask_replicate':rep}); rows.append(rr)
                        for method in STRUCTURED:
                            sc_mode=None; override=None
                            if method=='sc_dcta':
                                dec=confidence_aware_decision(belief,effective,weights); sc_mode=dec.mode; policy='top1_dcta' if dec.mode=='hard' else 'prob_dcta'; out=run_latent_policy(belief,truth,effective,method=policy,weights=weights)
                            elif method=='hard_source_dcta': out=run_latent_policy(belief,truth,effective,method='top1_dcta',weights=weights)
                            elif method=='positive_only_dcta': out=run_latent_policy(belief,truth,effective,method='positive_only_risk',weights=weights)
                            elif method=='oracle_source': out=run_latent_policy(belief.restrict_source(true_source),truth,effective,method='prob_dcta',weights=weights)
                            elif method=='full_information_hindsight':
                                out=run_latent_policy(belief,truth,effective,method='prob_dcta',weights=weights); fill=[x for x in sorted(belief.candidates) if x not in affected]; override=tuple(sorted(affected))+tuple(fill[:capacity-len(affected)])
                            else: out=run_latent_policy(belief,truth,effective,method=method,weights=weights)
                            rr=result_row(instance,condition,method,effective,None,out.replayed_ids,out.final_posterior,weights,capacity,archive['clean_fallback_safe'],sc_mode=sc_mode,quarantine_override=override); rr.update({'nominal_budget':budget,'mask_replicate':rep}); rows.append(rr)
                        for random_rep in range(int(c['random_replicates'])):
                            replayed,final=random_policy(belief,affected,effective,stable_seed(c['random_seed'],instance['instance_id'],condition,rep,budget,random_rep)); rr=result_row(instance,condition,'random',effective,random_rep,replayed,final,weights,capacity,archive['clean_fallback_safe']); rr.update({'nominal_budget':budget,'mask_replicate':rep}); rows.append(rr)
        print(f'[all97] evaluated {ai+1}/97',flush=True)
    # Restore nominal budget for aggregation and inference; actual replay count remains explicit.
    for row in rows: row['effective_budget']=row['budget']; row['budget']=row.pop('nominal_budget')
    primary={}; comparisons={}; suites_by={x['archive_id']:x['suite'] for x in archives}
    for condition in c['conditions']:
        values=archive_values(rows,condition,int(c['primary_budget']),'safe_recovery_success'); primary[condition]={m:statistics.fmean(v[m] for v in values.values()) for m in c['methods']}; comparisons[condition]={}
        for j,comp in enumerate(c['primary_comparators']): comparisons[condition][comp]=stratified_paired_bootstrap(values,suites_by,'tr_dcta',comp,int(c['bootstrap_draws']),int(c['bootstrap_seed'])+100*list(c['conditions']).index(condition)+j)
    strata={}
    for label,subset in [('all97',set(a['archive_id'] for a in archives)),('two_stage',set(a['archive_id'] for a in archives if a['depth']==2)),('three_stage',set(a['archive_id'] for a in archives if a['depth']==3))]:
        strata[label]={}
        for condition in c['conditions']:
            strata[label][condition]={m:statistics.fmean(float(r['safe_recovery_success']) for r in rows if r['archive_id'] in subset and r['condition']==condition and r['budget']==4 and r['method']==m) for m in c['methods']}
    expected_views=len(instances)*11; expected_scenarios=expected_views*3
    integrity={'official_tasks_97':len(archives)==97,'all_pairs_screened':screened_pairs==949,'two_stage_19':sum(a['depth']==2 for a in archives)==19,'three_stage_78':sum(a['depth']==3 for a in archives)==78,'three_origins_each':all(len(a['source_injection_tasks'])==3 for a in archives),'executable_labels':all(v[p]['error'] is None and (v[p]['attack_success'] if p=='positive' else v[p]['safe_success']) for a in archives for v in a['replay_map'].values() for p in ('positive','negative')),'views_exact':len(views)==expected_views,'truth_support':all(v['truth_support']>0 for v in views),'tr_grid':sum(r['method']=='tr_dcta' for r in rows)==expected_scenarios,'structured_grid':sum(r['method'] in STRUCTURED for r in rows)==expected_scenarios*len(STRUCTURED),'random_grid':sum(r['method']=='random' for r in rows)==expected_scenarios*50,'effective_budget_exact':all(len(r['replayed_ids'])==r['effective_budget'] for r in rows)}
    report={'schema_version':'agentdojo-tr-dcta-all97-v1','protocol':c['protocol'],'created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'COMPLETE' if all(integrity.values()) else 'INVALID','claim_boundary':'descriptive_full_dataset_after_method_development','counts':{'official_user_tasks':len(archives),'screened_pairs':screened_pairs,'qualifying_pairs':qualifying_pairs,'two_stage_tasks':19,'three_stage_tasks':78,'truth_instances':len(instances),'posterior_views':len(views),'method_runs':len(rows)},'integrity':integrity,'primary_budget4':primary,'paired_task_bootstrap':comparisons,'stage_breakdowns_budget4':strata,'summary':aggregate(rows),'screening':screening,'archives':archives,'instances':instances,'views':views,'rows':rows,'elapsed_s':time.perf_counter()-started,'artifact_hashes':{'config':digest(a.config),'runner':digest(Path(__file__))}}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({k:report[k] for k in ('status','counts','integrity','primary_budget4','stage_breakdowns_budget4','elapsed_s')},indent=2)); return 0 if all(integrity.values()) else 2
if __name__=='__main__': raise SystemExit(main())
