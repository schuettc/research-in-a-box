<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Deployment skill and CI (Plan 10a)

`research-archive-in-a-box/deployment-skill-and-ci` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 5 of 7** → Sign off

PLAN1 building · 5 of 7 done

Running: Task 7: Stop waiting ingest runs before destroy (PLAN1)

## Pick up next

- **PARK1 Page rollout by reindex:** Once Plan 8 makes the reindex rewrite every dataset page after its flip, rolling out a template change is just reindex &lt;stage> after a deploy. Add that to the skill's update step (and decide then whether CI runs it after each deploy, since a reindex wants publishing quiet). Agreed with the coordinating session (muster #960).
- **PARK2 CodeQL and cdk-nag:** Add CodeQL or cdk-nag to CI's security job once a real finding shows the dependency audits and zizmor miss something.
- **PARK3 Deploy concurrency group:** Add a concurrency group per stage to the deploy job, so two quick pushes to main don't deploy the same stage at once (from the final review).
- **PARK4 Smoke after seeding:** Once a stage has been seeded, have smoke fail rather than skip when search stops listing the sample dataset, so a search regression isn't hidden (from the final review).
- **PARK5 Trust keyed on repo id:** Use GitHub's custom OIDC sub template with the repo id, so a deleted and re-created repo of the same name can't match the deploy role's trust (from the final review).
- **PARK6 Seed's time limit overrun:** just seed checks its 15-minute limit after the next request, so it can overrun by one request (up to a minute) and could approve just after the limit. Check the deadline before each request (from the Task 4 review).

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 4, the archive infrastructure.)
> 
> Brief: Plan 10a in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the deployment skill and CI (Plan 10a). The skill ships in the repo and is for the person running an archive, not for researchers. Plan its steps and the points where it must stop and ask.

## Decisions

- **DCSN1 How the seed signs in.** How should the skill sign in as the new admin to submit and approve the sample package on a real (prod) stage? The user chose A: Browser sign-in, built once as Plan 9's shared module.
- **DCSN2 Upstream updates to a fork.** How should upstream changes to the kit reach an adopter's fork? The user chose A: The skill's update step merges upstream.
- **DCSN3 What the smoke test covers.** What should just smoke &lt;stage> check after a deploy? The user chose A: Read-only checks, no sign-in.
- **AGNT1 Deploy role stack.** A small separate CDK stack, ResearchArchiveDeploy, in packages/infra. It holds GitHub's OIDC provider and one role that trusts only this repo's GitHub environments and may assume only the CDK bootstrap roles. The skill deploys it from the laptop once per account, after cdk bootstrap if needed, and stores the role ARN as a repo variable. The user kept it.
- **AGNT2 Deploy order and environments.** On every push to main once the checks pass, one job per stage in the order archive.yaml lists them, each waiting for the one before. Each job runs in a GitHub environment named for the stage, which is what the role's trust is scoped to. With no deploy-role variable set, the deploy job skips. The user kept it.
- **AGNT3 Security checks.** Dependency audits (pip-audit on the exported uv lock, npm audit at high) and zizmor on the workflows, as one security job. The user kept it.
- **AGNT4 Settings from the schema.** It reads ArchiveConfig's JSON Schema (packages/web/src/schema/archive-contract.schema.json) for each setting's name, default and description, and validates the written file with the contract's load_config. The user kept it.
- **AGNT5 Teardown from the laptop.** A just destroy &lt;stage> recipe run from the laptop, never in CI. The skill makes the user type the stage name and says that prod keeps its buckets and tables. After cdk destroy it deletes the leftover log group of CDK's S3 auto-delete helper (Plan 4's PARK12) and confirms the stack is gone. The user kept it.
- **AGNT6 Cost before deploy.** It names what bills while idle and what bills per use, and the monthly budget alarm already in the config. It gives no dollar figure, since none has been measured. The user kept it.
- **AGNT7 First admin's groups.** admin, curator and contributor. just invite-user takes a comma-separated group list, so the skill runs just invite-user &lt;stage> &lt;email> admin,curator,contributor. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The deployment skill](spec.md#the-deployment-skill): rests on AGNT4, AGNT6, AGNT7
- [Connecting GitHub to AWS](spec.md#connecting-github-to-aws): rests on AGNT1
- [CI](spec.md#ci): rests on AGNT2, AGNT3
- [Seeding and the sign-in](spec.md#seeding-and-the-sign-in): rests on DCSN1, AGNT7
- [The smoke test](spec.md#the-smoke-test): rests on DCSN3
- [Update](spec.md#update): rests on DCSN2
- [Teardown](spec.md#teardown): rests on AGNT5
- [Risk and cost](spec.md#risk-and-cost): rests on AGNT1, AGNT5
- [Left out](spec.md#left-out): rests on DCSN2, DCSN3, AGNT3
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN3, AGNT1, AGNT2, AGNT5

## Plans

- [PLAN1](plans/1-deploy-skill-and-ci.md) The deployment skill and CI: building · 5 of 7 done
  - TASK1 Task 1: The deploy role stack: done. research-in-a-box#40 merged (eccd6a7); deploy-access synth tests pass; just check exit 0
  - TASK2 Task 2: CI's security and deploy jobs: done. #40 merged; main's CI run 43571390820: security, python, typescript, stages all success; deploy (prod) success with the notice 'prod has no AWS_DEPLOY_ROLE_ARN in its environment; skipped' and the cdk deploy step skipped
  - TASK3 Task 3: just smoke, just destroy and invite-user's groups: done. research-in-a-box#40 merged (eccd6a7); smoke tests pass; just check exit 0
  - TASK4 Task 4: just seed: done. research-in-a-box#43 merged (b540cc8); python, typescript and security green; just check exit 0; 6 seed tests
  - TASK5 Task 5: The deploy-archive skill: done. research-in-a-box#40 merged (eccd6a7); prettier exit 0
  - TASK6 Task 6: The live run on a throwaway copy: waiting on STEP1
  - TASK7 Task 7: Stop waiting ingest runs before destroy: building

## Steps

- STEP1 Walk the deployment skill end to end on a throwaway copy: action 1 of 7 · needs the user
  1. The user · Choose the AWS profile and region, and Go on creating two private throwaway repos · to come. Answers: Go: The agent creates both repos and the clone · No go (hands it back)
  2. agent · Create both repos, push main, and prepare the clone with archive.yaml listing one stage, deploy-test, and upstream pointing at research-in-a-box-upstream-test · to come
  3. The user · Run the skill in the clone and answer each stop · to come
  4. agent · Confirm CI deployed ResearchArchive-deploy-test, the seed published, and just smoke deploy-test passes every check · to come
  5. agent · Push a one-line change to research-in-a-box-upstream-test's main, run the skill's update in the clone, and confirm it merges, checks and deploys · to come
  6. The user · Go on the teardown, including deleting both throwaway repos · to come. Answers: Go: The agent tears down and deletes both repos · No go (hands it back)
  7. agent · Tear down the stage and the deploy access, confirm nothing is left, and delete both throwaway repos · to come

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `plans/` | the agent, header by diazo | One file per plan. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |
| `diagrams/` | diazo | The drawn picture (SVG) of each mermaid diagram in the folder. |

## Ids

Every card has an id: its prefix, then a number.

- `DCSN`: a decision the user makes
- `AGNT`: a call the agent made, which the user may reverse
- `PRIN`: a principle
- `PARK`: a follow-up, for later
- `STEP`: a step only the user can do
- `ASK`: an ask of someone other than the user
- `PLAN`: a plan
- `TASK`: a task of a plan

The full record is `decisions.json`; its schema is [schema/record.json](https://github.com/subaud-tools/diazo/blob/main/schema/record.json).
