# Offline mock vertical slice

Issue #26 proves the MarketData, LLM, research-schema and presentation contracts together without
constructing a live transport. The command is documented in the root README and accepts only the
fixed fictional `600XXX` request.

## Stage flow

The scheduler discovers executable task names, prompt versions, schemas and batching metadata from
`packages/prompts/registry.json` through `PromptCatalog`. It then runs S1, S2, isolated S3a–S3d
branches, S4 and S5 in stable order. S6 collects all localized text paths and divides them using the
registry's `max_texts_per_call`. Package assembly and Draft 2020-12 plus semantic validation happen
before S7. Each edition executes one S7 plan task and one registered slide task per ordered stub.

Every LLM boundary uses `LLMProvider.run(...)`. The injected scripted provider validates its output
against the exact bundled schema passed by the scheduler and returns realistic free-route metadata.
The whole public run patches socket creation to fail, so an accidental transport attempt cannot
reach a provider.

## Checkpoints and stopping

Each invocation appends an immutable checkpoint with stage, registered task name, prompt version,
attempt count, model metadata, safe error fields and an output digest. A retryable failure retries
only that invocation up to three attempts; completed upstream checkpoints are not rewritten. A
non-retryable failure stops immediately and no downstream task is called.

## Artifact bundle

```text
<output>/
├── manifest.json
├── research-package.json
├── slide-deck.zh-CN.json
├── slide-deck.en-AU.json
├── report.zh-CN.pptx
├── report.en-AU.pptx
├── overflow-zh-cn.json
├── overflow-en-au.json
└── audit/
    └── checkpoints.json
```

The PresentationProvider validates the verified package, deck schema, edition and package identity
before calling the read-only template entry point. PDF is explicitly unavailable. JSON artifacts
are deterministic for the fixed clock and fixtures; PPTX byte identity is not promised, but both
files remain native/editable and preserve equivalent IDs, values, references and slide counts.
