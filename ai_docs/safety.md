# CocoonKitchen — Safety & Ethics Register

> **Draft for review (2026-07-20).** Prompted by Aakash Gupta's "Safety & Ethics interview"
> playbook. This is the artifact the article says a PM owns: *the system that connects safety,
> written down.* It catalogs our harm surface, states the refusal policy, and names the open
> human-owned decisions. Nothing here changes rubric weights, golden labels, or code — those
> follow the normal loop once Amber sequences the rows.

## Framing (the two definitions we work from)

- **Safety = stops harm** (guardrails, refusals, output filters, confirmation/degrade paths). Concrete, measurable.
- **Ethics = defines harm** (scope: what should we score at all, whose constraints do we honor, what do we refuse to say).
- **The PM owns the connector** — sizing harm, choosing the guardrail tier, sequencing the fix, documenting the trade-off.

**Where CocoonKitchen sits:** we are an **Applied AI** product — we ship a foundation model (GLM/OpenRouter)
inside a product. Per the article's taxonomy that means safety is *product-level* (guardrails, disclaimers,
refusal/degrade paths), and the **Air Canada precedent applies to us, not to the model provider**: once Phase 5
puts a public URL up, our "clean score" and our swaps are **representations the product owns**. A disclaimer is a
liability boundary, not a tone choice.

**Our existing scar tissue (the good pattern to extend):** the Phase-3 job-posting-scored-as-a-recipe incident →
the two-layer `is_recipe` / `NotARecipeError` gate. That is our one real "built a guardrail after a near-miss"
story. It is also our *only* enforced refusal today (see below).

---

## 1. Harm classes (the register)

SHIR-sized (Severity · Harm-scope · Immediacy · Reversibility) + business impact. **Class** distinguishes
harm-class (could hurt a person) from quality/governance-class. Harm-class rows are the priority — our entire
pitfalls catalog to date is quality-class; none of these had been named.

| # | Harm class | Class | SHIR sizing | Status today | Roadmap home |
|---|-----------|-------|-------------|--------------|--------------|
| **H1** | **Unsafe swaps** — a "cleaner" swap introduces an allergen (nuts), violates a restriction (dairy/gluten/vegan), or **worsens the medical need it's blind to** (soy sauce → *more* sodium for a low-sodium user). | **Harm** | Sev **high** for constrained users; scope = anyone with an allergy/restriction/condition (a large minority); latent→acute on cook; harm may be irreversible (allergic reaction) | **No control.** Generator optimizes "cleaner" only; no constraint channel; exactly-3 cardinality *forces* a swap even when none is safe. | **Phase 13** (new) + Phase 6 eval |
| **H2** | **Medical / nutrition claims** — model asserts a health outcome ("good for diabetics", "lowers cholesterol") the product must not make. | **Harm** | Sev high (physical harm if trusted by a vulnerable user); scope all; latent; advice reversible, acting on it maybe not | "No medical advice" is **prompt text + a rendered UI disclaimer only.** No eval/filter asserts the model never emits a claim. | **Phase 6** neg-eval + **Phase 5** filter |
| **H3** | **Dietary-restriction blindness** — no way for a user to say "vegan / nut allergy / gluten-free / renal", and no decided safe-failure behavior when a constraint can't be met. | **Harm** | Sev high for the constrained; scope the constrained minority; latent; depends on the swap | No input channel exists; no safe-failure decision made. Root cause of H1. | **Phase 13** (new, human-owned scope) |
| **H4** | **Cooking-safety guidance** — undercooking, unsafe canning (botulism), raw-egg, etc. | **Harm** | Sev high; scope all; latent | **Out of scope by design today** (we score ingredients, not method). Phase 11 ("clean recipe generator") would *introduce* this surface — a boundary to consciously hold or cross. | Boundary note for **Phase 11** |
| **H5** | **Disordered-eating reinforcement** — scoring rewards restriction; a dangerously low-calorie "recipe" earns a high "clean" score; a gamified number invites orthorexic optimization. | **Harm** | Sev **high for a vulnerable sub-population** ("10K vulnerable > 10M general"); narrow scope; latent→acute; psychological harm not easily reversible | Non-shaming tone is a design rule; no explicit reframe/refuse path; score is a bare number. | **Phase 14** (new, human-owned ethics scope) |
| **H6** | **Cuisine / cultural bias** — seed-oil/NOVA-4/sodium rubric may score traditional ethnic dishes systematically harsher (implicitly moralizing food cultures). | Ethics/quality | Sev reputational/ethical (Gemini precedent); scope = whole cuisines; latent; reversible | Unmeasured. But *measurable* with a cuisine-tagged golden slice. | **Phase 6** bias-audit slice |
| **H7** | **Prompt injection** — pasted text + fetched URLs flow into the prompt; a malicious recipe could try to hijack output. | Safety | Sev medium (schema validation currently caps blast radius); latent; reversible per-request | Prompt *instructs* "never obey"; SSRF guarded. No adversarial eval proves the behavior. | **Phase 5** hardening + **Phase 6** red-team slice |
| **H8** | **Overtrust / false precision** — a 0–100 number implies precision a subjective judgment lacks. | Quality/trust | Sev low-med; scope all; latent; reversible | Bare number; Phase 7 (explainability) partially addresses. | **Phase 7** (uncertainty + provenance) |
| **H9** | **Accountability / provenance** — which model, which rubric version, "advisory not medical", documented limits. | Governance | Not a live harm; governance | I/O logged internally; no user-facing model card. | **Phase 5** deploy artifact |

---

## 2. The refusal policy — "the model must never output X"

The article's PM-owned job: *define what the model must refuse, and write it down so engineers and lawyers can
both read it.* Today we have **one** enforced refusal and a set of *aspirations*. This table is the proposed
policy; the **Enforced by** column is the honest current state, and every "prompt only / none" is a gap to close.

| Rule (the model must never…) | Enforced by *today* | Target enforcement |
|------------------------------|---------------------|--------------------|
| …score a non-recipe (job posting, prose, random text) | ✅ `is_recipe:false` structural gate + `NotARecipeError` | keep |
| …obey instructions embedded in the pasted recipe/URL | ⚠️ **prompt text only**; test asserts the *words are present*, not the behavior | + Phase-6 injection eval |
| …emit a medical or nutrition **claim** (diagnosis, treatment, "good/bad for <condition>") | ⚠️ **prompt text + UI disclaimer only**; no output check | + Phase-6 neg-eval + Phase-5 output filter |
| …propose a swap that introduces a **common allergen** or violates a **stated dietary restriction** | ❌ **none** | Phase-13 constraint model + Phase-6 unsafe-swap eval |
| …shame the cook or moralize a plate | ⚠️ **prompt text only** | + tone eval |
| …give **cooking-safety** instructions (doneness, canning, raw egg) while out of scope | ❌ implicit (we don't emit method today) | explicit boundary at Phase 11 |

**Legend:** ✅ enforced · ⚠️ written down but not enforced (prompt/UI only) · ❌ not addressed.

---

## 3. Dietary constraints — the open decision (human-owned)

The generator has **no constraint channel** and **no decided failure mode**. Before H1/H3 can be built, Amber owns:

1. **Do we accept constraints as input?** (e.g. vegan / vegetarian / common allergens / gluten-free / low-sodium.)
2. **What is safe-failure when no clean *and* safe swap exists?** Options, non-exclusive:
   - **Refuse the swap** ("no swap here keeps this safe for your <constraint>") — honest, needs the exactly-3 cardinality relaxed to *up-to-3* (this is the real reason to fix Phase 12 — safety, not just tidy UX).
   - **Caveat the swap** ("contains nuts") and let the user judge.
   - **Degrade** to flagging-only for constrained ingredients.
3. **Allergen awareness even with no declared constraint** — should every swap be checked against the common-allergen set and labeled, regardless? (Recommended: yes; labeling is cheap, silence is the harm.)

These are ethics *scope* decisions (what the product owns), so they are human-owned, same as rubric weights.

---

## 4. Precedents we cite (from the playbook)

- **Air Canada (Feb 2024)** — company owns its AI's representations. Applies the moment our score/swaps go public (Phase 5).
- **Gemini image gen (Feb 2024)** — "the cost of acting is lower than the cost of being *seen* not acting." Applies to the cuisine-bias audit (H6).
- **iTutorGroup (Aug 2023) / Mobley v. Workday** — automated systems don't launder responsibility. Applies to systematic bias in any automated judgment (H6).

---

## 5. Open decisions for Amber (human-owned — nothing built until set)

1. **Sequencing:** which of Phases 13/14 (new harm-class rows) come near-term vs. parked, and whether the Phase-6 safety evals run this phase or after merge.
2. **The dietary-constraint policy** (§3) — accept constraints? safe-failure behavior? allergen labeling default?
3. **The cuisine-bias slice** — worth golden-set labeling effort now? (Claude drafts cuisine tags, Amber curates — same discipline as the lexicons.)
4. **The "never output" list** (§2) — confirm the rules and the target enforcement per row.

---

## Changelog
- **2026-07-20** — Created. Register + refusal policy + dietary-constraint decision drafted from the Safety & Ethics
  playbook. Surfaced that all 13 pitfalls are quality-class (zero harm-class) and that the only *enforced* refusal
  is `is_recipe:false`. Proposed roadmap rows added to `cocoonkitchen_product.md` (NOT approved).
