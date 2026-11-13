# Local red-team run

Promptfoo and all generation are configured to use local Ollama. Do not run
without the remote-generation disable flag; this prevents accidental use of a
hosted generation service.

```powershell
$env:PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION = "true"
$env:ASSISTANT_SECURITY_TEST_KEY = "the same local test key configured on the API"
npm install
npm run redteam
```

The API key is read from the environment and is never stored in this folder.
Use a temporary test key and remove it after the run.
